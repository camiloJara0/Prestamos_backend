from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
import app.services.tipo_prestamo as services
import app.schemas.tipo_prestamo as schemas
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/tipo_prestamo", tags=["TipoPrestamo"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.TipoPrestamoOut)
def crear_tipo_prestamo(tipo_prestamo: schemas.TipoPrestamoCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return services.create_tipo_prestamo(db, tipo_prestamo)

@router.get("/", response_model=list[schemas.TipoPrestamoOut])
def listar_tipo_prestamos(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return services.get_tipo_prestamos(db, skip, limit)

@router.get("/{tipo_prestamo_id}", response_model=schemas.TipoPrestamoOut)
def obtener_tipo_prestamo(tipo_prestamo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_tipo_prestamo = services.get_tipo_prestamo(db, tipo_prestamo_id)
    if not db_tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de prestamo no encontrado")
    return db_tipo_prestamo

@router.put("/{tipo_prestamo_id}", response_model=schemas.TipoPrestamoOut)
def actualizar_tipo_prestamo(tipo_prestamo_id: int, tipo_prestamo: schemas.TipoPrestamoUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_tipo_prestamo = services.update_tipo_prestamo(db, tipo_prestamo_id, tipo_prestamo)
    if not db_tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de prestamo no encontrado")
    return db_tipo_prestamo

@router.delete("/{tipo_prestamo_id}")
def eliminar_tipo_prestamo(tipo_prestamo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_tipo_prestamo = services.delete_tipo_prestamo(db, tipo_prestamo_id)
    if not db_tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de prestamo no encontrado")
    return {"mensaje": "Tipo de prestamo eliminado"}