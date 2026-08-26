# Endpoint POST /capital : registra inversiones y retiros
# actualiza el monto total del capital disponible

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.schemas.capital import MovimientoCapitalCreate, MovimientoCapitalOut, CapitalOut
from app.services.capital import registrar_movimiento, get_or_create_capital
from app.dependencies.auth import get_current_user, require_rol

router = APIRouter(prefix="/capital", tags=["Capital"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/")
def crear_movimiento(movimiento: MovimientoCapitalCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_rol("admin"))):
    return registrar_movimiento(db, movimiento)

@router.get("/", response_model=CapitalOut)
def obtener_capital(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_or_create_capital(db)