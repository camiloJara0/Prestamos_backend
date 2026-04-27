# registrar pago en la base de datos, actualizar el estado de la cuota y el saldo pendiente del préstamo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.schemas.pago import PagoCreate, PagoOut
from app.services.pago import registrar_pago, get_pagos
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/pagos", tags=["Pagos"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=PagoOut)
def crear_pago(pago: PagoCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return registrar_pago(db, pago)

@router.get("/", response_model=list[PagoOut])
def listar_pagos(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_pagos(db, skip, limit)