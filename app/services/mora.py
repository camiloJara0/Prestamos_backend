from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models.models import Mora, PrestamoCuota, Pago
from app.schemas.mora import MoraCreate, MoraUpdate, MoraOut
from datetime import date


def get_moras(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Mora).filter(Mora.estado == "generada").order_by(Mora.fecha.desc()).offset(skip).limit(limit).all()  # Solo moras generadas

def get_moras_prestamo(db: Session, prestamo_id: int):
    return db.query(Mora).filter(Mora.prestamo_id == prestamo_id).order_by(Mora.fecha.desc()).all()

def get_mora(db: Session, mora_id: int):
    return db.query(Mora).filter(Mora.id == mora_id).first()

def update_mora(db: Session, mora_id: int, mora: MoraUpdate):
    db_mora = get_mora(db, mora_id)
    if not db_mora:
        return None
    for key, value in mora.dict(exclude_unset=True).items():
        setattr(db_mora, key, value)
    db.commit()
    db.refresh(db_mora)
    return db_mora

def delete_mora(db: Session, mora_id: int):
    db_mora = get_mora(db, mora_id)
    if db_mora:
        db.delete(db_mora)
        db.commit()
    return db_mora

# Calcular mora
def calcular_mora(db: Session, cuota: PrestamoCuota, tasa_diaria: float, pago: Pago) -> Mora | None:
    if cuota.estado == "pagado" or cuota.fecha_vencimiento >= date.today():
        return None

    # Caso especial: cuota parcial pero intereses ya cubiertos
    if cuota.estado == "parcial" and pago.interes_pagado == cuota.interes:
        return None

    dias_atraso = (date.today() - cuota.fecha_vencimiento).days
    valor_mora = cuota.valor_cuota * tasa_diaria * dias_atraso

    # Buscar si ya existe una mora registrada para esta cuota
    mora_existente = (
        db.query(Mora)
        .filter(Mora.cuota_id == cuota.id, Mora.estado == "generada")
        .first()
    )

    if mora_existente:
        # Actualizar valor y fecha
        mora_existente.valor = valor_mora
        mora_existente.fecha = date.today()
        db.add(mora_existente)
        db.commit()
        return mora_existente
    else:
        # Crear nueva mora
        mora = Mora(
            prestamo_id=cuota.prestamo_id,
            cuota_id=cuota.id,
            fecha=date.today(),
            valor=valor_mora,
            estado="generada"
        )
        cuota.estado = "vencido"
        db.add(mora)
        db.commit()
        return mora
    

def procesar_moras(db: Session, tasa_diaria: float):
    cuotas = db.query(PrestamoCuota).filter(PrestamoCuota.estado != "pagado").all()
    moras_generadas = []

    for cuota in cuotas:
        pago = db.query(Pago).filter(Pago.cuota_id == cuota.id).first()
        mora = calcular_mora(db, cuota, tasa_diaria, pago)
        if mora:
            moras_generadas.append(mora)

    return moras_generadas


