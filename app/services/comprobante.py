"""Construcción del comprobante/recibo PDF de pago (RF-043).

Antes vivía en routes/pago.py; se extrajo a services para que los
eventos automáticos (comprobante por WhatsApp al registrar pago)
puedan reutilizarlo sin dependencias circulares con las rutas.

El comprobante incluye (además del recibo del pago):
- Información general del préstamo (fecha desembolso, tasa, plazo, estado).
- Listado completo de cuotas con valor pagado y saldo por cuota.
- Totales: financiado, pagado, pendiente, intereses cobrados y capital abonado.
"""

from datetime import date, datetime

from sqlalchemy import func

from app.models.models import Cliente, Pago, Prestamo, PrestamoCuota
from app.utils.pdf_generator import generar_recibo_pdf_bytes

ESTADOS_CUOTA = {
    "pagado": "Pagada",
    "pendiente": "Pendiente",
    "vencido": "Vencida",
    "parcial": "Parcial",
}


def _fecha_iso(valor) -> str:
    """Fecha en dd/mm/YYYY, inmune a desfases de zona horaria (UTC)."""
    if valor is None:
        return ""
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    partes = str(valor).split("T")[0].split(" ")[0].split("-")
    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return str(valor)


def _abonos_por_cuota(db, prestamo_id: int) -> dict[int, dict]:
    """Abonos acumulados por cuota, excluyendo pagos devueltos.

    Patrón de _abonos_cuota (services/pago.py) generalizado a nivel préstamo.
    """
    filas = (
        db.query(
            Pago.cuota_id,
            func.sum(Pago.valor_pagado),
            func.sum(Pago.interes_pagado),
            func.sum(Pago.capital_pagado),
        )
        .filter(Pago.prestamo_id == prestamo_id, Pago.estado_pago != "devuelto")
        .group_by(Pago.cuota_id)
        .all()
    )
    return {
        cuota_id: {
            "pagado": float(valor or 0),
            "interes": float(interes or 0),
            "capital": float(capital or 0),
        }
        for cuota_id, valor, interes, capital in filas
        if cuota_id is not None
    }


def construir_datos_recibo(db, cuota: PrestamoCuota, pago_registro: Pago | None) -> dict:
    from app.services.configuracion import obtener_nombre_empresa

    prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
    cliente = db.query(Cliente).filter(Cliente.id == prestamo.cliente_id).first()

    metodo_pago_nombre = "Transferencia / Efectivo"

    if pago_registro and pago_registro.fecha_pago:
        fecha_bruta = pago_registro.fecha_pago
    elif cuota.fecha_pago:
        fecha_bruta = cuota.fecha_pago
    else:
        fecha_bruta = cuota.updated_at

    fecha_pago_real = _fecha_iso(fecha_bruta)

    if pago_registro and pago_registro.tipo_pago:
        metodo_pago_nombre = pago_registro.tipo_pago.nombre

    referencia_recibo = (
        pago_registro.referencia_recibo if pago_registro else f"REC-CUOTA-{cuota.id}"
    )

    datos_recibo = {
        "nombre_empresa": obtener_nombre_empresa(db),
        "referencia_pago": cuota.referencia_pago
        or f"REF-P{prestamo.id}C{cuota.numero_cuota}",
        "referencia_recibo": referencia_recibo,
        "estado_pago": pago_registro.estado_pago if pago_registro else "confirmado",
        "fecha_pago": fecha_pago_real,
        "cliente_nombre": cliente.nombre,
        "cliente_cedula": cliente.cedula,
        "prestamo_id": prestamo.id,
        "cuota_numero": cuota.numero_cuota,
        "monto_pagado": pago_registro.valor_pagado if pago_registro else cuota.valor_cuota,
        "metodo_pago": metodo_pago_nombre,
    }

    if pago_registro:
        datos_recibo["capital_pagado"] = pago_registro.capital_pagado
        datos_recibo["interes_pagado"] = pago_registro.interes_pagado
        datos_recibo["mora_pagada"] = pago_registro.mora_pagada
        if pago_registro.estado_pago == "devuelto":
            datos_recibo["fecha_devolucion"] = str(pago_registro.fecha_devolucion or "")
            datos_recibo["motivo_devolucion"] = pago_registro.motivo_devolucion

    # --- Información general del préstamo (ya en memoria, sin queries extra) ---
    datos_recibo.update(
        {
            "prestamo_fecha_desembolso": _fecha_iso(prestamo.fecha_prestamo),
            "prestamo_capital_desembolsado": float(prestamo.capital_prestado or 0),
            "prestamo_tasa_interes": prestamo.porcentaje_interes,
            "prestamo_plazo": prestamo.numero_cuotas,
            "prestamo_valor_cuota": float(prestamo.valor_cuota or 0),
            "prestamo_estado": prestamo.estado,
        }
    )

    # --- Detalle completo de cuotas con abonos y saldo por cuota ---
    cuotas = (
        db.query(PrestamoCuota)
        .filter(PrestamoCuota.prestamo_id == prestamo.id)
        .order_by(PrestamoCuota.numero_cuota)
        .all()
    )
    abonos = _abonos_por_cuota(db, prestamo.id)

    detalle_cuotas = []
    for c in cuotas:
        abono = abonos.get(c.id, {"pagado": 0.0, "interes": 0.0, "capital": 0.0})
        valor_cuota = float(c.valor_cuota or 0)
        pagado = abono["pagado"]
        detalle_cuotas.append(
            {
                "id": c.id,
                "numero": c.numero_cuota,
                "fecha_cobro": _fecha_iso(c.fecha_vencimiento),
                "valor_cuota": valor_cuota,
                "valor_pagado": pagado,
                "saldo_pendiente": max(0.0, valor_cuota - pagado),
                "estado": ESTADOS_CUOTA.get(c.estado, c.estado or ""),
            }
        )

    # --- Totales del préstamo ---
    datos_recibo.update(
        {
            "cuotas": detalle_cuotas,
            "total_financiado": float(prestamo.monto_total or 0),
            "total_pagado": sum(a["pagado"] for a in abonos.values()),
            "total_pendiente": float(prestamo.saldo_pendiente or 0),
            "total_intereses_cobrados": sum(a["interes"] for a in abonos.values()),
            "total_capital_abonado": sum(a["capital"] for a in abonos.values()),
        }
    )

    return datos_recibo


def generar_pdf_comprobante(db, cuota: PrestamoCuota, pago_registro: Pago | None):
    """Bytes del comprobante PDF listo para adjuntar o descargar."""
    datos = construir_datos_recibo(db, cuota, pago_registro)
    return generar_recibo_pdf_bytes(datos)
