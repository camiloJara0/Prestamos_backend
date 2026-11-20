"""Webhook de WhatsApp Business API (Meta) — Fase 2.

GET  /webhook/whatsapp → verificación de Meta (hub.challenge) usando la
     variable de entorno WHATSAPP_WEBHOOK_VERIFY_TOKEN.
POST /webhook/whatsapp → eventos de Meta:
     - statuses[]: sent / delivered / read / failed → actualiza la fila de
       EnvioMensaje por `whatsapp_message_id` (avance de estado monotónico).
     - messages[]: respuestas entrantes del cliente → fila con estado
       'recibido' (trazabilidad de la conversación).

Trazabilidad completa por mensaje: fecha de envío, estado, plantilla,
destinatario, respuesta del proveedor y respuesta recibida del cliente.
Si WHATSAPP_APP_SECRET está definido se valida la firma X-Hub-Signature-256.
Hacia Meta nunca se lanza un error en el POST (siempre 200 con ok/false).
"""

import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response

from app.db.database import SessionLocal
from app.models.models import EnvioMensaje

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook WhatsApp"])

# Estados de Meta → estados de EnvioMensaje (sin CHECK en la columna).
MAPA_ESTADOS = {
    "sent": "enviado",
    "delivered": "entregado",
    "read": "leido",
    "failed": "fallido",
}
# Avance monotónico de estados (evita retroceder leido→entregado).
ORDEN_ESTADOS = {"enviado": 1, "entregado": 2, "leido": 3}


@router.get("/whatsapp")
def verificar(request: Request):
    """Handshake de verificación de Meta (WhatsApp → Configuration → Webhook)."""
    params = request.query_params
    modo = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    esperado = (os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or "").strip()

    if (
        modo == "subscribe"
        and token
        and esperado
        and hmac.compare_digest(token.strip(), esperado)
    ):
        return Response(content=challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verificación de webhook inválida")


@router.post("/whatsapp")
async def recibir_eventos(request: Request):
    """Recibe los eventos de Meta y actualiza la trazabilidad de envíos."""
    payload_raw = await request.body()

    secreto = (os.getenv("WHATSAPP_APP_SECRET") or "").strip()
    if secreto:
        firma = request.headers.get("X-Hub-Signature-256", "")
        esperada = "sha256=" + hmac.new(
            secreto.encode(), payload_raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(firma, esperada):
            return {"ok": False}

    try:
        payload = json.loads(payload_raw or b"{}")
    except Exception:  # noqa: BLE001 - nunca lanzar hacia Meta
        return {"ok": True}

    _procesar(payload)
    return {"ok": True}


def _procesar(payload: dict, db=None) -> None:
    """Procesa el payload; si no se inyecta `db` abre una sesión propia."""
    propia = db is None
    if propia:
        db = SessionLocal()
    try:
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for estado in value.get("statuses") or []:
                    _registrar_estado(db, estado)
                for mensaje in value.get("messages") or []:
                    _registrar_recibido(db, mensaje)
    except Exception:  # noqa: BLE001 - el webhook nunca rompe el servicio
        logger.exception("[WEBHOOK] Error procesando evento de WhatsApp")
    finally:
        if propia:
            db.close()


def _registrar_estado(db, evento: dict) -> None:
    """Actualiza la fila EnvioMensaje según el estado reportado por Meta."""
    message_id = evento.get("id")
    nuevo = MAPA_ESTADOS.get(str(evento.get("status") or ""))
    if not message_id or not nuevo:
        return

    fila = (
        db.query(EnvioMensaje)
        .filter(EnvioMensaje.whatsapp_message_id == message_id)
        .first()
    )
    if not fila:
        return

    if nuevo == "fallido":
        errores = evento.get("errors") or []
        fila.estado = "fallido"
        fila.error_detalle = json.dumps(errores, ensure_ascii=False)[:4000]
    else:
        actual = ORDEN_ESTADOS.get(fila.estado, 0)
        destino = ORDEN_ESTADOS.get(nuevo, 99)
        if destino > actual:
            fila.estado = nuevo

    fila.respuesta_proveedor = json.dumps(evento, ensure_ascii=False)[:2000]
    db.commit()


def _registrar_recibido(db, mensaje: dict) -> None:
    """Registra la respuesta entrante del cliente (estado 'recibido')."""
    message_id = mensaje.get("id")
    if message_id:
        existente = (
            db.query(EnvioMensaje)
            .filter(EnvioMensaje.whatsapp_message_id == message_id)
            .first()
        )
        if existente:
            return

    tipo = str(mensaje.get("type") or "text")
    contenido = mensaje.get(tipo)
    texto = ""
    if isinstance(contenido, dict):
        texto = str(contenido.get("body") or "")

    db.add(
        EnvioMensaje(
            canal="whatsapp",
            destinatario=str(mensaje.get("from") or ""),
            asunto="Respuesta de cliente",
            cuerpo=texto,
            estado="recibido",
            motivo="Mensaje entrante vía webhook de WhatsApp",
            plantilla_id=None,
            whatsapp_message_id=message_id,
            respuesta_proveedor=json.dumps(mensaje, ensure_ascii=False)[:2000],
        )
    )
    db.commit()
