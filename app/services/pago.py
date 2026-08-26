from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import date
from app.models.models import Pago, PrestamoCuota, Prestamo, MovimientoCapital, TipoPago
from app.schemas.pago import PagoCreate, PagoOut


def _validar_pago(db: Session, pago: PagoCreate):
    # Verifica que la cuota exista y esté pendiente
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == pago.cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    if cuota.estado != "pendiente":
        raise HTTPException(status_code=400, detail="La cuota ya ha sido pagada o está en mora")

    # Verifica que el préstamo exista y que la cuota pertenezca al préstamo
    prestamo = db.query(Prestamo).filter(Prestamo.id == pago.prestamo_id).first()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    if cuota.prestamo_id != prestamo.id:
        raise HTTPException(status_code=400, detail="La cuota no pertenece al prestamo indicado")

    # Verifica que el cliente coincida con el cliente del préstamo
    if pago.cliente_id != prestamo.cliente_id:
        raise HTTPException(status_code=400, detail="El cliente del pago no coincide con el prestamo")

    # Verifica que el tipo de pago exista
    if not db.query(TipoPago).filter(TipoPago.id == pago.tipo_pago_id).first():
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")

    # Valida montos no negativos
    if pago.valor_pagado < 0 or pago.capital_pagado < 0 or pago.interes_pagado < 0 or pago.mora_pagada < 0:
        raise HTTPException(status_code=400, detail="Los montos del pago no pueden ser negativos")

    # El desglose debe cuadrar con el valor pagado (tolerancia de redondeo)
    desglose = round(pago.capital_pagado + pago.interes_pagado + pago.mora_pagada, 2)
    if abs(desglose - round(pago.valor_pagado, 2)) > 0.01:
        raise HTTPException(
            status_code=400,
            detail="El desglose (capital + interes + mora) no coincide con el valor pagado"
        )

    # No debe pagar más de lo que vale la cuota (salvo mora acumulada)
    if pago.valor_pagado > cuota.valor_cuota + pago.mora_pagada + 0.01:
        raise HTTPException(status_code=400, detail="El valor pagado supera el valor de la cuota")

    return cuota, prestamo


def registrar_pago(db: Session, pago: PagoCreate):
    cuota, prestamo = _validar_pago(db, pago)

    # Registra el pago
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

    # Actualiza el estado de la cuota
    if pago.valor_pagado >= cuota.valor_cuota:
        cuota.estado = "pagado"
    elif pago.valor_pagado > 0 and pago.valor_pagado < cuota.valor_cuota :
        cuota.estado = "parcial"
    else:
        cuota.estado = "pendiente"

    # Actualiza el saldo pendiente del préstamo
    prestamo.saldo_pendiente -= pago.capital_pagado

    # Registra el movimiento de capital
    movimiento = MovimientoCapital(
        prestamo_id=pago.prestamo_id,
        tipo_movimiento="pago_recibido",
        descripcion=f"Pago de cuota {cuota.numero_cuota}",
        valor=pago.capital_pagado,
        fecha=pago.fecha_pago
    )
    db.add(movimiento)

    db.commit()
    db.refresh(db_pago)

    return db_pago

def get_pagos(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Pago).offset(skip).limit(limit).all()

