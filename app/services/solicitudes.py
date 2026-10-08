"""Embudo de solicitudes de préstamo (RF-020 a RF-022, RF-024, RF-065, RF-066)."""

import logging
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from app.models.models import Cliente, ConfiguracionSistema, Contrato, SolicitudPrestamo, TipoPrestamo
from app.schemas.prestamo import PrestamoCreate
from app.schemas.solicitud import DecisionCreate, SolicitudCreate
from app.services.contratos import emitir_contrato
from app.services.prestamo import crear_prestamo
from app.services.scoring import consultar_scoring
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)

DEFAULT_DIAS_EXPIRACION = 7


def _config(db: Session, clave: str, default: str) -> str:
    fila = db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == clave).first()
    return fila.valor if fila and fila.valor is not None else default


def _dias_expiracion(db: Session) -> int:
    try:
        return max(1, int(_config(db, "dias_expiracion_solicitud", str(DEFAULT_DIAS_EXPIRACION))))
    except ValueError:
        return DEFAULT_DIAS_EXPIRACION


def _firma_requerida(db: Session) -> bool:
    return _config(db, "firma_contrato_requerida", "false").lower() == "true"


def crear_solicitud(db: Session, datos: SolicitudCreate, usuario_id: int, ip_address: str | None = None):
    cliente = db.query(Cliente).filter(Cliente.id == datos.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if cliente.estado != "activo":
        raise HTTPException(status_code=400, detail="El cliente está bloqueado: la solicitud no puede registrarse")

    tipo = db.query(TipoPrestamo).filter(TipoPrestamo.id == datos.tipo_prestamo_id).first()
    if not tipo or tipo.estado != "activo":
        raise HTTPException(status_code=404, detail="Tipo de préstamo no encontrado o inactivo")

    if tipo.max_cuotas and datos.plazo_cuotas > tipo.max_cuotas:
        raise HTTPException(
            status_code=400,
            detail=f"El plazo no puede superar las {tipo.max_cuotas} cuotas del tipo de préstamo",
        )

    porcentaje = (
        datos.porcentaje_interes
        if datos.porcentaje_interes is not None
        else (tipo.interes_mensual or 0.0)
    )

    solicitud = SolicitudPrestamo(
        cliente_id=datos.cliente_id,
        tipo_prestamo_id=datos.tipo_prestamo_id,
        monto_solicitado=datos.monto_solicitado,
        plazo_cuotas=datos.plazo_cuotas,
        porcentaje_interes=porcentaje,
        motivo=datos.motivo,
        estado="pendiente",
        usuario_creador_id=usuario_id,
    )
    db.add(solicitud)
    db.commit()
    db.refresh(solicitud)

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="solicitudes_prestamo",
        tipo_operacion="CREATE",
        registro_id=solicitud.id,
        valores_nuevos={
            "cliente_id": solicitud.cliente_id,
            "monto_solicitado": solicitud.monto_solicitado,
            "plazo_cuotas": solicitud.plazo_cuotas,
            "estado": solicitud.estado,
        },
        descripcion=f"Solicitud #{solicitud.id} registrada para cliente {cliente.nombre}",
        ip_address=ip_address,
    )
    return solicitud


def get_solicitudes(
    db: Session,
    page: int = 1,
    limit: int = 10,
    estado: str | None = None,
    cliente_id: int | None = None,
):
    query = db.query(SolicitudPrestamo).options(
        selectinload(SolicitudPrestamo.cliente),
        selectinload(SolicitudPrestamo.tipo_prestamo),
        selectinload(SolicitudPrestamo.creador),
        selectinload(SolicitudPrestamo.evaluador),
    )
    if estado:
        query = query.filter(SolicitudPrestamo.estado == estado)
    if cliente_id:
        query = query.filter(SolicitudPrestamo.cliente_id == cliente_id)
    query = query.order_by(SolicitudPrestamo.id.desc())
    return paginate(query, page=page, limit=limit)


