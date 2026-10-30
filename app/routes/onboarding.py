"""Estado de configuración inicial (onboarding) validado por el backend.

El "primer ingreso" se deriva de los DATOS reales de la instancia (no de una
marca booleana), de forma que si se migra o purga la base el asistente vuelve
a aparecer y ningún usuario se queda sin configurar.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.db.database import SessionLocal
from app.models.models import TipoPrestamo, TipoPago, Cliente, Capital

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/estado")
def estado_onboarding(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Indica si la instancia aún necesita la configuración inicial."""
    tipos = db.query(TipoPrestamo).filter(TipoPrestamo.estado == "activo").count()
    tipos_pago = db.query(TipoPago).filter(TipoPago.estado == "activo").count()
    clientes = db.query(Cliente).filter(Cliente.estado == "activo").count()
    capital = db.query(Capital).first()
    monto_capital = float(capital.monto_total or 0.0) if capital else 0.0

    # Primer ingreso: aún no hay ni catálogos ni clientes ni capital registrado.
    primer_ingreso = tipos == 0 and clientes == 0 and monto_capital == 0.0

    return {
        "primer_ingreso": primer_ingreso,
        "tipos_prestamo": tipos,
        "tipos_pago": tipos_pago,
        "clientes": clientes,
        "capital": monto_capital,
        "completado": not primer_ingreso,
    }


@router.post("/completar")
def completar_onboarding(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Compatibilidad con el cliente: recalcula y devuelve el estado actual."""
    tipos = db.query(TipoPrestamo).filter(TipoPrestamo.estado == "activo").count()
    clientes = db.query(Cliente).filter(Cliente.estado == "activo").count()
    capital = db.query(Capital).first()
    monto_capital = float(capital.monto_total or 0.0) if capital else 0.0
    primer_ingreso = tipos == 0 and clientes == 0 and monto_capital == 0.0
    return {"completado": not primer_ingreso, "primer_ingreso": primer_ingreso}
