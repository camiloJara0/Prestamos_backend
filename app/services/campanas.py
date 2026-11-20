"""Campañas de mensajes automáticos programadas por el prestamista (Fase 2).

Cada campaña combina una plantilla, un criterio de destinatarios
(recordatorios: próximos a vencer / vencidos) y un horario
(diario/semanal/mensual). El scheduler registra un job cron por campaña
activa; la ejecución establece el contexto del dueño para respetar el
aislamiento multiusuario (plantillas, credenciales WhatsApp y filtros),
reutiliza `recordatorios.enviar` (dedupe por día incluido) y queda
trazada en `ejecuciones_proceso` con tarea `campana_{id}`.

El agradecimiento inmediato tras registrar un pago sigue siendo un evento
de negocio (`eventos_mensajeria.notificar_pago_confirmado`) y no una campaña.
"""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.context import (
    aplicar_filtro_usuario,
    limpiar_contexto,
    usuario_actual_id,
    usuario_actual_rol,
)
from app.models.models import CampanaMensaje
from app.schemas.campana import CampanaCreate, CampanaUpdate
from app.services import recordatorios as recordatorios_service

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def obtener_campana(db: Session, campana_id: int) -> CampanaMensaje:
    """Campaña propia del usuario (IDOR: aislamiento multiusuario)."""
    campana = (
        aplicar_filtro_usuario(db.query(CampanaMensaje), CampanaMensaje)
        .filter(CampanaMensaje.id == campana_id)
        .first()
    )
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    return campana


def listar_campanas(db: Session) -> list[CampanaMensaje]:
    return (
        aplicar_filtro_usuario(db.query(CampanaMensaje), CampanaMensaje)
        .order_by(CampanaMensaje.estado.desc(), CampanaMensaje.nombre)
        .all()
    )


def _validar_regimen(frecuencia: str, dia_semana, dia_mes) -> None:
    if frecuencia == "semanal" and dia_semana is None:
        raise HTTPException(
            status_code=400,
            detail="La frecuencia semanal requiere el día de la semana",
        )
    if frecuencia == "mensual" and dia_mes is None:
        raise HTTPException(
            status_code=400,
            detail="La frecuencia mensual requiere el día del mes (1-28)",
        )


def _validar_plantilla(db: Session, plantilla_id: int) -> None:
    from app.services.plantillas import get_plantilla

    plantilla = get_plantilla(db, plantilla_id)
    if not plantilla.activa:
        raise HTTPException(status_code=400, detail="La plantilla está inactiva")


def _hora(db_ignora=None, texto: str | None = None):
    try:
        return datetime.strptime(texto or "", "%H:%M").time()
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="La hora debe tener formato HH:MM")


def _programar(campana: CampanaMensaje | None, campana_id: int | None = None) -> None:
    """Registra/retira el job del scheduler (import perezoso: evita ciclo)."""
    from app.services.scheduler import programar_campana

    objetivo = campana
    if objetivo is None and campana_id is not None:
        objetivo = (
            db.query(CampanaMensaje).filter(CampanaMensaje.id == campana_id).first()
        )
    if objetivo is None:
        programar_campana(campana_id=campana_id, activo=False)
        return
    programar_campana(
        campana_id=objetivo.id,
        hora=objetivo.hora_ejecucion,
        frecuencia=objetivo.frecuencia,
        dia_semana=objetivo.dia_semana,
        dia_mes=objetivo.dia_mes,
        activo=objetivo.estado == "activo",
    )


def crear_campana(db: Session, datos: CampanaCreate) -> CampanaMensaje:
    _validar_regimen(datos.frecuencia, datos.dia_semana, datos.dia_mes)
    _validar_plantilla(db, datos.plantilla_id)
    duplicada = (
        aplicar_filtro_usuario(db.query(CampanaMensaje), CampanaMensaje)
        .filter(CampanaMensaje.nombre == datos.nombre)
        .first()
    )
    if duplicada:
        raise HTTPException(status_code=400, detail="Ya existe una campaña con ese nombre")
    campana = CampanaMensaje(
        **datos.model_dump(exclude={"hora_ejecucion"}),
        hora_ejecucion=_hora(texto=datos.hora_ejecucion),
        usuario_id=usuario_actual_id.get(),
    )
    db.add(campana)
    db.commit()
    db.refresh(campana)
    _programar(campana)
    return campana


def actualizar_campana(db: Session, campana_id: int, datos: CampanaUpdate) -> CampanaMensaje:
    campana = obtener_campana(db, campana_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "hora_ejecucion" in cambios and cambios["hora_ejecucion"]:
        cambios["hora_ejecucion"] = _hora(texto=cambios.pop("hora_ejecucion"))
    if "plantilla_id" in cambios and cambios["plantilla_id"] is not None:
        _validar_plantilla(db, cambios["plantilla_id"])
    for campo, valor in cambios.items():
        setattr(campana, campo, valor)
    _validar_regimen(campana.frecuencia, campana.dia_semana, campana.dia_mes)
    db.commit()
    db.refresh(campana)
    _programar(campana)
    return campana


def eliminar_campana(db: Session, campana_id: int) -> None:
    campana = obtener_campana(db, campana_id)
    db.delete(campana)
    db.commit()
    _programar(None, campana_id=campana_id)


def ejecutar_campana(db: Session, campana: CampanaMensaje) -> dict:
    """Ejecución manual (request autenticado: el contexto ya está seteado)."""
    conteo = recordatorios_service.enviar(
        db, campana.plantilla_id, campana.filtro_tipo, campana.filtro_dias
    )
    campana.ultima_ejecucion = datetime.utcnow()
    db.commit()
    return conteo


def ejecutar_campana_job(campana_id: int, db=None) -> str:
    """Punto de entrada del job APScheduler (y de la ejecución manual trazada).

    Establece el contexto del dueño de la campaña y lo limpia al terminar
    (los hilos del executor del scheduler se reutilizan entre jobs).
    Si no se inyecta `db` abre una sesión propia. Los fallos los captura
    el historial de ejecuciones (`_ejecutar_y_registrar`).
    """
    propia = db is None
    if propia:
        from app.db.database import SessionLocal

        db = SessionLocal()
    try:
        campana = db.query(CampanaMensaje).filter(CampanaMensaje.id == campana_id).first()
        if not campana:
            return "Campaña no encontrada"
        usuario_actual_id.set(campana.usuario_id)
        usuario_actual_rol.set("prestamista")
        if campana.estado != "activo":
            return "Campaña inactiva"
        conteo = recordatorios_service.enviar(
            db, campana.plantilla_id, campana.filtro_tipo, campana.filtro_dias
        )
        campana.ultima_ejecucion = datetime.utcnow()
        db.commit()
        return (
            f"{conteo.get('enviados', 0)} enviados, {conteo.get('omitidos', 0)} omitidos, "
            f"{conteo.get('fallidos', 0)} fallidos de {conteo.get('destinatarios', 0)} destinatarios"
        )
    finally:
        limpiar_contexto()
        if propia:
            db.close()
