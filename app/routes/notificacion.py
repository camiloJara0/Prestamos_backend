from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.schemas.notificacion import PushSubscriptionCreate, PushSubscriptionOut
from app.dependencies.auth import get_current_user
from app.services import notificacion as notificacion_service

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
    """Registra o actualiza la suscripción Push delegan a la capa de servicios."""
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