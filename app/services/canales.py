"""Adaptador de canales de mensajería (RF-061 correo, RF-062 SMS/mensajería).

Variables de entorno:
  SMS_PROVIDER, WHATSAPP_PROVIDER: 'ninguno' (default) | 'piloto' | 'externo'
  SMS_HORA_INICIO, SMS_HORA_FIN: ventana horaria de envío (default 08:00 - 20:00)

Sin proveedor, sin consentimiento o fuera de la ventana horaria el envío se
omite y queda registrado (RF-062). Un fallo nunca revierte el evento de
negocio que disparó el mensaje (RF-061).
"""

import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.models.models import PlantillaMensaje
from app.services.plantillas import componer_mensaje, registrar_envio

logger = logging.getLogger(__name__)


def _id_plantilla(plantilla) -> int | None:
    """Id de la plantilla sea un modelo de BD o un dict de PLANTILLAS_POR_DEFECTO."""
    if not plantilla:
        return None
    if isinstance(plantilla, dict):
        return plantilla.get("id")
    return plantilla.id


def _ventana_permitida() -> tuple[bool, str]:
    inicio = int(os.getenv("SMS_HORA_INICIO", "8"))
    fin = int(os.getenv("SMS_HORA_FIN", "20"))
    hora = datetime.now().hour
    if inicio <= hora < fin:
        return True, ""
    return False, f"Fuera de la ventana de envío permitida ({inicio:02d}:00-{fin:02d}:00)"


def _resolver_proveedor(canal: str) -> str:
    variable = "SMS_PROVIDER" if canal == "sms" else "WHATSAPP_PROVIDER"
    return (os.getenv(variable) or "ninguno").lower()


def enviar_por_canal(
    db: Session,
    canal: str,
    destinatario: str,
    clave: str,
    contexto: dict,
    dedupe_clave: str | None = None,
    cliente_id: int | None = None,
) -> dict:
    """Compone el mensaje desde la plantilla y lo envía por el canal indicado.

    Siempre registra el resultado en envios_mensaje (con trazabilidad
    del cliente). Nunca lanza excepción.
    """
    def _plantilla_id_por_clave() -> int | None:
        fila = db.query(PlantillaMensaje).filter(
            PlantillaMensaje.clave == clave, PlantillaMensaje.canal == canal
        ).first()
        return fila.id if fila else None

    try:
        asunto, cuerpo, plantilla = componer_mensaje(db, clave, canal, contexto)
    except HTTPException as exc:
        # RF-079/CA-R4-5: plantilla desactivada → omitido registrado, sin error
        motivo = str(exc.detail)
        estado = "omitido" if "inactiva" in motivo else "fallido"
        registrar_envio(db, canal, destinatario, None, "", estado, motivo,
                        _plantilla_id_por_clave(), dedupe_clave=dedupe_clave,
                        cliente_id=cliente_id)
        return {"estado": estado, "motivo": motivo}
    except Exception as exc:  # noqa: BLE001 - plantilla rota no debe tumbar el evento
        logger.error("[CANALES] Error componiendo %s/%s: %s", canal, clave, exc)
        registrar_envio(db, canal, destinatario, None, "", "fallido", str(exc),
                        _plantilla_id_por_clave(), dedupe_clave=dedupe_clave,
                        cliente_id=cliente_id, error_detalle=str(exc)[:4000])
        return {"estado": "fallido", "motivo": str(exc)}

    if not destinatario:
        registro = registrar_envio(
            db, canal, destinatario or "(sin destinatario)", asunto, cuerpo,
            "omitido", "Sin destinatario registrado", _id_plantilla(plantilla),
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
        )
        return {"estado": "omitido", "motivo": registro.motivo}

    if canal == "email":
        from app.services.email import enviar_correo

        ok = enviar_correo(destinatario, asunto, cuerpo)
        estado = "enviado" if ok else "fallido"
        motivo = None if ok else "Servidor de correo no disponible o error de envío"
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, estado, motivo,
            _id_plantilla(plantilla),
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
        )
        return {"estado": estado, "motivo": motivo}

    proveedor = _resolver_proveedor(canal)
    if proveedor == "ninguno":
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "omitido",
            f"Proveedor de {canal} no configurado", _id_plantilla(plantilla),
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
        )
        return {"estado": "omitido", "motivo": registro.motivo}

    permitido, motivo_ventana = _ventana_permitida()
    if not permitido:
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "omitido", motivo_ventana,
            _id_plantilla(plantilla),
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
        )
        return {"estado": "omitido", "motivo": registro.motivo}

    if proveedor == "piloto":
        logger.info("[CANALES] (%s piloto) a %s: %s", canal, destinatario, cuerpo[:120])
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "enviado",
            "Envío simulado por proveedor piloto", _id_plantilla(plantilla),
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
        )
        return {"estado": "enviado", "motivo": registro.motivo}

    try:
        _enviar_externo(canal, destinatario, asunto, cuerpo)
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "enviado", None,
            _id_plantilla(plantilla),
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
        )
        return {"estado": "enviado", "motivo": None}
    except Exception as exc:  # noqa: BLE001 - el fallo no revierte el evento
        logger.error("[CANALES] Error enviando %s a %s: %s", canal, destinatario, exc)
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "fallido", str(exc)[:255],
            _id_plantilla(plantilla),
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
            error_detalle=str(exc)[:4000],
        )
        return {"estado": "fallido", "motivo": registro.motivo}


