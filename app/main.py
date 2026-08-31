import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db
from app.services.scheduler import iniciar_scheduler, scheduler
from app.routes import (
    auditoria,
    auth,
    capital,
    clientes,
    dashboard,
    mora,
    notificacion,
    pago,
    prestamo,
    push,
    reporte,
    tipo_pago,
    tipo_prestamo,
    usuarios,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    iniciar_scheduler()  # <-- Inicia el scheduler al arrancar la app
    yield
    scheduler.shutdown()  # <-- Detiene el scheduler limpiamente al apagar la app


app = FastAPI(lifespan=lifespan, title="Sistema de Préstamos")

# Lista de orígenes permitidos para CORS
allowed_origins = [
    "http://localhost:3001",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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
)


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
app.include_router(push.router)
app.include_router(dashboard.router)