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

from app.services.plantillas import componer_mensaje, registrar_envio

logger = logging.getLogger(__name__)


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
) -> dict:
    """Compone el mensaje desde la plantilla y lo envía por el canal indicado.

    Siempre registra el resultado en envios_mensaje. Nunca lanza excepción.
    """
    try:
        asunto, cuerpo, plantilla = componer_mensaje(db, clave, canal, contexto)
    except Exception as exc:  # noqa: BLE001 - plantilla rota no debe tumbar el evento
        logger.error("[CANALES] Error componiendo %s/%s: %s", canal, clave, exc)
        registrar_envio(db, canal, destinatario, None, "", "fallido", str(exc))
        return {"estado": "fallido", "motivo": str(exc)}

    if not destinatario:
        registro = registrar_envio(
            db, canal, destinatario or "(sin destinatario)", asunto, cuerpo,
            "omitido", "Sin destinatario registrado", plantilla.id if plantilla else None,
        )
        return {"estado": "omitido", "motivo": registro.motivo}

    if canal == "email":
        from app.services.email import enviar_correo

        ok = enviar_correo(destinatario, asunto, cuerpo)
        estado = "enviado" if ok else "fallido"
        motivo = None if ok else "Servidor de correo no disponible o error de envío"
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, estado, motivo,
            plantilla.id if plantilla else None,
        )
        return {"estado": estado, "motivo": motivo}

    proveedor = _resolver_proveedor(canal)
    if proveedor == "ninguno":
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "omitido",
            f"Proveedor de {canal} no configurado", plantilla.id if plantilla else None,
        )
        return {"estado": "omitido", "motivo": registro.motivo}

    permitido, motivo_ventana = _ventana_permitida()
    if not permitido:
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "omitido", motivo_ventana,
            plantilla.id if plantilla else None,
        )
        return {"estado": "omitido", "motivo": motivo_ventana}

    if proveedor == "piloto":
        logger.info("[CANALES] (%s piloto) a %s: %s", canal, destinatario, cuerpo[:120])
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "enviado",
            "Envío simulado por proveedor piloto", plantilla.id if plantilla else None,
        )
        return {"estado": "enviado", "motivo": registro.motivo}

    try:
        _enviar_externo(canal, destinatario, asunto, cuerpo)
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "enviado", None,
            plantilla.id if plantilla else None,
        )
        return {"estado": "enviado", "motivo": None}
    except Exception as exc:  # noqa: BLE001 - el fallo no revierte el evento
        logger.error("[CANALES] Error enviando %s a %s: %s", canal, destinatario, exc)
        registro = registrar_envio(
            db, canal, destinatario, asunto, cuerpo, "fallido", str(exc),
            plantilla.id if plantilla else None,
        )
        return {"estado": "fallido", "motivo": registro.motivo}


def _enviar_externo(canal: str, destinatario: str, asunto: str, cuerpo: str) -> None:
    """Punto de conexión del proveedor externo contratado.

    Aquí se integra la API del proveedor (SMS o mensajería) cuando exista
    contrato. Sin proveedor externo configurado no se llega a este punto.
    """
    raise NotImplementedError(
        f"Proveedor externo de {canal} sin integrar. Configure un adaptador piloto."
    )
