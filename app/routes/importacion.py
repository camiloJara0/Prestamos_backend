"""Importación masiva de datos Excel/CSV: columnas, previsualización,
ejecución parcial y bitácora (Fase 4)."""

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.dependencies.auth import get_db, get_usuario_id, require_rol
from app.schemas.importacion import (
    ColumnasOut,
    ImportacionBitacoraOut,
    ImportacionResultado,
)
from app.services import importacion as service

router = APIRouter(prefix="/importaciones", tags=["Importaciones"])


@router.post("/columnas", response_model=ColumnasOut)
async def columnas_archivo(
    archivo: UploadFile = File(...),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Lee el archivo y expone columnas + valores únicos (mapeo/homologación)."""
    contenido = await archivo.read()
    return service.obtener_columnas(contenido, archivo.filename or "")


@router.post("/previsualizar", response_model=ImportacionResultado)
async def previsualizar(
    archivo: UploadFile = File(...),
    entidad: str = Form(...),
    mapeo_columnas: str = Form(...),
    mapeo_catalogos: str = Form("{}"),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Valida todas las filas contra la BD sin importar nada."""
    contenido = await archivo.read()
    return service.previsualizar(
        db, entidad, contenido, archivo.filename or "",
        json.loads(mapeo_columnas), json.loads(mapeo_catalogos),
    )


@router.post("/ejecutar", response_model=ImportacionResultado)
async def ejecutar(
    archivo: UploadFile = File(...),
    entidad: str = Form(...),
    mapeo_columnas: str = Form(...),
    mapeo_catalogos: str = Form("{}"),
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Importa las filas válidas de forma parcial y registra la bitácora."""
    contenido = await archivo.read()
    return service.ejecutar(
        db, entidad, contenido, archivo.filename or "",
        json.loads(mapeo_columnas), json.loads(mapeo_catalogos),
        usuario_id=get_usuario_id(usuario),
    )


@router.get("/", response_model=list[ImportacionBitacoraOut])
def bitacoras(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_rol("admin", "prestamista")),
):
    """Historial de importaciones ejecutadas (bitácora)."""
    return service.listar_bitacoras(db)
