"""Observabilidad del Backoffice: request-id, métricas API y errores.

- Cada request recibe un `X-Request-ID` (correlación en respuestas, auditoría
  y errores). Se almacena en un ContextVar heredado por todo el árbol.
- Las peticiones se acumulan en un buffer en memoria y se vuelcan a
  `metricas_api` cada 60 s (y al apagar la app).
- Las excepciones no controladas y los 5xx se registran en `errores_app`
  agrupados por fingerprint. Jamás se guardan contraseñas, tokens ni
  secretos: los mensajes se truncan y se limpian valores sensibles.
"""

import hashlib
import re
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

INICIO_PROCESO = time.time()

# ---------------------------------------------------------------------------
# Métricas API (buffer en memoria -> volcado periódico a metricas_api)
# ---------------------------------------------------------------------------
_lock_metricas = threading.Lock()
_buffer_metricas: dict[tuple, list] = {}  # clave -> [conteo, suma_ms, max_ms]

# Patrón de segmentos numéricos/UUID para normalizar rutas (evita cardinalidad)
_SEGMENTO_ID = re.compile(r"/\d+|/[0-9a-fA-F-]{36}")
_VALORES_SENSIBLES = re.compile(
    r"(password|token|secret|authorization|api[_-]?key)\s*[\"':=]+\s*\S+",
    re.IGNORECASE,
)


def nuevo_request_id() -> str:
    return str(uuid.uuid4())


def obtener_request_id() -> Optional[str]:
    return request_id_ctx.get()


def normalizar_endpoint(path: str) -> str:
    """`/prestamos/12/cuotas/34` -> `/prestamos/{id}/cuotas/{id}`."""
    normalizado = _SEGMENTO_ID.sub("/{id}", path)
    if len(normalizado) > 200:
        normalizado = normalizado[:200]
    return normalizado


def registrar_peticion(endpoint: str, metodo: str, status_code: int, latencia_ms: float) -> None:
    """Agrega una petición al buffer (thread-safe)."""
    fecha_hora = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    clave = (fecha_hora, normalizar_endpoint(endpoint), metodo.upper(), int(status_code))
    with _lock_metricas:
        registro = _buffer_metricas.get(clave)
        if registro is None:
            _buffer_metricas[clave] = [1, float(latencia_ms), float(latencia_ms)]
        else:
            registro[0] += 1
            registro[1] += float(latencia_ms)
            registro[2] = max(registro[2], float(latencia_ms))


def volcar_metricas(db: Session) -> int:
    """Vuelca el buffer a `metricas_api` (merge por clave única). Devolve el nº de claves."""
    from app.models.models import MetricaApi

    with _lock_metricas:
        pendientes = dict(_buffer_metricas)
        _buffer_metricas.clear()

    for (fecha_hora, endpoint, metodo, status), (conteo, suma, maximo) in pendientes.items():
        fila = (
            db.query(MetricaApi)
            .filter(
                MetricaApi.fecha_hora == fecha_hora,
                MetricaApi.endpoint == endpoint,
                MetricaApi.metodo == metodo,
                MetricaApi.status_code == status,
            )
            .first()
        )
        if fila is None:
            db.add(
                MetricaApi(
                    fecha_hora=fecha_hora,
                    endpoint=endpoint,
                    metodo=metodo,
                    status_code=status,
                    conteo=conteo,
                    latencia_ms_suma=suma,
                    latencia_ms_max=maximo,
                )
            )
        else:
            fila.conteo += conteo
            fila.latencia_ms_suma += suma
            fila.latencia_ms_max = max(fila.latencia_ms_max, maximo)
    if pendientes:
        db.commit()
    return len(pendientes)


# ---------------------------------------------------------------------------
# Errores de la aplicación
# ---------------------------------------------------------------------------
def _limpiar_mensaje(mensaje: str) -> str:
    mensaje = _VALORES_SENSIBLES.sub(r"\1=[REDACTADO]", mensaje or "")
    mensaje = mensaje.replace("\x00", " ")
    return mensaje[:2000]


