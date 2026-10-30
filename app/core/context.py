"""Contexto del usuario autenticado por request.

Se setea en `get_current_user` y permite (a) asignar el dueño `usuario_id`
automáticamente a los registros del dominio al crearlos y (b) filtrar las
consultas por usuario sin tener que cambiar la firma de cada servicio.
"""

from contextvars import ContextVar

usuario_actual_id: ContextVar[int | None] = ContextVar("usuario_actual_id", default=None)
usuario_actual_rol: ContextVar[str | None] = ContextVar("usuario_actual_rol", default=None)


def limpiar_contexto() -> None:
    usuario_actual_id.set(None)
    usuario_actual_rol.set(None)


def aplicar_filtro_usuario(query, modelo):
    """Restringe una consulta SQLAlchemy al usuario actual (multiusuario).

    - Admin: ve todos los registros (auditoría global).
    - Usuario normal: solo sus propios registros (los que tienen usuario_id).
    - Sin contexto (jobs internos, seed): sin filtro.
    """
    uid = usuario_actual_id.get()
    rol = usuario_actual_rol.get()
    if rol == "admin" or not uid:
        return query
    if hasattr(modelo, "usuario_id"):
        return query.filter(modelo.usuario_id == uid)
    return query
