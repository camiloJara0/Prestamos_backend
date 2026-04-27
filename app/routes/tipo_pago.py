from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
import app.services.tipo_pago as services
import app.schemas.tipo_pago as schemas
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/tipo_pago", tags=["TipoPago"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.TipoPagoOut)
def crear_tipo_pago(tipo_pago: schemas.TipoPagoCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return services.create_tipo_pago(db, tipo_pago)

@router.get("/", response_model=list[schemas.TipoPagoOut])
def listar_tipo_pagos(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return services.get_tipo_pagos(db, skip, limit)

@router.get("/{tipo_pago_id}", response_model=schemas.TipoPagoOut)
def obtener_tipo_pago(tipo_pago_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_tipo_pago = services.get_tipo_pago(db, tipo_pago_id)
    if not db_tipo_pago:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")
    return db_tipo_pago

@router.put("/{tipo_pago_id}", response_model=schemas.TipoPagoOut)
def actualizar_tipo_pago(tipo_pago_id: int, tipo_pago: schemas.TipoPagoUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_tipo_pago = services.update_tipo_pago(db, tipo_pago_id, tipo_pago)
    if not db_tipo_pago:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")
    return db_tipo_pago

@router.delete("/{tipo_pago_id}")
def eliminar_tipo_pago(tipo_pago_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_tipo_pago = services.delete_tipo_pago(db, tipo_pago_id)
    if not db_tipo_pago:
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")
    return {"mensaje": "Tipo de pago eliminado"}