def get_solicitud(db: Session, solicitud_id: int) -> SolicitudPrestamo:
    solicitud = (
        db.query(SolicitudPrestamo)
        .options(
            selectinload(SolicitudPrestamo.cliente),
            selectinload(SolicitudPrestamo.tipo_prestamo),
            selectinload(SolicitudPrestamo.creador),
            selectinload(SolicitudPrestamo.evaluador),
        )
        .filter(SolicitudPrestamo.id == solicitud_id)
        .first()
    )
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


def evaluar_scoring(db: Session, solicitud_id: int) -> dict:
    """Adjunta el puntaje de scoring a la solicitud (RF-065)."""
    solicitud = get_solicitud(db, solicitud_id)
    puntaje, detalle, advertencia = consultar_scoring(db, solicitud.cliente_id)
    if puntaje is not None:
        solicitud.puntaje_scoring = puntaje
        solicitud.scoring_detalle = detalle
        db.commit()
        db.refresh(solicitud)
    return {
        "solicitud_id": solicitud.id,
        "puntaje": puntaje,
        "detalle": detalle,
        "advertencia": advertencia,
    }


def decidir_solicitud(
    db: Session,
    solicitud_id: int,
    datos: DecisionCreate,
    usuario_id: int,
    ip_address: str | None = None,
) -> SolicitudPrestamo:
    solicitud = get_solicitud(db, solicitud_id)
    if solicitud.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"La solicitud ya fue decidida (estado: {solicitud.estado})")

    puntaje, detalle, advertencia = consultar_scoring(db, solicitud.cliente_id)
    if puntaje is not None:
        solicitud.puntaje_scoring = puntaje
        solicitud.scoring_detalle = detalle
    if advertencia:
        logger.warning("[SOLICITUDES] Scoring solicitud %s: %s", solicitud.id, advertencia)

    solicitud.evaluador_id = usuario_id
    solicitud.fecha_decision = datetime.utcnow()
    solicitud.motivo_decision = datos.motivo

    aprobada = datos.accion == "aprobar"
    solicitud.estado = "aprobada" if aprobada else "rechazada"
    if aprobada:
        solicitud.fecha_expiracion = date.today() + timedelta(days=_dias_expiracion(db))

    db.commit()
    db.refresh(solicitud)

    if aprobada:
        emitir_contrato(db, solicitud, usuario_id)

    _notificar_decision(db, solicitud, aprobada)

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="solicitudes_prestamo",
        tipo_operacion="UPDATE",
        registro_id=solicitud.id,
        valores_anteriores={"estado": "pendiente"},
        valores_nuevos={
            "estado": solicitud.estado,
            "motivo": solicitud.motivo_decision,
            "puntaje_scoring": solicitud.puntaje_scoring,
        },
        descripcion=f"Solicitud #{solicitud.id} {solicitud.estado}",
        ip_address=ip_address,
    )
    return solicitud


