from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user, get_db, require_rol
from app.schemas.plantilla import (
    PlantillaCreate,
    PlantillaOut,
    PlantillaPreview,
    PlantillaPreviewOut,
    PlantillaUpdate,
)
from app.services import plantillas as plantillas_service
from app.services.auditoria import registrar_auditoria

router = APIRouter(prefix="/plantillas", tags=["Plantillas de mensajes"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/", response_model=list[PlantillaOut])
def listar_plantillas(
    canal: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return plantillas_service.get_plantillas(db, canal=canal)


@router.get("/{plantilla_id}", response_model=PlantillaOut)
def obtener_plantilla(
    plantilla_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return plantillas_service.get_plantilla(db, plantilla_id)


@router.post("/", response_model=PlantillaOut, status_code=201)
def crear_plantilla(
    datos: PlantillaCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    plantilla = plantillas_service.crear_plantilla(db, datos)
    registrar_auditoria(
        db,
        usuario_id=current_user.get("sub"),
        tabla_afectada="plantillas_mensaje",
        tipo_operacion="CREATE",
        registro_id=plantilla.id,
        valores_nuevos={"clave": plantilla.clave, "canal": plantilla.canal},
        descripcion=f"Plantilla '{plantilla.nombre}' creada",
        ip_address=_ip(request),
    )
    return plantilla


@router.put("/{plantilla_id}", response_model=PlantillaOut)
def actualizar_plantilla(
    plantilla_id: int,
    datos: PlantillaUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    anterior = plantillas_service.get_plantilla(db, plantilla_id)
    valores_anteriores = {
        "nombre": anterior.nombre,
        "asunto": anterior.asunto,
        "cuerpo": anterior.cuerpo,
        "activa": anterior.activa,
    }
    plantilla = plantillas_service.actualizar_plantilla(db, plantilla_id, datos)
    registrar_auditoria(
        db,
        usuario_id=current_user.get("sub"),
        tabla_afectada="plantillas_mensaje",
        tipo_operacion="UPDATE",
        registro_id=plantilla.id,
        valores_anteriores=valores_anteriores,
        valores_nuevos={
            "nombre": plantilla.nombre,
            "asunto": plantilla.asunto,
            "cuerpo": plantilla.cuerpo,
            "activa": plantilla.activa,
        },
        descripcion=f"Plantilla '{plantilla.nombre}' actualizada",
        ip_address=_ip(request),
    )
    return plantilla


@router.delete("/{plantilla_id}")
def eliminar_plantilla(
    plantilla_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    plantilla = plantillas_service.get_plantilla(db, plantilla_id)
    nombre = plantilla.nombre
    plantillas_service.eliminar_plantilla(db, plantilla_id)
    registrar_auditoria(
        db,
        usuario_id=current_user.get("sub"),
        tabla_afectada="plantillas_mensaje",
        tipo_operacion="DELETE",
        registro_id=plantilla_id,
        valores_anteriores={"nombre": nombre},
        descripcion=f"Plantilla '{nombre}' eliminada",
        ip_address=_ip(request),
    )
    return {"message": "Plantilla eliminada correctamente"}


@router.post("/previsualizar", response_model=PlantillaPreviewOut)
def previsualizar_plantilla(
    datos: PlantillaPreview,
    current_user: dict = Depends(get_current_user),
):
    return plantillas_service.previsualizar(
        datos.clave, datos.canal, datos.cuerpo, datos.asunto, datos.contexto
    )
