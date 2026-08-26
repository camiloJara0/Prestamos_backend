# Endpoints de prestamos
# POST /prestamos : crea un nuevo prestamo con cuotas automaticas
# GET /prestamos : lista los prestamos con filtros
# GET /prestamos/{id} : detalle completo con cuotas, pagos y cliente

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.db.database import SessionLocal
from app.schemas.prestamo import PrestamoCreate, PrestamoOut, PrestamoDetalleOut, RenovacionCreate, MarcarPerdidoRequest
from app.services.prestamo import crear_prestamo, get_prestamos, obtener_prestamo, renovar_prestamo, marcar_prestamo_perdido
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
def listar(
    skip: int = 0,
    limit: int = 10,
    estado: Optional[str] = "activo",
    cliente_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    busqueda: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_prestamos(
        db,
        skip=skip,
        limit=limit,
        estado=estado,
        cliente_id=cliente_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        busqueda=busqueda,
    )

@router.get("/{prestamo_id}", response_model=PrestamoDetalleOut)
def obtener(prestamo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_prestamo = obtener_prestamo(db, prestamo_id)
    if not db_prestamo:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    return db_prestamo

@router.post("/{prestamo_id}/renovar", response_model=PrestamoOut)
def renovar(prestamo_id: int, renovacion: RenovacionCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return renovar_prestamo(db, prestamo_id, renovacion)

@router.post("/{prestamo_id}/marcar_perdido")
def marcar_perdido(prestamo_id: int, datos: MarcarPerdidoRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return marcar_prestamo_perdido(db, prestamo_id, datos)

