from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import crud.tipo_prestamo as crud
import schemas.tipo_prestamo as schemas

router = APIRouter(prefix="/tipo_prestamo", tags=["TipoPrestamo"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.TipoPrestamoOut)
def crear_tipo_prestamo(tipo_prestamo: schemas.TipoPrestamoCreate, db: Session = Depends(get_db)):
    return crud.create_tipo_prestamo(db, tipo_prestamo)

@router.get("/", response_model=list[schemas.TipoPrestamoOut])
def listar_tipo_prestamos(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_tipo_prestamo(db, skip, limit)

@router.get("/{tipo_prestamo_id}", response_model=schemas.TipoPrestamoOut)
def obtener_tipo_prestamo(tipo_prestamo_id: int, db: Session = Depends(get_db)):
    db_tipo_prestamo = crud.get_tipo_prestamo(db, tipo_prestamo_id)
    if not db_tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de prestamo no encontrado")
    return db_tipo_prestamo

@router.put("/{tipo_prestamo_id}", response_model=schemas.TipoPrestamoOut)
def actualizar_tipo_prestamo(tipo_prestamo_id: int, tipo_prestamo: schemas.TipoPrestamoUpdate, db: Session = Depends(get_db)):
    db_tipo_prestamo = crud.update_tipo_prestamo(db, tipo_prestamo_id, tipo_prestamo)
    if not db_tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de prestamo no encontrado")
    return db_tipo_prestamo

@router.delete("/{tipo_prestamo_id}")
def eliminar_tipo_prestamo(tipo_prestamo_id: int, db: Session = Depends(get_db)):
    db_tipo_prestamo = crud.delete_tipo_prestamo(db, tipo_prestamo_id)
    if not db_tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de prestamo no encontrado")
    return {"mensaje": "Tipo de prestamo eliminado"}