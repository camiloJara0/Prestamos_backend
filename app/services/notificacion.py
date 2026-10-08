from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.models import Notificacion, Usuario, PushSubscription
from app.schemas.notificacion import PushSubscriptionCreate, PushNotificationPayload
from app.utils.pagination import paginate

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


def registrar_notificacion(
    db: Session,
    usuario_id: int,
    titulo: str,
    mensaje: str,
    url: str | None = None,
    tipo: str = "solicitud",
) -> Notificacion:
    """Registra el aviso interno e intenta enviar push (RF-023).

    Si el navegador no tiene suscripción push activa, la notificación queda
    solo en este registro interno.
    """
    push_enviado = False
    try:
        from app.services.push import enviar_notificacion_push

        resultado = enviar_notificacion_push(
            db=db,
            usuario_id=usuario_id,
            titulo=titulo,
            mensaje=mensaje,
            url=url,
        )
        push_enviado = bool(resultado.get("enviados"))
    except Exception:  # noqa: BLE001 - el fallo de push no debe romper el evento
        push_enviado = False

    notificacion = Notificacion(
        usuario_id=usuario_id,
        titulo=titulo,
        mensaje=mensaje,
        url=url,
        tipo=tipo,
        push_enviado=push_enviado,
    )
    db.add(notificacion)
    db.commit()
    db.refresh(notificacion)
    return notificacion


def get_notificaciones(
    db: Session,
    usuario_id: int,
    page: int = 1,
    limit: int = 20,
    solo_no_leidas: bool = False,
):
    query = (
        db.query(Notificacion)
        .filter(Notificacion.usuario_id == usuario_id)
        .order_by(Notificacion.fecha.desc())
    )
    if solo_no_leidas:
        query = query.filter(Notificacion.leida.is_(False))
    return paginate(query, page=page, limit=limit)


def marcar_leida(db: Session, notificacion_id: int, usuario_id: int) -> Notificacion:
    notificacion = (
        db.query(Notificacion)
        .filter(Notificacion.id == notificacion_id, Notificacion.usuario_id == usuario_id)
        .first()
    )
    if not notificacion:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notificacion.leida = True
    db.commit()
    db.refresh(notificacion)
    return notificacion


def contar_no_leidas(db: Session, usuario_id: int) -> int:
    return (
        db.query(Notificacion)
        .filter(Notificacion.usuario_id == usuario_id, Notificacion.leida.is_(False))
        .count()
    )