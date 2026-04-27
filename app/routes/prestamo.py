# Endpoints de prestamos
# POST /prestamos : crea un nuevo prestamo con cuotas automaticas
# GET /prestamos : lista los prestamos activos

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.schemas.prestamo import PrestamoCreate, PrestamoOut, RenovacionCreate
from app.services.prestamo import crear_prestamo, get_prestamos, renovar_prestamo
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/prestamos", tags=["Prestamos"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=PrestamoOut)
def crear(prestamo: PrestamoCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return crear_prestamo(db, prestamo)

@router.get("/", response_model=list[PrestamoOut])
def listar(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_prestamos(db, skip, limit)

@router.post("/{prestamo_id}/renovar", response_model=PrestamoOut)
def renovar(prestamo_id: int, renovacion: RenovacionCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return renovar_prestamo(db, prestamo_id, renovacion)