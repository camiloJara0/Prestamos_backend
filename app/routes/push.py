from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

# Cambiado a 'dependencies' (en inglés)
from app.dependencies.auth import get_current_user, get_db, get_usuario_id

from app.core.config import settings
from app.schemas.push import (
    PushNotificationSend,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
)
from app.services.push import enviar_notificacion_push, suscribir_usuario
from app.services.notificacion import eliminar_suscripcion

router = APIRouter(prefix="/push", tags=["Web Push"])


@router.get("/vapid-public-key")
def obtener_llave_publica_vapid():
    """RF-060: entrega la llave pública VAPID al navegador para suscribirse."""
    return {"public_key": settings.VAPID_PUBLIC_KEY}


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
    usuario_id = get_usuario_id(current_user)
    return suscribir_usuario(
        db=db, usuario_id=usuario_id, subscription_data=datos
    )


@router.delete("/subscribe")
def eliminar_suscripcion_push(
    datos: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RF-060: elimina la suscripción push del navegador."""
    eliminar_suscripcion(db=db, endpoint=datos.endpoint)
    return {"message": "Suscripción eliminada correctamente."}


@router.post("/test")
def probar_notificacion_push(
    datos: PushNotificationSend,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Envía una notificación push de prueba al usuario autenticado."""
    usuario_id = get_usuario_id(current_user)
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