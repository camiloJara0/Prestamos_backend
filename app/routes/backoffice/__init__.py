"""Routers del módulo Backoffice (consola interna de desarrolladores)."""

from app.routes.backoffice import (
    configuracion,
    dashboard,
    errores,
    procesos,
    respaldos,
    seguridad,
    usuarios,
)

routers = (
    dashboard.router,
    usuarios.router,
    errores.router,
    procesos.router,
    seguridad.router,
    respaldos.router,
    configuracion.router,
)

__all__ = ["routers"]
