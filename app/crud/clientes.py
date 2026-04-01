from sqlalchemy.orm import Session
from models.models import Cliente
from schemas.clientes import ClienteCreate, ClienteUpdate

def get_clientes(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Cliente).offset(skip).limit(limit).all()

def get_cliente(db: Session, cliente_id: int):
    return db.query(Cliente).filter(Cliente.id == cliente_id).first()

def create_cliente(db: Session, cliente: ClienteCreate):
    db_cliente = Cliente(**cliente.dict())
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

def update_cliente(db: Session, cliente_id: int, cliente: ClienteUpdate):
    db_cliente = get_cliente(db, cliente_id)
    if not db_cliente:
        return None
    for key, value in cliente.dict(exclude_unset=True).items():
        setattr(db_cliente, key, value)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

def delete_cliente(db: Session, cliente_id: int):
    db_cliente = get_cliente(db, cliente_id)
    if db_cliente:
        db.delete(db_cliente)
        db.commit()
    return db_cliente