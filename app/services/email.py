"""Envío de correos transaccionales por SMTP (RF-006).

Configuración por variables de entorno:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS

Sin SMTP_HOST configurado el servicio no falla: registra el mensaje en el log
para que el flujo siga operativo en desarrollo.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str, texto_plano: str = "") -> bool:
    host = os.getenv("SMTP_HOST")
    if not host:
        logger.warning(
            "[EMAIL] SMTP no configurado (SMTP_HOST ausente). Correo no enviado a %s. Asunto: %s | %s",
            destinatario, asunto, texto_plano,
        )
        return False

    port = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    remitente = os.getenv("SMTP_FROM") or usuario or "no-responder@loansoft.local"
    usar_tls = os.getenv("SMTP_TLS", "true").lower() == "true"

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    if texto_plano:
        mensaje.attach(MIMEText(texto_plano, "plain", "utf-8"))
    mensaje.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as servidor:
            if usar_tls:
                servidor.starttls()
            if usuario and password:
                servidor.login(usuario, password)
            servidor.sendmail(remitente, [destinatario], mensaje.as_string())
        logger.info("[EMAIL] Correo enviado a %s: %s", destinatario, asunto)
        return True
    except Exception as exc:  # noqa: BLE001 - el fallo de correo no debe tumbar la operación
        logger.error("[EMAIL] Error enviando correo a %s: %s", destinatario, exc)
        return False
