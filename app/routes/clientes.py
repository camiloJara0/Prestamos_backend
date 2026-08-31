from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.schemas import clientes as schemas
from app.schemas.pagination import PaginatedResponse
from app.services import clientes as services
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/clientes", tags=["Clientes"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.ClienteOut)
def crear_cliente(
    cliente: schemas.ClienteCreate, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    return services.create_cliente(db, cliente)

@router.get("/", response_model=PaginatedResponse[schemas.ClienteOut])
def listar_clientes(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    busqueda: str | None = Query(None, alias="q", description="Buscar por nombre o cédula"),
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    return services.get_clientes(db, page=page, limit=limit, busqueda=busqueda)

@router.get("/{cliente_id}", response_model=schemas.ClienteOut)
def obtener_cliente(
    cliente_id: int, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    db_cliente = services.get_cliente(db, cliente_id)
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return db_cliente

@router.put("/{cliente_id}", response_model=schemas.ClienteOut)
def actualizar_cliente(
    cliente_id: int, 
    cliente: schemas.ClienteUpdate, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    db_cliente = services.update_cliente(db, cliente_id, cliente)
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return db_cliente

@router.delete("/{cliente_id}")
def eliminar_cliente(
    cliente_id: int, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    db_cliente = services.delete_cliente(db, cliente_id)
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"mensaje": "Cliente eliminado"}