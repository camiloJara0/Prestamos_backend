import json
from datetime import datetime
from typing import Optional, Union
from sqlalchemy.orm import Session
from app.models.models import Auditoria, Usuario


def registrar_auditoria(
    db: Session,
    tabla_afectada: str,
    tipo_operacion: str,
    usuario_id: Optional[Union[int, str]] = None,
    registro_id: Optional[int] = None,
    valores_anteriores: Optional[dict] = None,
    valores_nuevos: Optional[dict] = None,
    descripcion: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    """Registra una entrada en la tabla auditoria resolviendo el ID de forma segura."""
    id_numerico: Optional[int] = None

    if isinstance(usuario_id, str):
        if usuario_id.isdigit():
            id_numerico = int(usuario_id)
        else:
            usr = db.query(Usuario).filter(Usuario.email == usuario_id).first()
            if usr:
                id_numerico = usr.id
    elif isinstance(usuario_id, int):
        id_numerico = usuario_id

    auditoria = Auditoria(
        usuario_id=id_numerico,
        tabla_afectada=tabla_afectada,
        tipo_operacion=tipo_operacion,
        registro_id=registro_id,
        valores_anteriores=json.dumps(valores_anteriores) if valores_anteriores else None,
        valores_nuevos=json.dumps(valores_nuevos) if valores_nuevos else None,
        descripcion=descripcion,
        ip_address=ip_address,
        fecha=datetime.utcnow(),
    )
    db.add(auditoria)
    db.commit()
    db.refresh(auditoria)
    return auditoria


def get_auditorias(db: Session, page: int = 1, limit: int = 10):
    """Obtiene todas las entradas de auditoría con respuesta paginada (B11)."""
    query = db.query(Auditoria)
    total = query.count()
    offset = (page - 1) * limit
    items = query.order_by(Auditoria.fecha.desc()).offset(offset).limit(limit).all()
    pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit
    }


def get_auditorias_por_usuario(
    db: Session, usuario_id: int, page: int = 1, limit: int = 10
):
    """Obtiene auditorias de un usuario específico."""
    query = db.query(Auditoria).filter(Auditoria.usuario_id == usuario_id)
    total = query.count()
    offset = (page - 1) * limit
    items = query.order_by(Auditoria.fecha.desc()).offset(offset).limit(limit).all()
    pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit
    }


def get_auditorias_por_tabla(
    db: Session, tabla_afectada: str, page: int = 1, limit: int = 10
):
    """Obtiene auditorias de una tabla específica."""
    query = db.query(Auditoria).filter(Auditoria.tabla_afectada == tabla_afectada)
    total = query.count()
    offset = (page - 1) * limit
    items = query.order_by(Auditoria.fecha.desc()).offset(offset).limit(limit).all()
    pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit
    }


def get_auditorias_por_operacion(
    db: Session, tipo_operacion: str, page: int = 1, limit: int = 10
):
    """Obtiene auditorias de un tipo de operación específico."""
    query = db.query(Auditoria).filter(Auditoria.tipo_operacion == tipo_operacion)
    total = query.count()
    offset = (page - 1) * limit
    items = query.order_by(Auditoria.fecha.desc()).offset(offset).limit(limit).all()
    pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit
    }