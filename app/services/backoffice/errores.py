"""Monitor de errores de la aplicación (Backoffice)."""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import ErroresApp, Usuario
from app.utils.pagination import paginate


def listar_errores(
    db: Session,
    page: int = 1,
    limit: int = 10,
    estado: Optional[str] = None,
    origen: Optional[str] = None,
    nivel: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    q: Optional[str] = None,
) -> dict:
    query = db.query(ErroresApp)
    if estado:
        query = query.filter(ErroresApp.estado == estado)
    if origen:
        query = query.filter(ErroresApp.origen == origen)
    if nivel:
        query = query.filter(ErroresApp.nivel == nivel)
    if desde:
        query = query.filter(ErroresApp.ultima_ocurrencia >= desde)
    if hasta:
        query = query.filter(ErroresApp.ultima_ocurrencia <= hasta)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (ErroresApp.mensaje.ilike(like))
            | (ErroresApp.endpoint.ilike(like))
            | (ErroresApp.tipo_exception.ilike(like))
            | (ErroresApp.request_id.ilike(like))
        )
    query = query.order_by(ErroresApp.ultima_ocurrencia.desc())
    return paginate(query, page=page, limit=limit)


def obtener_error(db: Session, error_id: int) -> ErroresApp:
    error = db.query(ErroresApp).filter(ErroresApp.id == error_id).first()
    if not error:
        raise HTTPException(status_code=404, detail="Error no encontrado.")
    return error


def actualizar_error(
    db: Session,
    error_id: int,
    datos: dict,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> ErroresApp:
    error = obtener_error(db, error_id)
    cambios = {}

    if datos.get("estado") is not None and datos["estado"] != error.estado:
        cambios["estado"] = {"antes": error.estado, "despues": datos["estado"]}
        error.estado = datos["estado"]
        if datos["estado"] in ("resuelto", "ignorado"):
            error.fecha_resolucion = datetime.utcnow()
            error.responsable_id = datos.get("responsable_id") or admin_id
        else:
            error.fecha_resolucion = None

    if datos.get("resolucion") is not None:
        error.resolucion = datos["resolucion"]
        cambios["resolucion"] = "actualizada"

    if datos.get("responsable_id") is not None:
        error.responsable_id = datos["responsable_id"]

    db.commit()
    db.refresh(error)

    if cambios:
        from app.services.auditoria import registrar_auditoria

        registrar_auditoria(
            db,
            tabla_afectada="errores_app",
            tipo_operacion="gestion_error",
            usuario_id=admin_id,
            registro_id=error.id,
            valores_nuevos=cambios,
            descripcion=f"Error #{error.id} actualizado ({error.tipo_exception})",
            resultado="ok",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
    return error


def crear_error(
    db: Session,
    datos: dict,
    usuario_id: Optional[int] = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> ErroresApp:
    """Reporte de error (frontend o backend). Agrupa por fingerprint."""
    from app.core.observabilidad import (
        _version_app,
        calcular_fingerprint,
        normalizar_endpoint,
    )

    mensaje = str(datos.get("mensaje") or "")[:2000]
    endpoint = datos.get("endpoint")
    endpoint_norm = normalizar_endpoint(endpoint) if endpoint else None
    fingerprint = calcular_fingerprint(
        datos.get("origen", "frontend"),
        datos.get("tipo_exception", ""),
        mensaje,
        endpoint_norm,
    )
    ahora = datetime.utcnow()

    registro = (
        db.query(ErroresApp)
        .filter(ErroresApp.fingerprint == fingerprint, ErroresApp.estado == "abierto")
        .first()
    )
    if registro is None:
        registro = ErroresApp(
            origen=datos.get("origen", "frontend"),
            nivel=datos.get("nivel", "error"),
            tipo_exception=str(datos.get("tipo_exception") or "Desconocido")[:150],
            mensaje=mensaje,
            stack_trace=(datos.get("stack_trace") or None) and str(datos["stack_trace"])[:8000],
            endpoint=endpoint_norm,
            componente=(datos.get("componente") or None) and str(datos["componente"])[:200],
            metodo_http=datos.get("metodo_http"),
            status_code=datos.get("status_code"),
            usuario_id=usuario_id,
            ip_address=ip_address,
            user_agent=(user_agent or None) and str(user_agent)[:255],
            request_id=request_id,
            version=_version_app(),
            fingerprint=fingerprint,
            ocurrencias=1,
            primera_ocurrencia=ahora,
            ultima_ocurrencia=ahora,
            estado="abierto",
        )
        db.add(registro)
    else:
        registro.ocurrencias = (registro.ocurrencias or 0) + 1
        registro.ultima_ocurrencia = ahora
        registro.mensaje = mensaje
        if datos.get("stack_trace"):
            registro.stack_trace = str(datos["stack_trace"])[:8000]
        if request_id:
            registro.request_id = request_id
        if usuario_id is not None and registro.usuario_id is None:
            registro.usuario_id = usuario_id
    db.commit()
    db.refresh(registro)
    return registro


def conteos_por_estado(db: Session) -> dict:
    filas = (
        db.query(ErroresApp.estado, func.count(ErroresApp.id))
        .group_by(ErroresApp.estado)
        .all()
    )
    base = {"abierto": 0, "en_seguimiento": 0, "resuelto": 0, "ignorado": 0}
    for estado, conteo in filas:
        base[estado] = conteo
    return base


def _verificar_usuario(db: Session, usuario_id: Optional[int]) -> None:
    if usuario_id is None:
        return
    if not db.query(Usuario).filter(Usuario.id == usuario_id).first():
        raise HTTPException(status_code=404, detail="Responsable no encontrado.")
