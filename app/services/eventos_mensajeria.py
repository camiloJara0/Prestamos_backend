"""Disparadores de mensajería automática por eventos de negocio (RF-079).

Canal principal: WHATSAPP. El canal SMS sigue soportado por la
arquitectura (canales.py + plantillas) y puede reactivarse cambiando el
canal del disparo, sin alterar la lógica de negocio.

Cada función envía el mensaje por los canales disponibles del cliente y
nunca lanza excepción: un fallo de mensajería no revierte el evento de
negocio. La deduplicación por dedupe_clave evita repetir el mismo evento
el mismo día.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.core.context import usuario_actual_id
from app.models.models import Cliente, EnvioMensaje, PrestamoCuota

logger = logging.getLogger(__name__)

CANAL_CLIENTE = "whatsapp"  # canal principal de comunicación con clientes


def _dedupe(db: Session, dedupe_clave: str) -> bool:
    """True si ya se registró un envío (enviado u omitido) con esta clave hoy."""
    return (
        db.query(EnvioMensaje)
        .filter(
            EnvioMensaje.dedupe_clave == dedupe_clave,
            EnvioMensaje.estado.in_(("enviado", "omitido", "entregado", "leido")),
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
    cliente_id: int | None = None,
) -> dict:
    """Envía un mensaje automático con deduplicación opcional. Nunca lanza."""
    try:
        if dedupe_clave and _dedupe(db, dedupe_clave):
            return {"estado": "omitido", "motivo": "Evento ya notificado hoy"}
        from app.services.canales import enviar_por_canal

        return enviar_por_canal(
            db, canal, destinatario, clave, contexto,
            dedupe_clave=dedupe_clave, cliente_id=cliente_id,
        )
    except Exception:  # noqa: BLE001 - la mensajería nunca rompe el negocio
        logger.exception("[EVENTOS] Error disparando %s/%s", clave, canal)
        return {"estado": "fallido", "motivo": "Error interno de mensajería"}


def _empresa_contexto(db: Session) -> dict:
    from app.services.configuracion import (
        obtener_nombre_empresa,
        obtener_telefono_empresa,
    )

    return {
        "empresa_nombre": obtener_nombre_empresa(db),
        "empresa_telefono": obtener_telefono_empresa(db),
    }


def _cliente_base(cliente: Cliente) -> dict:
    nombre = cliente.nombre.split()[0] if cliente.nombre else "cliente"
    return {
        "nombre": nombre,
        "cliente_nombre": cliente.nombre or "",
        "cliente_documento": cliente.cedula or "",
        "cliente_telefono": cliente.telefono or "",
        "cliente_direccion": cliente.direccion or "",
    }


def notificar_pago_confirmado(
    db: Session, pago, cuota: PrestamoCuota, cliente: Cliente | None
) -> None:
    """RF-079/CA-R4-1: confirmación de pago al cliente por WhatsApp,
    seguida del comprobante PDF adjunto. Un fallo no revierte el pago."""
    if not cliente or not cliente.telefono:
        return
    disparar(
        db,
        clave="pago_confirmado",
        canal=CANAL_CLIENTE,
        destinatario=cliente.telefono,
        contexto={
            **_cliente_base(cliente),
            "monto": f"{pago.valor_pagado:,.0f}",
            "numero_cuota": cuota.numero_cuota if cuota else "—",
            "cuota_numero": cuota.numero_cuota if cuota else "—",
            "referencia": pago.referencia_recibo,
        },
        dedupe_clave=f"pago_confirmado:pago:{pago.id}",
        cliente_id=cliente.id,
    )
    _enviar_comprobante_automatico(db, pago, cuota, cliente)


def _enviar_comprobante_automatico(
    db: Session, pago, cuota: PrestamoCuota, cliente: Cliente
) -> None:
    """Adjunta automáticamente el comprobante PDF tras registrar el pago."""
    try:
        if _dedupe(db, f"comprobante:pago:{pago.id}"):
            return

        from app.services.canales import enviar_whatsapp_directo
        from app.services.comprobante import generar_pdf_comprobante

        pdf = generar_pdf_comprobante(db, cuota, pago)
        enviar_whatsapp_directo(
            db,
            destinatario=cliente.telefono,
            cuerpo="Adjunto el comprobante de tu pago.",
            documento=pdf.getvalue(),
            nombre_archivo=f"Comprobante_{pago.referencia_recibo}.pdf",
            asunto=f"Comprobante de pago {pago.referencia_recibo}",
            dedupe_clave=f"comprobante:pago:{pago.id}",
            usuario_id=usuario_actual_id.get(),
            cliente_id=cliente.id,
        )
    except Exception:  # noqa: BLE001 - el comprobante automático no rompe el pago
        logger.exception("[EVENTOS] Error enviando comprobante del pago %s", pago.id)


def notificar_mora_aviso(
    db: Session, cuota: PrestamoCuota, valor_mora: float, dias_atraso: int
) -> None:
    """RF-079/CA-R4-2: aviso de mora al cliente por WhatsApp; un fallo no
    revierte la generación de mora."""
    cliente = (
        db.query(Cliente).filter(Cliente.id == cuota.prestamo.cliente_id).first()
        if cuota.prestamo
        else None
    )
    if not cliente or not cliente.telefono:
        return
    disparar(
        db,
        clave="mora_aviso",
        canal=CANAL_CLIENTE,
        destinatario=cliente.telefono,
        contexto={
            **_cliente_base(cliente),
            **_empresa_contexto(db),
            "numero_cuota": cuota.numero_cuota,
            "cuota_numero": cuota.numero_cuota,
            "monto_mora": f"{valor_mora:,.0f}",
            "dias_atraso": dias_atraso,
            "referencia": cuota.referencia_pago or "",
        },
        dedupe_clave=f"mora_aviso:cuota:{cuota.id}:{date.today().isoformat()}",
        cliente_id=cliente.id,
    )


def notificar_bienvenida(db: Session, cliente: Cliente) -> None:
    """RF-079/CA-R4-3: bienvenida al cliente nuevo por WhatsApp."""
    if not cliente or not cliente.telefono:
        return
    disparar(
        db,
        clave="cliente_bienvenida",
        canal=CANAL_CLIENTE,
        destinatario=cliente.telefono,
        contexto={**_cliente_base(cliente), **_empresa_contexto(db)},
        dedupe_clave=f"cliente_bienvenida:cliente:{cliente.id}",
        cliente_id=cliente.id,
    )


def notificar_prestamo_creado(
    db: Session, prestamo, cliente: Cliente | None, primera_cuota=None
) -> None:
    """Resumen inicial del préstamo por WhatsApp al cliente."""
    if not cliente or not cliente.telefono:
        return
    try:
        from app.services.canales import enviar_whatsapp_directo
        from app.services.plantillas import (
            obtener_plantilla,
            renderizar,
            _contexto_extendido,
        )

        contexto = _contexto_extendido(db, {
            **_cliente_base(cliente),
            "prestamo_id": prestamo.id,
            "prestamo_monto": f"{prestamo.capital_prestado:,.0f}",
            "prestamo_cuotas": prestamo.numero_cuotas,
            "cuota_numero": primera_cuota.numero_cuota if primera_cuota else "1",
            "cuota_fecha_vencimiento": (
                primera_cuota.fecha_vencimiento.isoformat()
                if primera_cuota and primera_cuota.fecha_vencimiento
                else "—"
            ),
        })
        plantilla_db = obtener_plantilla(db, "prestamo_creado", CANAL_CLIENTE)
        cuerpo = renderizar(
            plantilla_db.cuerpo if plantilla_db else "", contexto
        )
        enviar_whatsapp_directo(
            db,
            destinatario=cliente.telefono,
            cuerpo=cuerpo,
            asunto="Préstamo registrado",
            plantilla_id=plantilla_db.id if plantilla_db else None,
            dedupe_clave=f"prestamo_creado:prestamo:{prestamo.id}",
            usuario_id=usuario_actual_id.get() or prestamo.usuario_id,
            cliente_id=cliente.id,
        )
    except Exception:  # noqa: BLE001 - la mensajería nunca rompe el negocio
        logger.exception("[EVENTOS] Error notificando préstamo creado")
