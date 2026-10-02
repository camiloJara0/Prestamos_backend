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
    """Actualiza una configuración existente validando tipo y rango del valor."""
    config = get_configuracion_por_clave(db, clave)
    config.valor = _validar_valor(config.tipo_valor, datos.valor)
    if datos.descripcion:
        config.descripcion = datos.descripcion
    db.commit()
    db.refresh(config)
    return config

def _validar_valor(tipo_valor: str, valor: str) -> str:
    """RF-011: los valores numéricos deben ser no negativos."""
    if tipo_valor in ("float", "int", "number"):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="El valor debe ser numérico.")
        if numero < 0:
            raise HTTPException(status_code=422, detail="El valor no puede ser negativo.")
        if tipo_valor == "int" and not numero.is_integer():
            raise HTTPException(status_code=422, detail="El valor debe ser un entero.")
    return valor

def crear_configuracion(db: Session, datos: ConfiguracionCreate):
    """Crea una nueva configuración"""
    config = ConfiguracionSistema(**datos.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config