def _enviar_externo(canal: str, destinatario: str, asunto: str, cuerpo: str) -> None:
    """Punto de conexión del proveedor externo contratado.

    WhatsApp usa la WhatsApp Cloud API (Meta) con WHATSAPP_ACCESS_TOKEN y
    WHATSAPP_PHONE_NUMBER_ID. SMS queda pendiente de contrato (Integración
    planeada en el módulo de mensajería masiva).
    """
    if canal == "whatsapp":
        _enviar_whatsapp_cloud(destinatario, cuerpo, documento=None, nombre_archivo=None)
        return
    raise NotImplementedError(
        f"Proveedor externo de {canal} sin integrar. Configure un adaptador piloto."
    )


# ---------------------------------------------------------------------------
# WhatsApp Cloud API (Meta) — envío real con cuenta Business
# ---------------------------------------------------------------------------
_API_BASE = "https://graph.facebook.com/v21.0"


def _credenciales_whatsapp(credenciales: dict | None = None) -> tuple[str, str]:
    """Token y Phone Number ID: credenciales del prestamista (Opción 2) o
    las corporativas del entorno (Opción 1)."""
    if credenciales:
        token = credenciales.get("access_token")
        phone_id = credenciales.get("phone_number_id")
        if token and phone_id:
            return token, str(phone_id)
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_id:
        raise RuntimeError(
            "WhatsApp Cloud API no configurada: defina WHATSAPP_ACCESS_TOKEN y "
            "WHATSAPP_PHONE_NUMBER_ID (o credenciales propias del prestamista)."
        )
    return token, phone_id


def _numero_whatsapp(destinatario: str) -> str:
    digitos = "".join(c for c in (destinatario or "") if c.isdigit())
    if not digitos:
        raise ValueError("El destinatario no tiene número de teléfono válido")
    return digitos


