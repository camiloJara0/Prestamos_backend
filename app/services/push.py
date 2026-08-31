# app/services/push.py
import json
from datetime import date, timedelta
from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import Cliente, Prestamo, PrestamoCuota, PushSubscription, Usuario


def suscribir_usuario(
    db: Session, usuario_id: int, subscription_data
) -> PushSubscription:
    """Guarda o actualiza la suscripción push de un dispositivo/navegador."""
    endpoint = subscription_data.endpoint
    p256dh = subscription_data.keys.p256dh
    auth = subscription_data.keys.auth

    sub = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == endpoint)
        .first()
    )

    if sub:
        sub.usuario_id = usuario_id
        sub.p256dh = p256dh
        sub.auth = auth
    else:
        sub = PushSubscription(
            usuario_id=usuario_id, endpoint=endpoint, p256dh=p256dh, auth=auth
        )
        db.add(sub)

    db.commit()
    db.refresh(sub)
    return sub


def enviar_notificacion_push(
    db: Session, usuario_id: int, titulo: str, mensaje: str, url: str = "/"
):
    """Envía una notificación push a todos los dispositivos registrados del usuario."""
    suscripciones = (
        db.query(PushSubscription)
        .filter(PushSubscription.usuario_id == usuario_id)
        .all()
    )

    payload = json.dumps({"title": titulo, "body": mensaje, "data": {"url": url}})

    enviados = 0
    for sub in suscripciones:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIM_EMAIL},
            )
            enviados += 1
        except WebPushException as ex:
            # Si el navegador desrevocó o eliminó el permiso (HTTP 410 / 404), borramos la suscripción
            if ex.response and ex.response.status_code in [404, 410]:
                db.delete(sub)
                db.commit()

    return {"enviados": enviados, "total_dispositivos": len(suscripciones)}


def procesar_recordatorios_vencimiento_push(db: Session):
    """
    Busca cuotas que vencen en 3 días y en 1 día, y envía notificaciones push
    a los usuarios administradores activos del sistema.
    """
    hoy = date.today()
    rangos = [
        (hoy + timedelta(days=3), "en 3 días"),
        (hoy + timedelta(days=1), "mañana"),
    ]

    admins = db.query(Usuario).filter(Usuario.rol == "admin", Usuario.estado == "activo").all()
    if not admins:
        return 0

    total_enviados = 0

    for fecha_target, texto_tiempo in rangos:
        cuotas = (
            db.query(PrestamoCuota)
            .filter(
                PrestamoCuota.estado == "pendiente",
                PrestamoCuota.fecha_vencimiento == fecha_target,
            )
            .all()
        )

        for cuota in cuotas:
            prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
            cliente = (
                db.query(Cliente).filter(Cliente.id == prestamo.cliente_id).first()
                if prestamo
                else None
            )

            nombre_cliente = cliente.nombre if cliente else "Cliente"
            mensaje = f"La cuota #{cuota.numero_cuota} de {nombre_cliente} por ${cuota.valor_cuota:,.0f} vence {texto_tiempo}."

            for admin in admins:
                res = enviar_notificacion_push(
                    db=db,
                    usuario_id=admin.id,
                    titulo="Recordatorio de Vencimiento",
                    mensaje=mensaje,
                    url=f"/prestamos/{cuota.prestamo_id}" if prestamo else "/",
                )
                total_enviados += res.get("enviados", 0)

    return total_enviados