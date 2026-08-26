from sqlalchemy.orm import Session
from app.models.models import TipoPago
from app.schemas.tipo_pago import TipoPagoCreate, TipoPagoUpdate

def get_tipo_pagos(db: Session, skip: int = 0, limit: int = 10):
    return db.query(TipoPago).filter(TipoPago.estado == "activo").offset(skip).limit(limit).all()

def get_tipo_pago(db: Session, tipo_pago_id: int):
    return db.query(TipoPago).filter(TipoPago.id == tipo_pago_id).first()

def create_tipo_pago(db: Session, tipo_pago: TipoPagoCreate):
    db_tipo_pago = TipoPago(**tipo_pago.dict())
    db.add(db_tipo_pago)
    db.commit()
    db.refresh(db_tipo_pago)
    return db_tipo_pago

def update_tipo_pago(db: Session, tipo_pago_id: int, tipo_pago: TipoPagoUpdate):
    db_tipo_pago = get_tipo_pago(db, tipo_pago_id)
    if not db_tipo_pago:
        return None
    for key, value in tipo_pago.dict(exclude_unset=True).items():
        setattr(db_tipo_pago, key, value)
    db.commit()
    db.refresh(db_tipo_pago)
    return db_tipo_pago

def delete_tipo_pago(db: Session, tipo_pago_id: int):
    db_tipo_pago = get_tipo_pago(db, tipo_pago_id)
    if db_tipo_pago:
        db_tipo_pago.estado = "inactivo"  # soft-delete
        db.commit()
    return db_tipo_pago