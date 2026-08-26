from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models.models import Cliente
from app.schemas.clientes import ClienteCreate, ClienteUpdate


def get_clientes(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Cliente).filter(Cliente.estado == "activo").offset(skip).limit(limit).all() # Solo clientes activos

def get_cliente(db: Session, cliente_id: int):
    return db.query(Cliente).filter(Cliente.id == cliente_id).first()

def create_cliente(db: Session, cliente: ClienteCreate):
    existente = db.query(Cliente).filter(Cliente.cedula == cliente.cedula).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe un cliente con esa cedula") # valida cedula unica antes de guardar
    db_cliente = Cliente(**cliente.dict())
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

def update_cliente(db: Session, cliente_id: int, cliente: ClienteUpdate):
    db_cliente = get_cliente(db, cliente_id)
    if not db_cliente:
        return None
    if cliente.cedula and cliente.cedula != db_cliente.cedula:
        existe = db.query(Cliente).filter(Cliente.cedula == cliente.cedula).first() # valida cedula unica antes de actualizar
        if existe:
            raise HTTPException(status_code= 400, detail="Ya existe un cliente con esa cedula")
    for key, value in cliente.dict(exclude_unset=True).items():
        setattr(db_cliente, key, value)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

def delete_cliente(db: Session, cliente_id: int):
    db_cliente = get_cliente(db, cliente_id)
    if db_cliente:
        db_cliente.estado = "inactivo"  # soft-delete: preserva referencias historicas
        db.commit()
    return db_cliente