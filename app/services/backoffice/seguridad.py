"""Seguridad del Backoffice: auditoría avanzada y accesos por usuario."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Auditoria, Token
from app.utils.pagination import paginate

# Tipos de evento del mapa "tipo → eventos concretos" (§11 del plan).
MAPA_EVENTOS = {
    "sesiones": [
        "login",
        "login_fallido",
        "login_bloqueado",
        "logout",
        "revocacion_sesion_admin",
        "rotacion_token",
    ],
    "usuarios": [
        "creacion_usuario",
        "modificacion_usuario",
        "suspension_usuario",
        "reactivacion_usuario",
        "restablecer_acceso",
        "solicitud_reset_password",
        "reset_password",
        "cambio_password",
    ],
    "sesion_admin": [
        "ejecucion_proceso",
        "reintento_proceso",
        "cancelacion_proceso",
        "gestion_error",
        "actualizacion_configuracion",
        "respaldo_manual",
    ],
}


def listar_auditoria(
    db: Session,
    page: int = 1,
    limit: int = 10,
    usuario_id: Optional[int] = None,
    tabla_afectada: Optional[str] = None,
    tipo_operacion: Optional[str] = None,
    resultado: Optional[str] = None,
    evento: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    q: Optional[str] = None,
) -> dict:
    query = db.query(Auditoria)
    if usuario_id is not None:
        query = query.filter(Auditoria.usuario_id == usuario_id)
    if tabla_afectada:
        query = query.filter(Auditoria.tabla_afectada == tabla_afectada)
    if tipo_operacion:
        query = query.filter(Auditoria.tipo_operacion == tipo_operacion)
    if resultado:
        query = query.filter(Auditoria.resultado == resultado)
    if evento:
        eventos = MAPA_EVENTOS.get(evento, [evento])
        query = query.filter(Auditoria.tipo_operacion.in_(eventos))
    if desde:
        query = query.filter(Auditoria.fecha >= desde)
    if hasta:
        query = query.filter(Auditoria.fecha <= hasta)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (Auditoria.descripcion.ilike(like))
            | (Auditoria.request_id.ilike(like))
        )
    query = query.order_by(Auditoria.fecha.desc())
    return paginate(query, page=page, limit=limit)


def accesos_usuario(
    db: Session,
    usuario_id: int,
    page: int = 1,
    limit: int = 20,
) -> dict:
    """Historial de accesos: tokens emitidos (sin valores) + eventos de sesión."""
    query = (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id)
        .order_by(Token.created_at.desc())
    )
    return paginate(query, page=page, limit=limit)


def sesiones_activas(db: Session, usuario_id: int) -> list[Token]:
    return (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id, Token.activo == 1)
        .order_by(Token.created_at.desc())
        .all()
    )


def eventos_por_tipo(db: Session) -> dict:
    """Conteo de eventos agrupados por tipo (para el panel de seguridad)."""
    from sqlalchemy import func

    filas = (
        db.query(Auditoria.tipo_operacion, func.count(Auditoria.id))
        .group_by(Auditoria.tipo_operacion)
        .all()
    )
    return {tipo: conteo for tipo, conteo in filas}