def _notificar_decision(db: Session, solicitud: SolicitudPrestamo, aprobada: bool) -> None:
    """Notificación interna + push al creador (RF-023) y aviso al cliente (RF-061/062)."""
    if solicitud.usuario_creador_id:
        try:
            from app.services.notificacion import registrar_notificacion

            estado_txt = "aprobada" if aprobada else "rechazada"
            registrar_notificacion(
                db,
                usuario_id=solicitud.usuario_creador_id,
                titulo=f"Solicitud #{solicitud.id} {estado_txt}",
                mensaje=f"La solicitud de ${solicitud.monto_solicitado:,.2f} fue {estado_txt}. {solicitud.motivo_decision}",
                url=f"/solicitudes/{solicitud.id}",
                tipo="solicitud",
            )
        except Exception:  # noqa: BLE001 - la notificación no debe revertir la decisión
            logger.exception("Error registrando notificación de decisión")

    cliente = solicitud.cliente
    if cliente and cliente.telefono:
        try:
            from app.services.canales import enviar_por_canal

            enviar_por_canal(
                db,
                canal="sms",
                destinatario=cliente.telefono,
                clave="solicitud_decidida",
                contexto={
                    "nombre": cliente.nombre.split()[0] if cliente.nombre else "cliente",
                    "monto": f"{solicitud.monto_solicitado:,.0f}",
                    "estado": "aprobada" if aprobada else "rechazada",
                    "motivo": solicitud.motivo_decision or "—",
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("Error enviando aviso de decisión al cliente")


def convertir_solicitud(
    db: Session,
    solicitud_id: int,
    porcentaje_interes: float | None = None,
    numero_cuotas: int | None = None,
    observaciones: str | None = None,
    usuario_id: int = 0,
    ip_address: str | None = None,
):
    solicitud = get_solicitud(db, solicitud_id)

    if solicitud.estado == "expirada":
        raise HTTPException(status_code=400, detail="La solicitud aprobada expiró y ya no puede convertirse")
    if solicitud.estado != "aprobada":
        raise HTTPException(status_code=400, detail="Solo las solicitudes aprobadas pueden convertirse en préstamo")
    if solicitud.fecha_expiracion and solicitud.fecha_expiracion < date.today():
        solicitud.estado = "expirada"
        db.commit()
        raise HTTPException(status_code=400, detail="La solicitud aprobada expiró y ya no puede convertirse")

    if _firma_requerida(db):
        contrato = (
            db.query(Contrato)
            .filter(Contrato.solicitud_id == solicitud.id, Contrato.estado != "rechazado")
            .order_by(Contrato.id.desc())
            .first()
        )
        if not contrato or contrato.estado != "firmado":
            raise HTTPException(
                status_code=400,
                detail="La firma del contrato es obligatoria antes de convertir la solicitud en préstamo",
            )

    plazo = numero_cuotas or solicitud.plazo_cuotas
    tipo = db.query(TipoPrestamo).filter(TipoPrestamo.id == solicitud.tipo_prestamo_id).first()
    if tipo and tipo.max_cuotas and plazo > tipo.max_cuotas:
        raise HTTPException(status_code=400, detail=f"El plazo no puede superar las {tipo.max_cuotas} cuotas")

    datos_prestamo = PrestamoCreate(
        cliente_id=solicitud.cliente_id,
        tipo_prestamo_id=solicitud.tipo_prestamo_id,
        capital_prestado=solicitud.monto_solicitado,
        porcentaje_interes=porcentaje_interes if porcentaje_interes is not None else solicitud.porcentaje_interes,
        numero_cuotas=plazo,
        observaciones=observaciones or f"Convertido de solicitud #{solicitud.id}",
    )
    # crear_prestamo valida capital disponible (RF-026) y puede lanzar 400.
    prestamo = crear_prestamo(db, datos_prestamo, usuario_id, ip_address=ip_address)

    solicitud.estado = "convertida"
    solicitud.prestamo_id = prestamo.id
    db.commit()
    db.refresh(solicitud)

    contrato = (
        db.query(Contrato)
        .filter(Contrato.solicitud_id == solicitud.id, Contrato.estado != "rechazado")
        .order_by(Contrato.id.desc())
        .first()
    )
    if contrato:
        contrato.prestamo_id = prestamo.id
        db.commit()

    if solicitud.usuario_creador_id:
        try:
            from app.services.notificacion import registrar_notificacion

            registrar_notificacion(
                db,
                usuario_id=solicitud.usuario_creador_id,
                titulo=f"Solicitud #{solicitud.id} convertida",
                mensaje=f"La solicitud se convirtió en el préstamo #{prestamo.id}.",
                url=f"/prestamos/{prestamo.id}",
                tipo="solicitud",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Error notificando conversión")

    return solicitud, prestamo
