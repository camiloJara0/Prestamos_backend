from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.dependencies.auth import get_current_user, get_db, get_usuario_id, require_rol
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


@router.get("/metricas")
def metricas_envios(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin", "prestamista")),
):
    """RF-079: totales de envíos por canal, estado y plantilla en el periodo"""
    return plantillas_service.get_metricas_envios(db, desde=desde, hasta=hasta)


@router.get("/envios")
def historial_envios(
    plantilla_id: Optional[int] = Query(None),
    canal: Optional[str] = Query(None),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin", "prestamista")),
):
    """RF-079: historial reciente de envíos para auditar la comunicación"""
    return plantillas_service.get_envios(
        db, plantilla_id=plantilla_id, canal=canal, desde=desde, hasta=hasta, limit=limit
    )


@router.get("/variables")
def variables_disponibles(
    current_user: dict = Depends(get_current_user),
):
    """Catálogo de variables dinámicas agrupadas por categoría, con
    descripción y ejemplo renderizado (panel de ayuda del editor)."""
    from app.services.plantillas import catalogo_variables

    return catalogo_variables()


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
    current_user: dict = Depends(require_rol("admin", "prestamista")),
):
    plantilla = plantillas_service.crear_plantilla(db, datos)
    registrar_auditoria(
        db,
        usuario_id=get_usuario_id(current_user),
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
    current_user: dict = Depends(require_rol("admin", "prestamista")),
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
        usuario_id=get_usuario_id(current_user),
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
    current_user: dict = Depends(require_rol("admin", "prestamista")),
):
    plantilla = plantillas_service.get_plantilla(db, plantilla_id)
    nombre = plantilla.nombre
    plantillas_service.eliminar_plantilla(db, plantilla_id)
    registrar_auditoria(
        db,
        usuario_id=get_usuario_id(current_user),
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
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return plantillas_service.previsualizar(
        db, datos.clave, datos.canal, datos.cuerpo, datos.asunto, datos.contexto
    )
