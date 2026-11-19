"""Capa de permisos granular para el Backoffice (consola interna).

Los permisos son claves de código agrupadas por rol en un único mapa:
el rol `admin` (equipo interno) posee todos los permisos del Backoffice;
`prestamista` (empresa) y `usuario` no poseen ninguno — la información
global nunca es visible para clientes.

Esta capa es compatible con la autenticación existente: se compone con
`get_current_user` (JWT + tabla `tokens`) mediante `Depends`.
"""

from fastapi import Depends, HTTPException, status

from app.dependencies.auth import get_current_user

# ---------------------------------------------------------------------------
# Catálogo de permisos del Backoffice
# ---------------------------------------------------------------------------
PERMISOS_BACKOFFICE: set[str] = {
    "backoffice.acceso",
    "backoffice.dashboard.ver",
    "backoffice.usuarios.ver",
    "backoffice.usuarios.gestionar",
    "backoffice.usuarios.sesiones",
    "backoffice.errores.ver",
    "backoffice.errores.gestionar",
    "backoffice.procesos.ver",
    "backoffice.procesos.gestionar",
    "backoffice.seguridad.ver",
    "backoffice.respaldos.ver",
    "backoffice.respaldos.gestionar",
    "backoffice.config.ver",
    "backoffice.config.editar",
}

# Mapa rol -> permisos. Única fuente de verdad (backend). El frontend tiene
# un espejo en `shared/config/permisos.ts`.
PERMISOS_POR_ROL: dict[str, set[str]] = {
    "admin": set(PERMISOS_BACKOFFICE),
    "prestamista": set(),
    "usuario": set(),
}


def permisos_de(rol: str | None) -> set[str]:
    """Devuelve el conjunto de permisos efectivos de un rol."""
    if not rol:
        return set()
    return set(PERMISOS_POR_ROL.get(rol, set()))


def tiene_permiso(rol: str | None, permiso: str) -> bool:
    return permiso in permisos_de(rol)


def require_permiso(*permisos: str):
    """Dependencia: permite el paso solo si el rol posee TODOS los permisos.

    Ejemplos:
        require_permiso("backoffice.dashboard.ver")
        require_permiso("backoffice.usuarios.gestionar")
    """

    def verificar(current_user: dict = Depends(get_current_user)) -> dict:
        rol = current_user.get("rol")
        faltantes = [p for p in permisos if p not in permisos_de(rol)]
        if faltantes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado : no tienes permiso para realizar esta accion",
            )
        return current_user

    return verificar
