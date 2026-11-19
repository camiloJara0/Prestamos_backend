"""Respaldos de base de datos (listado y ejecución manual).

Sin endpoint de restauración por API (§11 del plan): restaurar es
operación de línea de comandos con el archivo en el servidor.
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import EjecucionProceso


def _directorio():
    from app.services.backup import DIRECTORIO_RESPALDOS, RETENCION_RESPALDOS

    return DIRECTORIO_RESPALDOS, RETENCION_RESPALDOS


def listar_respaldos(db: Session) -> dict:
    directorio, retencion = _directorio()

    archivos = []
    if directorio.exists():
        for ruta in sorted(directorio.glob("*"), reverse=True):
            if not ruta.is_file():
                continue
            estado = ruta.stat()
            archivos.append(
                {
                    "nombre": ruta.name,
                    "tamano_bytes": estado.st_size,
                    "fecha": datetime.fromtimestamp(estado.st_mtime),
                }
            )

    ultima = (
        db.query(EjecucionProceso)
        .filter(EjecucionProceso.tarea == "respaldo_diario_bd")
        .order_by(EjecucionProceso.fecha_solicitud.desc())
        .first()
    )

    return {
        "items": archivos,
        "directorio": str(directorio),
        "retencion_dias": retencion,
        "ultimo_estado": ultima.estado if ultima else None,
        "ultimo_resultado": ultima.resultado if ultima else None,
        "ultimo_fin": ultima.fin if ultima else None,
    }


def crear_respaldo_manual(
    db: Session,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Dispara el job de respaldo (idempotente vía procesos.ejecutar_tarea)."""
    from app.services.backoffice.procesos import ejecutar_tarea

    resultado = ejecutar_tarea(
        db,
        job_id="respaldo_diario_bd",
        admin_id=admin_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        tabla_afectada="ejecuciones_proceso",
        tipo_operacion="respaldo_manual",
        usuario_id=admin_id,
        registro_id=resultado.get("ejecucion_id"),
        descripcion="Respaldo manual solicitado desde el Backoffice",
        resultado="ok",
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
    return resultado


def detalle_respaldos_directorio() -> Optional[str]:
    directorio, _ = _directorio()
    return str(directorio) if directorio.exists() else None