def calcular_fingerprint(origen: str, tipo: str, mensaje: str, endpoint: Optional[str]) -> str:
    base = "|".join(
        [
            origen,
            tipo or "",
            re.sub(r"\d+", "{n}", (mensaje or "")[:200]),
            endpoint or "",
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:64]


def _version_app() -> str:
    import os

    return os.getenv("APP_VERSION", "1.0.0")


def registrar_error(
    db: Session,
    *,
    origen: str,
    nivel: str,
    tipo_exception: str,
    mensaje: str,
    stack_trace: Optional[str] = None,
    endpoint: Optional[str] = None,
    componente: Optional[str] = None,
    metodo_http: Optional[str] = None,
    status_code: Optional[int] = None,
    usuario_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """Registra (o incrementa) un incidente agrupado por fingerprint."""
    from app.models.models import ErroresApp

    mensaje_limpio = _limpiar_mensaje(mensaje)
    fingerprint = calcular_fingerprint(origen, tipo_exception, mensaje_limpio, endpoint)
    ahora = datetime.utcnow()

    registro = (
        db.query(ErroresApp)
        .filter(ErroresApp.fingerprint == fingerprint, ErroresApp.estado == "abierto")
        .first()
    )
    if registro is None:
        registro = (
            db.query(ErroresApp)
            .filter(ErroresApp.fingerprint == fingerprint)
            .order_by(ErroresApp.ultima_ocurrencia.desc())
            .first()
        )
        if registro is not None and registro.estado in ("resuelto", "ignorado"):
            # Un incidente resuelto que reaparece se reabre como nueva fila.
            registro = None

    if registro is None:
        db.add(
            ErroresApp(
                origen=origen,
                nivel=nivel,
                tipo_exception=(tipo_exception or "Desconocido")[:150],
                mensaje=mensaje_limpio,
                stack_trace=(stack_trace or None) and str(stack_trace)[:8000],
                endpoint=(endpoint or None) and str(endpoint)[:200],
                componente=(componente or None) and str(componente)[:200],
                metodo_http=metodo_http,
                status_code=status_code,
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
        )
    else:
        registro.ocurrencias = (registro.ocurrencias or 0) + 1
        registro.ultima_ocurrencia = ahora
        registro.mensaje = mensaje_limpio
        if stack_trace:
            registro.stack_trace = str(stack_trace)[:8000]
        if status_code is not None:
            registro.status_code = status_code
        if request_id:
            registro.request_id = request_id
        if usuario_id is not None and registro.usuario_id is None:
            registro.usuario_id = usuario_id
    db.commit()


# ---------------------------------------------------------------------------
# Middleware ASGI: request-id + métricas de latencia/peticiones
# ---------------------------------------------------------------------------
class ObservabilidadMiddleware:
    """Asigna `X-Request-ID`, mide la latencia y acumula métricas.

    Debe registrar­se el último (externo a los demás middlewares) para que el
    ContextVar herede a todo el árbol de ejecución de la request.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = nuevo_request_id()
        token = request_id_ctx.set(request_id)
        method = str(scope.get("method", "") or "")
        path = str(scope.get("path", "") or "")
        inicio = time.perf_counter()
        estado = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                estado["status"] = message.get("status", 500)
                headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("ascii")))
                    message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latencia_ms = (time.perf_counter() - inicio) * 1000.0
            try:
                registrar_peticion(path, method, estado["status"], latencia_ms)
            except Exception:  # noqa: BLE001 - las métricas nunca rompen requests
                pass
            request_id_ctx.reset(token)


def capturar_excepcion(request, exc: BaseException) -> None:
    """Registra una excepción en `errores_app` sin jamás romper la respuesta.

    Mejor esfuerzo: si la escritura falla (p. ej. sesión SQL caída), se
    descarta y el error original continúa su curso.
    """
    try:
        import traceback

        from app.core.context import usuario_actual_id
        from app.db.database import SessionLocal

        path = str(getattr(request, "url", None) and request.url.path or "")
        headers = getattr(request, "headers", None) or {}
        client = getattr(request, "client", None)
        status_code = getattr(exc, "status_code", None)
        tipo = type(exc).__name__
        stack = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

        db = SessionLocal()
        try:
            registrar_error(
                db,
                origen="backend",
                nivel="error",
                tipo_exception=tipo,
                mensaje=str(exc) or tipo,
                stack_trace=stack,
                endpoint=normalizar_endpoint(path) if path else None,
                metodo_http=getattr(request, "method", None),
                status_code=int(status_code) if status_code else None,
                usuario_id=usuario_actual_id.get(),
                ip_address=client.host if client else None,
                user_agent=headers.get("user-agent"),
                request_id=obtener_request_id(),
            )
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass
