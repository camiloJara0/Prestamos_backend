"""Gestión global de usuarios del Backoffice (visibilidad de plataforma)."""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permisos import permisos_de
from app.models.models import Auditoria, Cliente, Token, Usuario
from app.utils.pagination import paginate


def _ultimo_acceso_map(db: Session, ids: list[int]) -> dict:
    """Última actividad por usuario: max(auditoría, uso de token)."""
    if not ids:
        return {}
    aud = dict(
        db.query(Auditoria.usuario_id, func.max(Auditoria.fecha))
        .filter(Auditoria.usuario_id.in_(ids))
        .group_by(Auditoria.usuario_id)
        .all()
    )
    tok = dict(
        db.query(
            Token.usuario_id,
            func.max(func.coalesce(Token.ultimo_uso_at, Token.created_at)),
        )
        .filter(Token.usuario_id.in_(ids))
        .group_by(Token.usuario_id)
        .all()
    )
    resultado = {}
    for uid in ids:
        candidatos = [v for v in (aud.get(uid), tok.get(uid)) if v]
        resultado[uid] = max(candidatos) if candidatos else None
    return resultado


def listar_usuarios(
    db: Session,
    page: int = 1,
    limit: int = 10,
    q: Optional[str] = None,
    rol: Optional[str] = None,
    estado: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
) -> dict:
    query = db.query(Usuario)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (Usuario.nombre.ilike(like)) | (Usuario.email.ilike(like))
        )
    if rol:
        query = query.filter(Usuario.rol == rol)
    if estado:
        query = query.filter(Usuario.estado == estado)
    if desde:
        query = query.filter(Usuario.created_at >= desde)
    if hasta:
        query = query.filter(Usuario.created_at <= hasta)
    query = query.order_by(Usuario.id.asc())

    page_data = paginate(query, page=page, limit=limit)
    items = page_data["items"]
    ids = [u.id for u in items]

    sesiones = dict(
        db.query(Token.usuario_id, func.count(Token.id))
        .filter(Token.usuario_id.in_(ids) if ids else [0], Token.activo == 1)
        .group_by(Token.usuario_id)
        .all()
    )
    clientes = dict(
        db.query(Cliente.usuario_id, func.count(Cliente.id))
        .filter(
            Cliente.usuario_id.in_(ids) if ids else [0],
            Cliente.usuario_id.isnot(None),
        )
        .group_by(Cliente.usuario_id)
        .all()
    )
    actividad = _ultimo_acceso_map(db, ids)

    # Vista enriquecida (la paginación devuelve la lista base).
    enriquecidos = []
    for usuario in items:
        enriquecidos.append(
            {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "email": usuario.email,
                "rol": usuario.rol,
                "estado": usuario.estado,
                "created_at": usuario.created_at,
                "ultima_actividad": actividad.get(usuario.id),
                "sesiones_activas": int(sesiones.get(usuario.id, 0)),
                "clientes": int(clientes.get(usuario.id, 0)),
            }
        )
    page_data["items"] = enriquecidos
    return page_data


def detalle_usuario(db: Session, usuario_id: int) -> dict:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    sesiones = (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id, Token.activo == 1)
        .order_by(Token.created_at.desc())
        .limit(10)
        .all()
    )
    accesos = (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id)
        .order_by(Token.created_at.desc())
        .limit(20)
        .all()
    )
    eventos = (
        db.query(Auditoria)
        .filter(Auditoria.usuario_id == usuario_id)
        .order_by(Auditoria.fecha.desc())
        .limit(10)
        .all()
    )
    clientes = int(
        db.query(func.count(Cliente.id))
        .filter(Cliente.usuario_id == usuario_id)
        .scalar()
        or 0
    )
    actividad = _ultimo_acceso_map(db, [usuario_id]).get(usuario_id)

    return {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol": usuario.rol,
        "estado": usuario.estado,
        "created_at": usuario.created_at,
        "ultima_actividad": actividad,
        "sesiones_activas": len(sesiones),
        "clientes": clientes,
        "permisos": sorted(permisos_de(usuario.rol)),
        "accesos": accesos,
        "ultimos_eventos": eventos,
    }


