from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.schemas.capital import MovimientoCapitalCreate, MovimientoCapitalOut, CapitalOut
from app.schemas.pagination import PaginatedResponse
from app.services.capital import registrar_movimiento, get_or_create_capital, get_movimientos_capital
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
    db: Session = Depends(get_db), 
    current_user: dict = Depends(require_rol("admin"))
):
    return registrar_movimiento(db, movimiento)

@router.get("/", response_model=CapitalOut)
def obtener_capital(
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    return get_or_create_capital(db)

@router.get("/movimientos", response_model=PaginatedResponse[MovimientoCapitalOut])
def listar_movimientos(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(50, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    return get_movimientos_capital(db, page=page, limit=limit)