from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import date
from app.models.models import Pago, PrestamoCuota, Prestamo, MovimientoCapital
from app.schemas.pago import PagoCreate, PagoOut

def registrar_pago(db: Session, pago: PagoCreate):
    # Verifica que la cuota exista y esté pendiente
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == pago.cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    if cuota.estado != "pendiente":
        raise HTTPException(status_code=400, detail="La cuota ya ha sido pagada o está en mora")

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
    else:
        cuota.estado = "pendiente"

    # Actualiza el saldo pendiente del préstamo
    prestamo = db.query(Prestamo).filter(Prestamo.id == pago.prestamo_id).first()
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

