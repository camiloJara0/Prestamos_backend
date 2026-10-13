from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from typing import List

from app.db.database import SessionLocal
from app.schemas.notificacion import (
    NotificacionCountOut,
    NotificacionOut,
    PushSubscriptionCreate,
    PushSubscriptionOut,
    RecordatorioCuotaResponse,
)
from app.schemas.pagination import PaginatedResponse
from app.dependencies.auth import get_current_user, get_usuario_id
from app.services import notificacion as notificacion_service
from app.services import recordatorios as recordatorio_service

router = APIRouter(prefix="/notificacion", tags=["Notificaciones"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/subscribe", response_model=PushSubscriptionOut, status_code=status.HTTP_201_CREATED)
def suscribir_push(
    subscription: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Registra o actualiza la suscripción Push delegando a la capa de servicios."""
    return notificacion_service.guardar_suscripcion(
        db=db, 
        email_usuario=current_user["sub"], 
        subscription=subscription
    )


@router.post("/unsubscribe")
def desuscribir_push(
    subscription: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Elimina la suscripción Push especificada por su endpoint."""
    notificacion_service.eliminar_suscripcion(db=db, endpoint=subscription.endpoint)
    return {"message": "Suscripción eliminada correctamente."}


@router.get("/", response_model=PaginatedResponse[NotificacionOut])
def bandeja_notificaciones(
    page: int = 1,
    limit: int = 20,
    solo_no_leidas: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RF-023: registro interno de notificaciones del usuario autenticado."""
    usuario_id = get_usuario_id(current_user)
    return notificacion_service.get_notificaciones(
        db, usuario_id=usuario_id, page=page, limit=limit, solo_no_leidas=solo_no_leidas
    )


@router.get("/no-leidas", response_model=NotificacionCountOut)
def contar_no_leidas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    usuario_id = get_usuario_id(current_user)
    return NotificacionCountOut(no_leidas=notificacion_service.contar_no_leidas(db, usuario_id))


@router.post("/{notificacion_id}/leer", response_model=NotificacionOut)
def marcar_como_leida(
    notificacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    usuario_id = get_usuario_id(current_user)
    return notificacion_service.marcar_leida(db, notificacion_id, usuario_id)


@router.get("/proximos-vencimientos", response_model=List[RecordatorioCuotaResponse])
def obtener_proximos_vencimientos(
    dias_anticipacion: int = Query(default=3, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene las cuotas pendientes que vencen en los próximos N días.
    Genera la plantilla con el formato Credifast y el enlace directo a WhatsApp.
    La consulta y el formato viven en app.services.recordatorios (compartido con
    los recordatorios masivos).
    """
    return recordatorio_service.proximos_vencimientos(db, dias_anticipacion)