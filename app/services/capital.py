# Servicio de capital : maneja la logica de inversiones y retiros
# cada movimiento actualiza el monto total del capital disponible

from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import date

from app.models.models import MovimientoCapital, Capital
from app.schemas.capital import MovimientoCapitalCreate
from app.utils.pagination import paginate

def get_or_create_capital(db: Session) -> Capital:
    capital = db.query(Capital).first()
    if not capital:
        capital = Capital(monto_total=0.0)
        db.add(capital)
        db.commit()
        db.refresh(capital)
    return capital

def registrar_movimiento(db: Session, movimiento: MovimientoCapitalCreate):
    if movimiento.tipo_movimiento not in ["inversion", "retiro"]:
        raise HTTPException(status_code=400, detail="Tipo de movimiento debe ser inversion o retiro")
    
    capital = get_or_create_capital(db)

    if movimiento.tipo_movimiento == "retiro":
        if movimiento.valor > capital.monto_total:
            raise HTTPException(status_code=400, detail="Capital insuficiente para realizar el retiro")
        capital.monto_total -= movimiento.valor
    else:
        capital.monto_total += movimiento.valor

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

# --- B2 & B11: Consulta paginada estandarizada del historial de movimientos de capital ---
def get_movimientos_capital(db: Session, page: int = 1, limit: int = 50):
    """
    Retorna la lista paginada del historial de todos los movimientos de capital
    (inversiones, retiros, préstamos otorgados, pagos recibidos, pérdidas).
    """
    query = db.query(MovimientoCapital).order_by(MovimientoCapital.id.desc())
    return paginate(query, page=page, limit=limit)