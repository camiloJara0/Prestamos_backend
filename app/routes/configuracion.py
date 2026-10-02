from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.schemas.configuracion import ConfiguracionOut, ConfiguracionUpdate
from app.services.configuracion import (
    actualizar_configuracion,
    get_configuracion_por_clave,
    get_todas_configuraciones,
)
from app.services.auditoria import registrar_auditoria
from app.dependencies.auth import get_current_user, require_rol

router = APIRouter(prefix="/configuracion", tags=["Configuración"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=list[ConfiguracionOut])
def listar_configuraciones(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_todas_configuraciones(db)


@router.get("/{clave}", response_model=ConfiguracionOut)
def obtener_configuracion(
    clave: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_configuracion_por_clave(db, clave)


@router.put("/{clave}", response_model=ConfiguracionOut)
def modificar_configuracion(
    clave: str,
    datos: ConfiguracionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    anterior = get_configuracion_por_clave(db, clave)
    valor_anterior = anterior.valor
    config = actualizar_configuracion(db, clave, datos)
    registrar_auditoria(
        db,
        tabla_afectada="configuracion_sistema",
        tipo_operacion="UPDATE",
        usuario_id=current_user.get("sub"),
        registro_id=config.id,
        valores_anteriores={"valor": valor_anterior},
        valores_nuevos={"valor": config.valor},
        descripcion=f"Actualización del parámetro '{clave}'",
        ip_address=request.client.host if request.client else None,
    )
    return config
