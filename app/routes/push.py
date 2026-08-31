from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

# Cambiado a 'dependencies' (en inglés)
from app.dependencies.auth import get_current_user, get_db

from app.schemas.push import (
    PushNotificationSend,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
)
from app.services.push import enviar_notificacion_push, suscribir_usuario

router = APIRouter(prefix="/push", tags=["Web Push"])


@router.post(
    "/subscribe",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_suscripcion_push(
    datos: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Registra la suscripción Web Push desde el navegador del usuario."""
    usuario_id = int(current_user.get("sub") or current_user.get("id"))
    return suscribir_usuario(
        db=db, usuario_id=usuario_id, subscription_data=datos
    )


@router.post("/test")
def probar_notificacion_push(
    datos: PushNotificationSend,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Envía una notificación push de prueba al usuario autenticado."""
    usuario_id = int(current_user.get("sub") or current_user.get("id"))
    resultado = enviar_notificacion_push(
        db=db,
        usuario_id=usuario_id,
        titulo=datos.titulo,
        mensaje=datos.mensaje,
        url=datos.url,
    )
    return {
        "ok": True,
        "mensaje": f"Notificación enviada a {resultado['enviados']} de {resultado['total_dispositivos']} dispositivos.",
    }