"""Middleware ASGI que registra el usuario autenticado en el ContextVar.

FastAPI ejecuta dependencias síncronas y endpoints en copias separadas de
`contextvars`, por lo que un `ContextVar.set()` dentro de una dependencia no
llega al resto del request (ni a los eventos de SQLAlchemy como `before_flush`).
Al setearlo en un middleware ASGI (que corre en el contexto raíz de la request
ANTES del dispatch), el valor se hereda por todo el árbol de ejecución.
"""

from jose import JWTError

from app.core.security import decode_token
from app.core.context import usuario_actual_id, usuario_actual_rol


class ContextoUsuarioMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            headers = {
                k.decode("latin-1"): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            auth = headers.get("authorization", "")
            if auth.startswith("Bearer "):
                try:
                    payload = decode_token(auth[7:])
                except JWTError:
                    payload = None
                if payload:
                    uid = payload.get("id")
                    if uid is None:
                        sub = payload.get("sub")
                        uid = int(sub) if sub and str(sub).isdigit() else None
                    usuario_actual_id.set(uid)
                    usuario_actual_rol.set(payload.get("rol"))
        except Exception:  # noqa: BLE001 - el contexto nunca debe romper la request
            pass

        try:
            await self.app(scope, receive, send)
        finally:
            usuario_actual_id.set(None)
            usuario_actual_rol.set(None)
