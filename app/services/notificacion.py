from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.models import Usuario, PushSubscription
from app.schemas.notificacion import PushSubscriptionCreate, PushNotificationPayload

def guardar_suscripcion(db: Session, email_usuario: str, subscription: PushSubscriptionCreate) -> PushSubscription:
    """Registra o actualiza la suscripción Push de un usuario."""
    usuario = db.query(Usuario).filter(Usuario.email == email_usuario).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    sub_existente = db.query(PushSubscription).filter(PushSubscription.endpoint == subscription.endpoint).first()

    if sub_existente:
        sub_existente.usuario_id = usuario.id
        sub_existente.p256dh = subscription.p256dh
        sub_existente.auth = subscription.auth
        db_sub = sub_existente
    else:
        db_sub = PushSubscription(
            usuario_id=usuario.id,
            endpoint=subscription.endpoint,
            p256dh=subscription.p256dh,
            auth=subscription.auth
        )
        db.add(db_sub)

    db.commit()
    db.refresh(db_sub)
    return db_sub


def eliminar_suscripcion(db: Session, endpoint: str) -> bool:
    """Elimina una suscripción Push mediante su endpoint."""
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if sub:
        db.delete(sub)
        db.commit()
        return True
    return False