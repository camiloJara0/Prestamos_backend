from sqlalchemy.orm import Session
from app.models.models import TipoPrestamo
from app.schemas.tipo_prestamo import TipoPrestamoCreate, TipoPrestamoUpdate
from app.core.context import aplicar_filtro_usuario
from app.utils.pagination import paginate

def get_tipo_prestamos(db: Session, page: int = 1, limit: int = 10):
    query = aplicar_filtro_usuario(db.query(TipoPrestamo), TipoPrestamo).filter(TipoPrestamo.estado == "activo")
    query = query.order_by(TipoPrestamo.id.asc())
    return paginate(query, page=page, limit=limit)

def get_tipo_prestamo(db: Session, tipo_prestamo_id: int):
    return aplicar_filtro_usuario(db.query(TipoPrestamo), TipoPrestamo).filter(TipoPrestamo.id == tipo_prestamo_id).first()

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
        db_tipo_prestamo.estado = "inactivo"  # soft-delete
        db.commit()
    return db_tipo_prestamo