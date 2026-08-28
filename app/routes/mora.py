from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.services import mora as services
from app.schemas import mora as schemas
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/moras", tags=["Moras"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=list[schemas.MoraOut])
def listar_moras(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return services.get_moras(db, skip, limit)

@router.get("/prestamo/{prestamo_id}", response_model=list[schemas.MoraOut])
def moras_por_prestamo(prestamo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return services.get_moras_prestamo(db, prestamo_id)

@router.get("/{mora_id}", response_model=schemas.MoraOut)
def obtener_mora(mora_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_mora = services.get_mora(db, mora_id)
    if not db_mora:
        raise HTTPException(status_code=404, detail="Mora no encontrada")
    return db_mora

@router.put("/{mora_id}", response_model=schemas.MoraOut)
def actualizar_mora(mora_id: int, mora: schemas.MoraUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_mora = services.update_mora(db, mora_id, mora)
    if not db_mora:
        raise HTTPException(status_code=404, detail="Mora no encontrada")
    return db_mora

@router.delete("/{mora_id}")
def eliminar_mora(mora_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_mora = services.delete_mora(db, mora_id)
    if not db_mora:
        raise HTTPException(status_code=404, detail="Mora no encontrada")
    return {"mensaje": "Mora eliminada"}

# Manual temporalmente
@router.post("/procesar-moras")
def ejecutar_moras(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    moras = services.procesar_moras(db, tasa_diaria=0.01)
    return {"moras_actualizadas": [m.id for m in moras]}

from app.services.configuracion import (
    get_todas_configuraciones, 
    get_configuracion_por_clave, 
    actualizar_configuracion
)
from app.schemas.configuracion import ConfiguracionUpdate

# ... endpoints de mora que ya existen ...

# ========== ENDPOINTS DE CONFIGURACIÓN DEL SISTEMA ==========

@router.get("/config/todas")
def obtener_todas_configuraciones(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene todas las configuraciones activas del sistema"""
    configs = get_todas_configuraciones(db)
    return {
        "total": len(configs),
        "configuraciones": [
            {
                "id": c.id,
                "clave": c.clave,
                "valor": c.valor,
                "descripcion": c.descripcion,
                "tipo_valor": c.tipo_valor,
                "activo": c.activo
            }
            for c in configs
        ]
    }

@router.get("/config/{clave}")
def obtener_configuracion_por_clave(
    clave: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene una configuración específica por su clave"""
    config = get_configuracion_por_clave(db, clave)
    return {
        "id": config.id,
        "clave": config.clave,
        "valor": config.valor,
        "descripcion": config.descripcion,
        "tipo_valor": config.tipo_valor,
        "activo": config.activo
    }

@router.put("/config/{clave}")
def actualizar_config(
    clave: str,
    datos: ConfiguracionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Actualiza una configuración específica (solo admins)"""
    if current_user["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden modificar configuraciones")
    
    config = actualizar_configuracion(db, clave, datos)
    return {
        "id": config.id,
        "clave": config.clave,
        "valor": config.valor,
        "descripcion": config.descripcion,
        "tipo_valor": config.tipo_valor,
        "activo": config.activo,
        "mensaje": "Configuración actualizada exitosamente"
    }