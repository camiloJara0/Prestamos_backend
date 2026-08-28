from sqlalchemy.orm import Session
from app.models.models import ConfiguracionSistema
from app.schemas.configuracion import ConfiguracionCreate, ConfiguracionUpdate
from fastapi import HTTPException

def get_configuracion_por_clave(db: Session, clave: str):
    """Obtiene una configuración por su clave"""
    config = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == clave,
        ConfiguracionSistema.activo == True
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail=f"Configuración '{clave}' no encontrada")
    return config

def get_todas_configuraciones(db: Session):
    """Obtiene todas las configuraciones activas"""
    return db.query(ConfiguracionSistema).filter(ConfiguracionSistema.activo == True).all()

def actualizar_configuracion(db: Session, clave: str, datos: ConfiguracionUpdate):
    """Actualiza una configuración existente"""
    config = get_configuracion_por_clave(db, clave)
    config.valor = datos.valor
    if datos.descripcion:
        config.descripcion = datos.descripcion
    db.commit()
    db.refresh(config)
    return config

def crear_configuracion(db: Session, datos: ConfiguracionCreate):
    """Crea una nueva configuración"""
    config = ConfiguracionSistema(**datos.dict())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config