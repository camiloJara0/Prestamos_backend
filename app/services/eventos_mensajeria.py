"""Disparadores de mensajería automática por eventos de negocio (RF-079).

Cada función envía el mensaje por los canales disponibles del cliente y nunca
lanza excepción: un fallo de mensajería no revierte el evento de negocio.
La deduplicación por dedupe_clave evita repetir el mismo evento el mismo día.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models.models import Cliente, EnvioMensaje, PrestamoCuota

logger = logging.getLogger(__name__)


def _dedupe(db: Session, dedupe_clave: str) -> bool:
    """True si ya se registró un envío (enviado u omitido) con esta clave hoy."""
    return (
        db.query(EnvioMensaje)
        .filter(
            EnvioMensaje.dedupe_clave == dedupe_clave,
            EnvioMensaje.estado.in_(("enviado", "omitido")),
            EnvioMensaje.fecha >= f"{date.today().isoformat()} 00:00:00",
        )
        .count()
        > 0
    )


def disparar(
    db: Session,
    clave: str,
    canal: str,
    destinatario: str,
    contexto: dict,
    dedupe_clave: str | None = None,
) -> dict:
    """Envía un mensaje automático con deduplicación opcional. Nunca lanza."""
    try:
        if dedupe_clave and _dedupe(db, dedupe_clave):
            return {"estado": "omitido", "motivo": "Evento ya notificado hoy"}
        from app.services.canales import enviar_por_canal

        return enviar_por_canal(db, canal, destinatario, clave, contexto, dedupe_clave=dedupe_clave)
    except Exception:  # noqa: BLE001 - la mensajería nunca rompe el negocio
        logger.exception("[EVENTOS] Error disparando %s/%s", clave, canal)
        return {"estado": "fallido", "motivo": "Error interno de mensajería"}


def notificar_pago_confirmado(db: Session, pago, cuota: PrestamoCuota, cliente: Cliente | None) -> None:
    """RF-079/CA-R4-1: confirmación de pago al cliente por SMS si tiene teléfono."""
    if not cliente or not cliente.telefono:
        return
    nombre = cliente.nombre.split()[0] if cliente.nombre else "cliente"
    disparar(
        db,
        clave="pago_confirmado",
        canal="sms",
        destinatario=cliente.telefono,
        contexto={
            "nombre": nombre,
            "monto": f"{pago.valor_pagado:,.0f}",
            "numero_cuota": cuota.numero_cuota if cuota else "—",
            "referencia": pago.referencia_recibo,
        },
        dedupe_clave=f"pago_confirmado:pago:{pago.id}",
    )


def notificar_mora_aviso(db: Session, cuota: PrestamoCuota, valor_mora: float, dias_atraso: int) -> None:
    """RF-079/CA-R4-2: aviso de mora al cliente; un fallo no revierte la generación de mora."""
    cliente = db.query(Cliente).filter(Cliente.id == cuota.prestamo.cliente_id).first() if cuota.prestamo else None
    if not cliente or not cliente.telefono:
        return
    nombre = cliente.nombre.split()[0] if cliente.nombre else "cliente"
    disparar(
        db,
        clave="mora_aviso",
        canal="sms",
        destinatario=cliente.telefono,
        contexto={
            "nombre": nombre,
            "numero_cuota": cuota.numero_cuota,
            "monto_mora": f"{valor_mora:,.0f}",
            "dias_atraso": dias_atraso,
            "referencia": cuota.referencia_pago or "",
        },
        dedupe_clave=f"mora_aviso:cuota:{cuota.id}:{date.today().isoformat()}",
    )


def notificar_bienvenida(db: Session, cliente: Cliente) -> None:
    """RF-079/CA-R4-3: bienvenida al cliente nuevo por SMS si tiene teléfono."""
    if not cliente or not cliente.telefono:
        return
    nombre = cliente.nombre.split()[0] if cliente.nombre else "cliente"
    disparar(
        db,
        clave="cliente_bienvenida",
        canal="sms",
        destinatario=cliente.telefono,
        contexto={"nombre": nombre},
        dedupe_clave=f"cliente_bienvenida:cliente:{cliente.id}",
    )
