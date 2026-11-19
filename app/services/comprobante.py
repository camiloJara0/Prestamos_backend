"""Construcción del comprobante/recibo PDF de pago (RF-043).

Antes vivía en routes/pago.py; se extrajo a services para que los
eventos automáticos (comprobante por WhatsApp al registrar pago)
puedan reutilizarlo sin dependencias circulares con las rutas.
"""

from app.models.models import Cliente, Pago, Prestamo, PrestamoCuota
from app.utils.pdf_generator import generar_recibo_pdf_bytes


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

    fecha_pago_real = str(fecha_bruta).split("T")[0].split(" ")[0]

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

    return datos_recibo


def generar_pdf_comprobante(db, cuota: PrestamoCuota, pago_registro: Pago | None):
    """Bytes del comprobante PDF listo para adjuntar o descargar."""
    datos = construir_datos_recibo(db, cuota, pago_registro)
    return generar_recibo_pdf_bytes(datos)
