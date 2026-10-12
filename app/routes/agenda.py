"""Endpoints de la agenda operativa (RF-080)."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user, get_db
from app.schemas.agenda import (
    EventoAgendaCreate,
    EventoAgendaOut,
    EventoAgendaUpdate,
    GeneracionEventosOut,
    ResumenAgendaOut,
    TipoCitaCreate,
    TipoCitaOut,
    TipoCitaUpdate,
)
from app.services import agenda as agenda_service

router = APIRouter(prefix="/agenda", tags=["Agenda"])
router_prestamos = APIRouter(prefix="/prestamos", tags=["Agenda"])


@router.get("/eventos", response_model=list[EventoAgendaOut])
def listar_eventos(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    tipo: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """CA-R5-1: eventos con filtros por rango de fecha, tipo y estado."""
    return agenda_service.get_eventos(
        db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, tipo=tipo, estado=estado
    )


@router.post("/eventos", response_model=EventoAgendaOut, status_code=201)
def crear_evento(
    datos: EventoAgendaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return agenda_service.crear_evento(db, datos)


@router.put("/eventos/{evento_id}", response_model=EventoAgendaOut)
def actualizar_evento(
    evento_id: int,
    datos: EventoAgendaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return agenda_service.actualizar_evento(db, evento_id, datos)


@router.delete("/eventos/{evento_id}")
def eliminar_evento(
    evento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    agenda_service.eliminar_evento(db, evento_id)
    return {"message": "Evento eliminado"}


@router.patch("/eventos/{evento_id}/completar", response_model=EventoAgendaOut)
def completar_evento(
    evento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """CA-R5-6: marca el evento como completado sin eliminarlo."""
    return agenda_service.cambiar_estado_evento(db, evento_id, "completado")


@router.patch("/eventos/{evento_id}/cancelar", response_model=EventoAgendaOut)
def cancelar_evento(
    evento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """CA-R5-6: marca el evento como cancelado sin eliminarlo."""
    return agenda_service.cambiar_estado_evento(db, evento_id, "cancelado")


@router.get("/tipos-cita", response_model=list[TipoCitaOut])
def listar_tipos_cita(
    estado: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return agenda_service.get_tipos_cita(db, estado=estado)


@router.post("/tipos-cita", response_model=TipoCitaOut, status_code=201)
def crear_tipo_cita(
    datos: TipoCitaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return agenda_service.crear_tipo_cita(db, datos)


@router.put("/tipos-cita/{tipo_cita_id}", response_model=TipoCitaOut)
def actualizar_tipo_cita(
    tipo_cita_id: int,
    datos: TipoCitaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return agenda_service.actualizar_tipo_cita(db, tipo_cita_id, datos)


@router.delete("/tipos-cita/{tipo_cita_id}")
def eliminar_tipo_cita(
    tipo_cita_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    agenda_service.eliminar_tipo_cita(db, tipo_cita_id)
    return {"message": "Tipo de cita eliminado"}


@router.get("/resumen", response_model=ResumenAgendaOut)
def resumen(
    fecha: Optional[date] = Query(None),
    mes: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """CA-R5-5: eventos del día y conteo del mes."""
    return agenda_service.resumen_agenda(db, fecha=fecha, mes=mes)


@router_prestamos.post("/{prestamo_id}/generar-eventos-agenda", response_model=GeneracionEventosOut)
def generar_eventos_agenda(
    prestamo_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """CA-R5-4: generación idempotente de eventos de vencimiento de cuotas."""
    return agenda_service.generar_eventos_cuota(db, prestamo_id)
