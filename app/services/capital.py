# Servicio de capital : maneja la logica de inversiones y retiros
# cada movimiento actualiza el monto total del capital disponible

from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import date
from app.models.models import MovimientoCapital, Capital
from app.schemas.capital import MovimientoCapitalCreate

def get_or_create_capital(db: Session) -> Capital:
    # Obtiene el registro de capital o lo crea si no existe
    capital = db.query(Capital).first()
    if not capital:
        capital = Capital(monto_total=0.0)
        db.add(capital)
        db.commit()
        db.refresh(capital)
    return capital

def registrar_movimiento(db: Session, movimiento: MovimientoCapitalCreate):
    # Valida que el tipo de movimiento sea inversion o retiro
    if movimiento.tipo_movimiento not in ["inversion", "retiro"]:
        raise HTTPException(status_code=400, detail="Tipo de movimiento debe ser inversion o retiro")
    
    capital = get_or_create_capital(db)

    # Si es retiro verifica que haya suficiente capital
    if movimiento.tipo_movimiento == "retiro":
        if movimiento.valor > capital.monto_total:
            raise HTTPException(status_code=400, detail="Capital insuficiente para realizar el retiro")
        capital.monto_total -= movimiento.valor
    else:
        capital.monto_total += movimiento.valor

    # Registra el movimiento en el historial
    db_movimiento = MovimientoCapital(
        tipo_movimiento=movimiento.tipo_movimiento,
        descripcion=movimiento.descripcion,
        valor=movimiento.valor,
        fecha=movimiento.fecha
    )
    db.add(db_movimiento)
    db.commit()
    db.refresh(db_movimiento)

    return {"movimiento": db_movimiento, "capital_actual": capital.monto_total}