def _enviar_whatsapp_cloud(
    destinatario: str,
    cuerpo: str,
    documento: bytes | None = None,
    nombre_archivo: str | None = None,
    credenciales: dict | None = None,
) -> dict:
    """Envía texto y opcionalmente un documento (PDF) por WhatsApp Cloud API.

    Devuelve el id de mensaje de WhatsApp. Lanza excepción en fallo
    (el llamador registra el estado 'fallido').
    """
    import httpx

    token, phone_id = _credenciales_whatsapp(credenciales)
    destino = _numero_whatsapp(destinatario)
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30) as cliente:
        if documento:
            respuesta = cliente.post(
                f"{_API_BASE}/{phone_id}/media",
                headers=headers,
                files={"file": (nombre_archivo or "documento.pdf", documento, "application/pdf")},
                data={"messaging_product": "whatsapp", "type": "document"},
            )
            respuesta.raise_for_status()
            media_id = respuesta.json()["id"]

            payload = {
                "messaging_product": "whatsapp",
                "to": destino,
                "type": "document",
                "document": {"id": media_id, "filename": nombre_archivo or "documento.pdf"},
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": destino,
                "type": "text",
                "text": {"body": cuerpo or ""},
            }

        respuesta = cliente.post(
            f"{_API_BASE}/{phone_id}/messages",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        mensajes = datos.get("messages") or [{}]
        return {"whatsapp_message_id": mensajes[0].get("id")}


def enviar_whatsapp_directo(
    db: Session,
    destinatario: str,
    cuerpo: str,
    documento: bytes | None = None,
    nombre_archivo: str | None = None,
    asunto: str | None = None,
    plantilla_id: int | None = None,
    dedupe_clave: str | None = None,
    credenciales: dict | None = None,
    usuario_id: int | None = None,
    cliente_id: int | None = None,
) -> dict:
    """Envía un mensaje libre (p. ej. comprobante con PDF adjunto) por WhatsApp.

    Sin plantilla, sin ventana horaria (el prestamista lo dispara
    manualmente). Siempre registra el resultado en envios_mensaje con la
    trazabilidad completa (respuesta y error del proveedor).

    Modos soportados: si `credenciales` no viene y hay `usuario_id`, se
    intenta usar las credenciales propias del prestamista (Modo 2); si no
    existen, se usan las corporativas del entorno (Modo 1).
    """
    from app.services.whatsapp import credenciales_de_usuario

    if not credenciales and usuario_id is not None:
        credenciales = credenciales_de_usuario(db, usuario_id)
        modo = "propio" if credenciales else "corporativo"
    else:
        modo = "propio" if credenciales else "corporativo"

    proveedor = _resolver_proveedor("whatsapp")
    if not destinatario:
        registrar_envio(db, "whatsapp", "(sin destinatario)", asunto, cuerpo,
                        "omitido", "Cliente sin teléfono registrado",
                        plantilla_id, dedupe_clave=dedupe_clave,
                        usuario_id=usuario_id, cliente_id=cliente_id)
        return {"estado": "omitido", "motivo": "Cliente sin teléfono registrado", "modo": modo}

    if proveedor == "ninguno":
        registrar_envio(db, "whatsapp", destinatario, asunto, cuerpo, "omitido",
                        "Proveedor de whatsapp no configurado",
                        plantilla_id, dedupe_clave=dedupe_clave,
                        usuario_id=usuario_id, cliente_id=cliente_id)
        return {"estado": "omitido", "motivo": "Proveedor de WhatsApp no configurado", "modo": modo}

    try:
        if proveedor == "piloto":
            logger.info(
                "[CANALES] (whatsapp piloto/%s) a %s: %s | adjunto=%s",
                modo, destinatario, cuerpo[:120], bool(documento),
            )
            registrar_envio(db, "whatsapp", destinatario, asunto, cuerpo, "enviado",
                            f"Envío simulado por proveedor piloto (modo {modo})",
                            plantilla_id, dedupe_clave=dedupe_clave,
                            usuario_id=usuario_id, cliente_id=cliente_id)
            return {"estado": "enviado", "motivo": None, "modo": modo}

        respuesta = _enviar_whatsapp_cloud(
            destinatario, cuerpo, documento, nombre_archivo, credenciales
        )
        registrar_envio(db, "whatsapp", destinatario, asunto, cuerpo, "enviado", None,
                        plantilla_id, dedupe_clave=dedupe_clave,
                        usuario_id=usuario_id, cliente_id=cliente_id,
                        whatsapp_message_id=respuesta.get("whatsapp_message_id"),
                        respuesta_proveedor=str(respuesta)[:2000])
        return {"estado": "enviado", "motivo": None, "modo": modo,
                "whatsapp_message_id": respuesta.get("whatsapp_message_id")}
    except Exception as exc:  # noqa: BLE001 - el fallo no revierte el evento
        logger.error("[CANALES] Error enviando whatsapp a %s: %s", destinatario, exc)
        registrar_envio(db, "whatsapp", destinatario, asunto, cuerpo, "fallido", str(exc)[:255],
                        plantilla_id, dedupe_clave=dedupe_clave,
                        usuario_id=usuario_id, cliente_id=cliente_id,
                        error_detalle=str(exc)[:4000])
        return {"estado": "fallido", "motivo": str(exc)[:255], "modo": modo}
