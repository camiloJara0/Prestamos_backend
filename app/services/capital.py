# Servicio de capital : maneja la logica de inversiones y retiros
# cada movimiento actualiza el monto total del capital disponible

from typing import Optional
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

def registrar_movimiento(db: Session, movimiento: MovimientoCapitalCreate, usuario_id: Optional[int] = None, ip_address: Optional[str] = None):
    if movimiento.tipo_movimiento not in ["inversion", "retiro"]:
        raise HTTPException(status_code=400, detail="Tipo de movimiento debe ser inversion o retiro")
    if not movimiento.descripcion or not movimiento.descripcion.strip():
        raise HTTPException(status_code=422, detail="El concepto del movimiento es obligatorio")
    
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

    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="movimientos_capital",
        tipo_operacion="CREATE",
        registro_id=db_movimiento.id,
        valores_nuevos={
            "tipo_movimiento": db_movimiento.tipo_movimiento,
            "descripcion": db_movimiento.descripcion,
            "valor": db_movimiento.valor,
            "fecha": str(db_movimiento.fecha),
        },
        descripcion=f"Movimiento de caja registrado: {db_movimiento.descripcion}",
        ip_address=ip_address,
    )

    return {"movimiento": db_movimiento, "capital_actual": capital.monto_total}

# --- B2 & B11: Consulta paginada estandarizada del historial de movimientos de capital ---
def get_movimientos_capital(
    db: Session,
    page: int = 1,
    limit: int = 50,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    tipo: Optional[str] = None,
):
    """
    Historial paginado de movimientos de capital con filtros de periodo y tipo (RF-051).
    """
    query = db.query(MovimientoCapital)
    if desde:
        query = query.filter(MovimientoCapital.fecha >= desde)
    if hasta:
        query = query.filter(MovimientoCapital.fecha <= hasta)
    if tipo:
        query = query.filter(MovimientoCapital.tipo_movimiento == tipo)
    query = query.order_by(MovimientoCapital.id.desc())
    return paginate(query, page=page, limit=limit)


def get_resumen_caja(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None):
    """
    Totales de ingresos y egresos de caja (aportes y retiros) en el periodo (RF-051).
    """
    query = db.query(MovimientoCapital).filter(
        MovimientoCapital.tipo_movimiento.in_(["inversion", "retiro"])
    )
    if desde:
        query = query.filter(MovimientoCapital.fecha >= desde)
    if hasta:
        query = query.filter(MovimientoCapital.fecha <= hasta)
    movimientos = query.all()

    ingresos = [m for m in movimientos if m.tipo_movimiento == "inversion"]
    egresos = [m for m in movimientos if m.tipo_movimiento == "retiro"]

    if desde and hasta:
        periodo = f"{desde} a {hasta}"
    elif desde:
        periodo = f"Desde {desde}"
    elif hasta:
        periodo = f"Hasta {hasta}"
    else:
        periodo = "Todos los periodos"

    capital = get_or_create_capital(db)

    return {
        "periodo": periodo,
        "ingresos": round(sum(m.valor for m in ingresos), 2),
        "egresos": round(sum(m.valor for m in egresos), 2),
        "cantidad_ingresos": len(ingresos),
        "cantidad_egresos": len(egresos),
        "saldo_capital": round(capital.monto_total, 2),
    }