from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import date

from app.models.models import Pago, PrestamoCuota, Prestamo, MovimientoCapital, TipoPago, Capital
from app.schemas.pago import PagoCreate, PagoOut
from app.utils.pagination import paginate


def _validar_pago(db: Session, pago: PagoCreate):
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == pago.cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    if cuota.estado == "pagado":
        raise HTTPException(status_code=400, detail="La cuota ya ha sido completamente pagada")

    prestamo = db.query(Prestamo).filter(Prestamo.id == pago.prestamo_id).first()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    if cuota.prestamo_id != prestamo.id:
        raise HTTPException(status_code=400, detail="La cuota no pertenece al prestamo indicado")

    if pago.cliente_id != prestamo.cliente_id:
        raise HTTPException(status_code=400, detail="El cliente del pago no coincide con el prestamo")

    if not db.query(TipoPago).filter(TipoPago.id == pago.tipo_pago_id).first():
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")

    if pago.valor_pagado < 0 or pago.capital_pagado < 0 or pago.interes_pagado < 0 or pago.mora_pagada < 0:
        raise HTTPException(status_code=400, detail="Los montos del pago no pueden ser negativos")

    desglose = round(pago.capital_pagado + pago.interes_pagado + pago.mora_pagada, 2)
    if abs(desglose - round(pago.valor_pagado, 2)) > 0.01:
        raise HTTPException(
            status_code=400,
            detail="El desglose (capital + interes + mora) no coincide con el valor pagado"
        )

    return cuota, prestamo


def registrar_pago(db: Session, pago: PagoCreate, usuario_id: int):
    cuota, prestamo = _validar_pago(db, pago)

    db_pago = Pago(
        prestamo_id=pago.prestamo_id,
        cliente_id=pago.cliente_id,
        cuota_id=pago.cuota_id,
        tipo_pago_id=pago.tipo_pago_id,
        fecha_pago=pago.fecha_pago,
        valor_pagado=pago.valor_pagado,
        capital_pagado=pago.capital_pagado,
        interes_pagado=pago.interes_pagado,
        mora_pagada=pago.mora_pagada,
        observaciones=pago.observaciones
    )
    db.add(db_pago)

    pagos_anteriores = db.query(Pago).filter(Pago.cuota_id == cuota.id).all()
    total_abonado = sum(p.valor_pagado for p in pagos_anteriores) + pago.valor_pagado

    if total_abonado >= cuota.valor_cuota - 0.01:
        cuota.estado = "pagado"
    else:
        cuota.estado = "parcial"

    prestamo.saldo_pendiente = round(prestamo.saldo_pendiente - (pago.capital_pagado + pago.interes_pagado), 2)
    if prestamo.saldo_pendiente <= 0:
        prestamo.saldo_pendiente = 0.0
        prestamo.estado = "pagado"

    capital_obj = db.query(Capital).first()
    if capital_obj:
        capital_obj.monto_total += pago.valor_pagado

    movimiento = MovimientoCapital(
        prestamo_id=pago.prestamo_id,
        tipo_movimiento="pago_recibido",
        descripcion=f"Pago de cuota #{cuota.numero_cuota} (Préstamo #{prestamo.id})",
        valor=pago.valor_pagado,
        fecha=pago.fecha_pago
    )
    db.add(movimiento)

    db.commit()
    db.refresh(db_pago)

    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="pagos",
        tipo_operacion="CREATE",
        registro_id=db_pago.id,
        valores_nuevos={
            "cuota_id": db_pago.cuota_id,
            "monto_pagado": db_pago.valor_pagado,
            "capital_pagado": db_pago.capital_pagado,
            "interes_pagado": db_pago.interes_pagado,
            "mora_pagada": db_pago.mora_pagada,
            "fecha_pago": str(db_pago.fecha_pago)
        },
        descripcion=f"Pago registrado para cuota #{db_pago.cuota_id}"
    )

    return db_pago


def get_pagos(db: Session, page: int = 1, limit: int = 10):
    query = db.query(Pago).order_by(Pago.id.desc())
    return paginate(query, page=page, limit=limit)