import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db
from app.services.scheduler import iniciar_scheduler, scheduler
from app.routes import (
    agenda,
    auditoria,
    auth,
    backoffice,
    campanas,
    capital,
    clientes,
    conciliacion,
    configuracion,
    dashboard,
    importacion,
    metodos_pago,  # <-- 1. Importamos el router de métodos de pago y QR
    mora,
    notificacion,
    onboarding,
    pago,
    pasarela,
    plantilla,
    prestamo,
    publico,
    push,
    recordatorio,
    reporte,
    solicitudes,
    tipo_pago,
    tipo_prestamo,
    usuarios,
    webhook_whatsapp,
    whatsapp,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    iniciar_scheduler()  # <-- Inicia el scheduler al arrancar la app
    yield
    scheduler.shutdown()  # <-- Detiene el scheduler limpiamente al apagar la app
    # Vuelca las métricas acumuladas en memoria antes de morir.
    try:
        from app.core.observabilidad import volcar_metricas
        from app.db.database import SessionLocal

        db = SessionLocal()
        try:
            volcar_metricas(db)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - el cierre nunca debe fallar
        pass


app = FastAPI(lifespan=lifespan, title="Sistema de Préstamos")

# Lista de orígenes permitidos para CORS: el origen real del frontend más los
# orígenes de desarrollo local. RF-074: sin comodín "*" en el entorno productivo.
allowed_origins = [
    "http://localhost:3001",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://taskflow.ctsantaisabel.com",
    "https://loansoft.netlify.app",
]

frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Contexto de usuario por request (aislamiento multiusuario). Debe ir después
# de CORS para que el token ya esté disponible en las cabeceras.
from app.core.middleware import ContextoUsuarioMiddleware

app.add_middleware(ContextoUsuarioMiddleware)

# Backoffice: request-id de correlación + métricas de peticiones/latencia.
# Se registra el último (externo) para heredar el ContextVar a toda la request.
from app.core.observabilidad import ObservabilidadMiddleware, capturar_excepcion

app.add_middleware(ObservabilidadMiddleware)


# ---------------------------------------------------------------------------
# Backoffice: captura de errores (5xx) en `errores_app`. Mejor esfuerzo:
# registrar el incidente nunca altera la respuesta original.
# ---------------------------------------------------------------------------
from fastapi import HTTPException
from fastapi.responses import JSONResponse


@app.exception_handler(Exception)
async def handler_excepcion_global(request: Request, exc: Exception):
    capturar_excepcion(request, exc)
    request_id = None
    try:
        from app.core.observabilidad import obtener_request_id

        request_id = obtener_request_id()
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Error interno del servidor.",
            "request_id": request_id,
        },
    )


@app.exception_handler(HTTPException)
async def handler_http_exception(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        capturar_excepcion(request, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )

# RF-074 · Cabeceras de seguridad y política de contenidos.
CABECERAS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# Política estricta para las respuestas de la API (JSON/ archivos).
CSP_API = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'self'; report-uri /csp-report"
)

# Swagger UI carga sus recursos desde CDN en el navegador.
CSP_DOCS = (
    "default-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "frame-ancestors 'none'; report-uri /csp-report"
)

RUTAS_DOCUMENTACION = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def cabeceras_seguridad(request, call_next):
    respuesta = await call_next(request)

    # Las respuestas con datos sensibles no se almacenan en caché.
    respuesta.headers["Cache-Control"] = "no-store"

    for cabecera, valor in CABECERAS_SEGURIDAD.items():
        respuesta.headers[cabecera] = valor

    if request.url.path.startswith(RUTAS_DOCUMENTACION):
        respuesta.headers["Content-Security-Policy"] = CSP_DOCS
    else:
        respuesta.headers["Content-Security-Policy"] = CSP_API

    return respuesta


@app.post("/csp-report", status_code=204, include_in_schema=False)
async def recibir_reporte_csp(request: Request):
    """RF-074: registra las violaciones de la política de contenidos."""
    try:
        reporte = await request.json()
    except Exception:
        reporte = {}
    print(f"[CSP] Violacion reportada: {reporte}")
    return Response(status_code=204)


@app.get("/")
def read_root():
    return {"mensaje": "Hola FastAPI"}


# Registro de Routers
app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(clientes.router)
app.include_router(tipo_prestamo.router)
app.include_router(capital.router)
app.include_router(prestamo.router)
app.include_router(tipo_pago.router)
app.include_router(pago.router)
app.include_router(mora.router)
app.include_router(reporte.router)
app.include_router(auditoria.router)
app.include_router(notificacion.router)
app.include_router(recordatorio.router)
app.include_router(push.router)
app.include_router(dashboard.router)
app.include_router(configuracion.router)
app.include_router(conciliacion.router)
app.include_router(metodos_pago.router)
# Routers públicos (RF-081): deben registrarse antes de /solicitudes para que
# /solicitudes/simular no caiga en /solicitudes/{solicitud_id}.
app.include_router(publico.router_planes)
app.include_router(publico.router_simulacion)
app.include_router(publico.router_solicitud)
app.include_router(publico.router_landing)
app.include_router(solicitudes.router)
app.include_router(solicitudes.router_contratos)
app.include_router(plantilla.router)
app.include_router(pasarela.router)
app.include_router(agenda.router)
app.include_router(agenda.router_prestamos)
app.include_router(campanas.router)
app.include_router(importacion.router)
app.include_router(onboarding.router)

# Backoffice (consola interna): routers con permisos propios.
for _router in backoffice.routers:
    app.include_router(_router)

app.include_router(whatsapp.router)
# Webhook público de WhatsApp Business API (sin auth: verificación de Meta)
app.include_router(webhook_whatsapp.router)