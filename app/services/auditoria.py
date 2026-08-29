from sqlalchemy.orm import Session
from app.models.models import Auditoria
from app.schemas.auditoria import AuditoriaCreate
from datetime import datetime
import json

def registrar_auditoria(
    db: Session,
    usuario_id: int,
    tabla_afectada: str,
    tipo_operacion: str,
    registro_id: int = None,
    valores_anteriores: dict = None,
    valores_nuevos: dict = None,
    descripcion: str = None,
    ip_address: str = None
):
    """Registra una entrada en la tabla auditoria"""
    
    auditoria = Auditoria(
        usuario_id=usuario_id,
        tabla_afectada=tabla_afectada,
        tipo_operacion=tipo_operacion,
        registro_id=registro_id,
        valores_anteriores=json.dumps(valores_anteriores) if valores_anteriores else None,
        valores_nuevos=json.dumps(valores_nuevos) if valores_nuevos else None,
        descripcion=descripcion,
        ip_address=ip_address,
        fecha=datetime.utcnow()
    )
    db.add(auditoria)
    db.commit()
    db.refresh(auditoria)
    return auditoria

def get_auditorias(db: Session, skip: int = 0, limit: int = 10):
    """Obtiene todas las entradas de auditoria"""
    return db.query(Auditoria).order_by(Auditoria.fecha.desc()).offset(skip).limit(limit).all()

def get_auditorias_por_usuario(db: Session, usuario_id: int, skip: int = 0, limit: int = 10):
    """Obtiene auditorias de un usuario específico"""
    return db.query(Auditoria).filter(Auditoria.usuario_id == usuario_id).order_by(Auditoria.fecha.desc()).offset(skip).limit(limit).all()

def get_auditorias_por_tabla(db: Session, tabla_afectada: str, skip: int = 0, limit: int = 10):
    """Obtiene auditorias de una tabla específica"""
    return db.query(Auditoria).filter(Auditoria.tabla_afectada == tabla_afectada).order_by(Auditoria.fecha.desc()).offset(skip).limit(limit).all()

def get_auditorias_por_operacion(db: Session, tipo_operacion: str, skip: int = 0, limit: int = 10):
    """Obtiene auditorias de un tipo de operación específico"""
    return db.query(Auditoria).filter(Auditoria.tipo_operacion == tipo_operacion).order_by(Auditoria.fecha.desc()).offset(skip).limit(limit).all()