def sesiones_activas(db: Session, usuario_id: int) -> list[Token]:
    return (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id, Token.activo == 1)
        .order_by(Token.created_at.desc())
        .all()
    )


def revocar_sesion(
    db: Session,
    usuario_id: int,
    token_id: int,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    token = (
        db.query(Token)
        .filter(Token.id == token_id, Token.usuario_id == usuario_id)
        .first()
    )
    if not token:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    if token.activo != 1:
        raise HTTPException(status_code=409, detail="La sesión ya estaba revocada.")

    token.activo = 0
    db.commit()

    from app.services.auditoria import registrar_auditoria

    # Nunca se registran valores de tokens.
    registrar_auditoria(
        db,
        tabla_afectada="tokens",
        tipo_operacion="revocacion_sesion_admin",
        usuario_id=admin_id,
        registro_id=token.id,
        descripcion=f"Sesión #{token.id} revocada del usuario #{usuario_id}",
        resultado="ok",
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


def _contexto(admin_id, ip_address, user_agent, request_id) -> dict:
    return {
        "usuario_id": admin_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "request_id": request_id,
    }


def suspender_usuario(
    db: Session,
    usuario_id: int,
    motivo: str,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if admin_id and usuario_id == admin_id:
        raise HTTPException(
            status_code=400,
            detail="Un administrador no puede desactivar su propia cuenta.",
        )
    if usuario.estado == "inactivo":
        raise HTTPException(status_code=409, detail="El usuario ya está suspendido.")

    from app.services.usuarios import _verificar_ultimo_admin

    _verificar_ultimo_admin(db, usuario, nuevo_estado="inactivo")

    usuario.estado = "inactivo"
    revocadas = (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id, Token.activo == 1)
        .update({"activo": 0}, synchronize_session=False)
    )
    db.commit()

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="suspension_usuario",
        registro_id=usuario.id,
        valores_anteriores={"estado": "activo"},
        valores_nuevos={"estado": "inactivo", "motivo": motivo},
        descripcion=f"Suspendido: {usuario.email}. Motivo: {motivo} ({revocadas} sesiones revocadas)",
        resultado="ok",
        **_contexto(admin_id, ip_address, user_agent, request_id),
    )


def reactivar_usuario(
    db: Session,
    usuario_id: int,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if usuario.estado == "activo":
        raise HTTPException(status_code=409, detail="El usuario ya está activo.")

    usuario.estado = "activo"
    db.commit()

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="reactivacion_usuario",
        registro_id=usuario.id,
        valores_anteriores={"estado": "inactivo"},
        valores_nuevos={"estado": "activo"},
        descripcion=f"Reactivado: {usuario.email}",
        resultado="ok",
        **_contexto(admin_id, ip_address, user_agent, request_id),
    )


def restablecer_acceso(
    db: Session,
    usuario_id: int,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> str:
    """Procedimiento seguro de restablecimiento: correo con enlace de una
    hora + revocación de sesiones. Nunca se setea una contraseña directa."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if usuario.estado != "activo":
        raise HTTPException(
            status_code=409,
            detail="Reactiva el usuario antes de restablecer su acceso.",
        )

    from app.services.auth import solicitar_reset_password

    mensaje = solicitar_reset_password(
        db,
        usuario.email,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )

    revocadas = (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id, Token.activo == 1)
        .update({"activo": 0}, synchronize_session=False)
    )
    db.commit()

    from app.services.auditoria import registrar_auditoria

    # _contexto aporta usuario_id/ip/ua/request_id (sin duplicar kwargs).
    registrar_auditoria(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="restablecer_acceso",
        registro_id=usuario.id,
        descripcion=(
            f"Acceso restablecido para {usuario.email}: enlace enviado y "
            f"{revocadas} sesiones revocadas"
        ),
        resultado="ok",
        **_contexto(admin_id, ip_address, user_agent, request_id),
    )
    return mensaje
