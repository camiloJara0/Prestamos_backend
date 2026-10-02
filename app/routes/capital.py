from datetime import date
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.schemas.capital import MovimientoCapitalCreate, MovimientoCapitalOut, CapitalOut, ResumenCajaOut
from app.schemas.pagination import PaginatedResponse
from app.services.capital import (
    registrar_movimiento,
    get_or_create_capital,
    get_movimientos_capital,
    get_resumen_caja,
)
from app.dependencies.auth import get_current_user, require_rol

router = APIRouter(prefix="/capital", tags=["Capital"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/")
def crear_movimiento(
    movimiento: MovimientoCapitalCreate, 
    request: Request,
    db: Session = Depends(get_db), 
    current_user: dict = Depends(require_rol("admin"))
):
    return registrar_movimiento(
        db, movimiento,
        usuario_id=current_user.get("sub"),
        ip_address=request.client.host if request.client else None,
    )

@router.get("/", response_model=CapitalOut)
def obtener_capital(
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    return get_or_create_capital(db)

@router.get("/resumen-caja", response_model=ResumenCajaOut)
def resumen_caja(
    desde: date | None = Query(None, description="Fecha desde"),
    hasta: date | None = Query(None, description="Fecha hasta"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Ingresos y egresos de caja del periodo (RF-051)."""
    return get_resumen_caja(db, desde=desde, hasta=hasta)

@router.get("/movimientos", response_model=PaginatedResponse[MovimientoCapitalOut])
def listar_movimientos(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=100, description="Elementos por página"),
    desde: date | None = Query(None, description="Fecha desde"),
    hasta: date | None = Query(None, description="Fecha hasta"),
    tipo: str | None = Query(None, description="Tipo de movimiento"),
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    return get_movimientos_capital(db, page=page, limit=limit, desde=desde, hasta=hasta, tipo=tipo)
