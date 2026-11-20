"""Campañas de mensajes automáticos: CRUD + ejecución manual (Fase 2)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies.auth import get_db, require_rol
from app.schemas.campana import (
    CampanaCreate,
    CampanaEjecucionOut,
    CampanaOut,
    CampanaUpdate,
)
from app.services import campanas as service
from app.services.scheduler import _ejecutar_y_registrar

from functools import partial

router = APIRouter(prefix="/campanas", tags=["Campañas"])


def _out(campana) -> dict:
    plantilla = getattr(campana, "plantilla", None)
    return {
        "id": campana.id,
        "nombre": campana.nombre,
        "plantilla_id": campana.plantilla_id,
        "plantilla_nombre": plantilla.nombre if plantilla else None,
        "hora_ejecucion": campana.hora_ejecucion.strftime("%H:%M"),
        "frecuencia": campana.frecuencia,
        "dia_semana": campana.dia_semana,
        "dia_mes": campana.dia_mes,
        "filtro_tipo": campana.filtro_tipo,
        "filtro_dias": campana.filtro_dias,
        "estado": campana.estado,
        "ultima_ejecucion": campana.ultima_ejecucion.isoformat() if campana.ultima_ejecucion else None,
    }


@router.get("/", response_model=list[CampanaOut])
def listar(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Campañas del usuario autenticado (admin ve todas)."""
    return [_out(c) for c in service.listar_campanas(db)]


@router.post("/", response_model=CampanaOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: CampanaCreate,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Crea la campaña y registra su job cron si queda activa."""
    return _out(service.crear_campana(db, datos))


@router.get("/{campana_id}", response_model=CampanaOut)
def obtener(
    campana_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    return _out(service.obtener_campana(db, campana_id))


@router.put("/{campana_id}", response_model=CampanaOut)
def actualizar(
    campana_id: int,
    datos: CampanaUpdate,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Actualiza y reprograma el job (o lo retira si queda inactiva)."""
    return _out(service.actualizar_campana(db, campana_id, datos))


@router.delete("/{campana_id}")
def eliminar(
    campana_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    service.eliminar_campana(db, campana_id)
    return {"message": "Campaña eliminada."}


@router.post("/{campana_id}/ejecutar", response_model=CampanaEjecucionOut)
def ejecutar(
    campana_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Ejecución manual trazada en `ejecuciones_proceso` (origen manual)."""
    campana = service.obtener_campana(db, campana_id)
    _ejecutar_y_registrar(
        f"campana_{campana.id}",
        "manual",
        partial(service.ejecutar_campana_job, campana.id),
        solicitado_por=campana.usuario_id,
    )
    db.refresh(campana)
    return {
        "message": "Campaña ejecutada",
        "ultima_ejecucion": campana.ultima_ejecucion.isoformat() if campana.ultima_ejecucion else None,
    }
