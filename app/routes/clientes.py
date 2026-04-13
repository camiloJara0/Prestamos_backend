from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.services import clientes as services
from app.schemas import clientes as schemas

router = APIRouter(prefix="/clientes", tags=["Clientes"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.ClienteOut)
def crear_cliente(cliente: schemas.ClienteCreate, db: Session = Depends(get_db)):
    return services.create_cliente(db, cliente)

@router.get("/", response_model=list[schemas.ClienteOut])
def listar_clientes(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return services.get_clientes(db, skip, limit)

@router.get("/{cliente_id}", response_model=schemas.ClienteOut)
def obtener_cliente(cliente_id: int, db: Session = Depends(get_db)):
    db_cliente = services.get_cliente(db, cliente_id)
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return db_cliente

@router.put("/{cliente_id}", response_model=schemas.ClienteOut)
def actualizar_cliente(cliente_id: int, cliente: schemas.ClienteUpdate, db: Session = Depends(get_db)):
    db_cliente = services.update_cliente(db, cliente_id, cliente)
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return db_cliente

@router.delete("/{cliente_id}")
def eliminar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    db_cliente = services.delete_cliente(db, cliente_id)
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"mensaje": "Cliente eliminado"}