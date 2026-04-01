from sqlalchemy.orm import Session
from models.models import TipoPrestamo
from schemas.tipo_prestamo import TipoPrestamoCreate, TipoPrestamoUpdate

def get_tipo_prestamo(db: Session, skip: int = 0, limit: int = 10):
    return db.query(TipoPrestamo).offset(skip).limit(limit).all()

def get_tipo_prestamo(db: Session, tipo_prestamo_id: int):
    return db.query(TipoPrestamo).filter(TipoPrestamo.id == tipo_prestamo_id).first()

def create_tipo_prestamo(db: Session, tipo_prestamo: TipoPrestamoCreate):
    db_tipo_prestamo = TipoPrestamo(**tipo_prestamo.dict())
    db.add(db_tipo_prestamo)
    db.commit()
    db.refresh(db_tipo_prestamo)
    return db_tipo_prestamo

def update_tipo_prestamo(db: Session, tipo_prestamo_id: int, tipo_prestamo: TipoPrestamoUpdate):
    db_tipo_prestamo = get_tipo_prestamo(db, tipo_prestamo_id)
    if not db_tipo_prestamo:
        return None
    for key, value in tipo_prestamo.dict(exclude_unset=True).items():
        setattr(db_tipo_prestamo, key, value)
    db.commit()
    db.refresh(db_tipo_prestamo)
    return db_tipo_prestamo

def delete_tipo_prestamo(db: Session, tipo_prestamo_id: int):
    db_tipo_prestamo = get_tipo_prestamo(db, tipo_prestamo_id)
    if db_tipo_prestamo:
        db.delete(db_tipo_prestamo)
        db.commit()
    return db_tipo_prestamo