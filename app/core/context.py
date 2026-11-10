"""Contexto del usuario autenticado por request.

Se setea en `get_current_user` y permite (a) asignar el dueño `usuario_id`
automáticamente a los registros del dominio al crearlos y (b) filtrar las
consultas por usuario sin tener que cambiar la firma de cada servicio.
"""

from contextvars import ContextVar
from app.models import PrestamoCuota, Prestamo, Cliente, Pago

usuario_actual_id: ContextVar[int | None] = ContextVar("usuario_actual_id", default=None)
usuario_actual_rol: ContextVar[str | None] = ContextVar("usuario_actual_rol", default=None)


def limpiar_contexto() -> None:
    usuario_actual_id.set(None)
    usuario_actual_rol.set(None)


# def aplicar_filtro_usuario(query, modelo):
#     """Restringe una consulta SQLAlchemy al usuario actual (multiusuario).

#     - Admin: ve todos los registros (auditoría global).
#     - Usuario normal: solo sus propios registros (los que tienen usuario_id).
#       Los modelos sin usuario_id pero con dueño alternativo (p. ej.
#       SolicitudPrestamo.usuario_creador_id) también quedan cubiertos.
#     - Sin contexto (jobs internos, seed): sin filtro.
#     """
#     uid = usuario_actual_id.get()
#     rol = usuario_actual_rol.get()
#     if rol == "admin" or not uid:
#         return query
#     columna = getattr(modelo, "usuario_id", None) or getattr(modelo, "usuario_creador_id", None)
#     if columna is not None:
#         return query.filter(columna == uid)
#     return query

FILTROS_RELACIONADOS = {
    PrestamoCuota: (Prestamo, PrestamoCuota.prestamo_id, Prestamo.id),
    Pago: (Prestamo, Pago.prestamo_id, Prestamo.id),
}

def aplicar_filtro_usuario(query, modelo):
    uid = usuario_actual_id.get()
    rol = usuario_actual_rol.get()

    if rol == "admin" or not uid:
        return query

    columna = (
        getattr(modelo, "usuario_id", None)
        or getattr(modelo, "usuario_creador_id", None)
    )

    if columna is not None:
        return query.filter(columna == uid)

    if modelo in FILTROS_RELACIONADOS:
        padre, fk_hijo, pk_padre = FILTROS_RELACIONADOS[modelo]

        return (
            query.join(padre, fk_hijo == pk_padre)
                 .filter(padre.usuario_id == uid)
        )

    return query
