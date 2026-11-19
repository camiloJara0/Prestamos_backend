import json
from datetime import date
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.core.context import aplicar_filtro_usuario
from app.dependencies.auth import get_current_user, require_rol
from app.models import IdempotencyKey, PrestamoCuota, Prestamo, Cliente, Pago, Usuario
from app.schemas.pago import PagoCreate, PagoOut, PagoDevolucionCreate, PagoHistorialOut
from app.schemas.pagination import PaginatedResponse
from app.services.pago import get_pagos, registrar_pago, devolver_pago, resumen_deuda_cuota
from app.utils.pdf_generator import generar_recibo_pdf_bytes

router = APIRouter(prefix="/pagos", tags=["Pagos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _obtener_usuario_id(current_user: dict, db: Session) -> int:
    val_sub = current_user.get("sub") or current_user.get("id") or current_user.get("email")
    if isinstance(val_sub, int) or (isinstance(val_sub, str) and val_sub.isdigit()):
        return int(val_sub)

    usuario_db = db.query(Usuario).filter(Usuario.email == str(val_sub)).first()
    if not usuario_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario autenticado no se encuentra en el sistema."
        )
    return usuario_db.id


@router.post("/", response_model=PagoOut, status_code=status.HTTP_200_OK)
def crear_pago(
    pago: PagoCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    key = x_idempotency_key or getattr(pago, "idempotency_key", None)

    # 1. Verificar si la clave de idempotencia ya existe
    if key:
        existente = (
            db.query(IdempotencyKey)
            .filter(IdempotencyKey.key == str(key))
            .first()
        )
        if existente:
            return JSONResponse(
                status_code=existente.status_code,
                content=json.loads(existente.response),
            )

    # 2. Obtener el ID del usuario de manera segura
    usuario_id = _obtener_usuario_id(current_user, db)

    # 3. Registrar el pago en la base de datos
    nuevo_pago = registrar_pago(db, pago, usuario_id=usuario_id, ip_address=_ip(request))

    # 4. Convertir a esquema y guardar clave de idempotencia
    pago_dict = PagoOut.model_validate(nuevo_pago).model_dump(mode="json")

    if key:
        registro_key = IdempotencyKey(
            key=str(key),
            response=json.dumps(pago_dict),
            status_code=status.HTTP_200_OK,
        )
        db.add(registro_key)
        db.commit()

    return nuevo_pago


@router.get("/", response_model=PaginatedResponse[PagoHistorialOut])
def listar_pagos(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    cliente_id: int | None = Query(None, description="Filtrar pagos por cliente"),
    tipo_pago_id: int | None = Query(None, description="Filtrar pagos por tipo de pago"),
    fecha_desde: date | None = Query(None, description="Fecha inicial (inclusive)"),
    fecha_hasta: date | None = Query(None, description="Fecha final (inclusive)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Historial global de pagos con filtros por cliente, fecha y tipo (RF-041)."""
    return get_pagos(
        db,
        page=page,
        limit=limit,
        cliente_id=cliente_id,
        tipo_pago_id=tipo_pago_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


@router.get("/deuda", summary="Deuda vigente de una cuota (tiempo real)")
def resumen_deuda(
    cuota_id: int = Query(..., description="Cuota a evaluar"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Deuda al día de hoy de una cuota: capital pendiente, interés corriente,
    mora acumulada y total a pagar.

    La mora se calcula en tiempo real con la configuración personalizada del
    usuario (días de gracia, porcentaje o valor fijo, simple o compuesta) y no
    requiere que el procesamiento diario haya corrido.
    """
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="La cuota especificada no existe.")
    prestamo = (
        aplicar_filtro_usuario(db.query(Prestamo), Prestamo)
        .filter(Prestamo.id == cuota.prestamo_id)
        .first()
    )
    if not prestamo:
        raise HTTPException(
            status_code=404,
            detail="El préstamo de esta cuota no existe o no está disponible.",
        )
    return resumen_deuda_cuota(db, cuota)


@router.get("/{pago_id}", response_model=PagoOut)
def obtener_pago(
    pago_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Obtiene los detalles de un pago específico por su ID.
    """
    pago = aplicar_filtro_usuario(db.query(Pago), Pago).filter(Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="El pago especificado no existe.")
    return pago


@router.post("/{pago_id}/devolver", response_model=PagoOut)
def solicitar_devolucion_pago(
    pago_id: int,
    datos_devolucion: PagoDevolucionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin", "prestamista")),
):
    """
    Anula/Devuelve un pago previamente registrado dentro del margen máximo de 30 días,
    realizando la reversión en cascada de cuota, préstamo, saldo global y auditoría (RF-042).
    Solo administrador.
    """
    usuario_id = _obtener_usuario_id(current_user, db)
    pago_devuelto = devolver_pago(
        db=db,
        pago_id=pago_id,
        datos_devolucion=datos_devolucion,
        usuario_id=usuario_id,
        ip_address=_ip(request),
    )
    return pago_devuelto


def _construir_datos_recibo(db: Session, cuota: PrestamoCuota, pago_registro: Pago | None) -> dict:
    """Arma los datos del comprobante PDF para una cuota y su pago (RF-043)."""
    from app.services.comprobante import construir_datos_recibo

    return construir_datos_recibo(db, cuota, pago_registro)


def _responder_pdf(datos_recibo: dict) -> Response:
    pdf_bytes = generar_recibo_pdf_bytes(datos_recibo)
    nombre_archivo = f"Recibo_{datos_recibo['referencia_recibo']}.pdf"
    return Response(
        content=pdf_bytes.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )


@router.get("/cuota/{cuota_id}/recibo-pdf")
def descargar_recibo_cuota_pdf(
    cuota_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Genera y descarga en tiempo real el recibo en PDF de una cuota pagada.
    """
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="La cuota no existe.")
    prestamo = (
        aplicar_filtro_usuario(db.query(Prestamo), Prestamo)
        .filter(Prestamo.id == cuota.prestamo_id)
        .first()
    )
    if not prestamo:
        raise HTTPException(status_code=404, detail="El préstamo de esta cuota no existe o no está disponible.")

    pago_registro = db.query(Pago).filter(Pago.cuota_id == cuota.id).order_by(Pago.id.desc()).first()
    return _responder_pdf(_construir_datos_recibo(db, cuota, pago_registro))


# ---------------------------------------------------------------------------
# Envío del comprobante por WhatsApp (PrestamoPagoModal)
# ---------------------------------------------------------------------------
def _enviar_comprobante_whatsapp(db: Session, pago_registro: Pago, current_user: dict) -> dict:
    from urllib.parse import quote_plus

    from app.core.context import usuario_actual_id, usuario_actual_rol
    from app.services.canales import enviar_whatsapp_directo
    from app.services.configuracion import obtener_nombre_empresa
    from app.services.rate_limit import verificar_rate_limit

    uid = usuario_actual_id.get()
    verificar_rate_limit(f"comprobante_wa:{uid}", maximo=15, ventana_segundos=60)

    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == pago_registro.cuota_id).first()
    prestamo = (
        db.query(Prestamo).filter(Prestamo.id == pago_registro.prestamo_id).first()
    )
    cliente = (
        db.query(Cliente).filter(Cliente.id == pago_registro.cliente_id).first()
    )

    # Validación: el cliente debe tener teléfono registrado para habilitar el envío
    telefono = "".join(c for c in (cliente.telefono or "") if c.isdigit()) if cliente else ""
    if not telefono:
        raise HTTPException(
            status_code=400,
            detail="El cliente no tiene número telefónico registrado. Actualiza la ficha del cliente para habilitar el envío.",
        )

    empresa = obtener_nombre_empresa(db)
    monto = f"${pago_registro.valor_pagado:,.0f}".replace(",", ".")
    fecha = str(pago_registro.fecha_pago or "").split("T")[0].split(" ")[0]
    cuerpo = (
        f"Hola {cliente.nombre}, te compartimos el comprobante de tu pago.\n"
        f"Recibo: {pago_registro.referencia_recibo}\n"
        f"Cuota #{cuota.numero_cuota} del préstamo #{prestamo.id}\n"
        f"Valor pagado: {monto}\n"
        f"Fecha: {fecha}\n\n"
        f"Gracias por tu puntualidad.\n{empresa}"
    )

    datos_recibo = _construir_datos_recibo(db, cuota, pago_registro)
    pdf = generar_recibo_pdf_bytes(datos_recibo)

    asunto = f"Comprobante de pago {pago_registro.referencia_recibo}"
    resultado = enviar_whatsapp_directo(
        db,
        destinatario=telefono,
        cuerpo=cuerpo,
        documento=pdf.getvalue(),
        nombre_archivo=f"Comprobante_{pago_registro.referencia_recibo}.pdf",
        asunto=asunto,
    )

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        usuario_id=current_user.get("id"),
        tabla_afectada="envios_mensaje",
        tipo_operacion="envio_comprobante_whatsapp",
        registro_id=pago_registro.id,
        valores_nuevos={"estado": resultado["estado"], "destinatario": telefono},
        descripcion=(
            f"Comprobante {pago_registro.referencia_recibo} enviado por WhatsApp "
            f"al cliente {cliente.nombre} ({resultado['estado']})"
        ),
        resultado="ok" if resultado["estado"] == "enviado" else "fallido",
    )

    # Fallback manual: enlace wa.me para el prestamista si la API no está configurada
    enlace = ""
    if resultado["estado"] != "enviado":
        enlace = f"https://wa.me/{telefono}?text={quote_plus(cuerpo)}"

    return {**resultado, "whatsapp_url": enlace, "destinatario": telefono}


@router.post("/{pago_id}/enviar-whatsapp")
def enviar_comprobante_whatsapp(
    pago_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Envía el comprobante PDF del pago por WhatsApp al cliente.

    Requiere teléfono registrado del cliente. El envío queda en el
    historial de envíos y se puede reenviar cuando se necesite.
    """
    pago_registro = aplicar_filtro_usuario(db.query(Pago), Pago).filter(Pago.id == pago_id).first()
    if not pago_registro:
        raise HTTPException(status_code=404, detail="El pago especificado no existe.")
    if pago_registro.estado_pago == "devuelto":
        raise HTTPException(status_code=400, detail="El pago está devuelto; no se puede enviar su comprobante.")

    return _enviar_comprobante_whatsapp(db, pago_registro, current_user)


@router.get("/{pago_id}/envios-whatsapp")
def historial_envios_comprobante(
    pago_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Historial de envíos de WhatsApp del comprobante (permite reenvíos)."""
    pago_registro = aplicar_filtro_usuario(db.query(Pago), Pago).filter(Pago.id == pago_id).first()
    if not pago_registro:
        raise HTTPException(status_code=404, detail="El pago especificado no existe.")

    from app.core.context import usuario_actual_id, usuario_actual_rol
    from app.models import EnvioMensaje

    uid = usuario_actual_id.get()
    query = db.query(EnvioMensaje).filter(
        EnvioMensaje.asunto == f"Comprobante de pago {pago_registro.referencia_recibo}",
        EnvioMensaje.canal == "whatsapp",
    )
    if uid is not None and usuario_actual_rol.get() != "admin":
        query = query.filter(EnvioMensaje.usuario_id == uid)

    filas = query.order_by(EnvioMensaje.fecha.desc()).limit(20).all()
    return [
        {
            "id": e.id,
            "fecha": str(e.fecha),
            "destinatario": e.destinatario,
            "estado": e.estado,
            "motivo": e.motivo,
        }
        for e in filas
    ]


@router.get("/{pago_id}/comprobante")
def descargar_comprobante_pago(
    pago_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Comprobante PDF de un pago específico, con su desglose de capital, interés y mora (RF-043).
    Si el pago fue devuelto, el documento incluye la marca de anulación y su motivo.
    """
    pago_registro = aplicar_filtro_usuario(db.query(Pago), Pago).filter(Pago.id == pago_id).first()
    if not pago_registro:
        raise HTTPException(status_code=404, detail="El pago especificado no existe.")

    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == pago_registro.cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="La cuota asociada al pago no existe.")

    return _responder_pdf(_construir_datos_recibo(db, cuota, pago_registro))