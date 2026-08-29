from fastapi import FastAPI
from app.routes import clientes, tipo_prestamo, tipo_pago, pago, mora, capital, prestamo, reporte
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from app.db.database import init_db
from app.routes.auth import router as auth_router
from app.routes.auditoria import router as auditoria_router
import os

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

# Creamos una lista limpia de orígenes permitidos
allowed_origins = [
    "http://localhost:3001",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Si existe la variable de entorno, la sumamos a la lista
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins, # Usamos nuestra lista segura
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"mensaje": "Hola FastAPI"}

app.include_router(clientes.router)
app.include_router(tipo_prestamo.router)
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(capital.router)
app.include_router(prestamo.router)
app.include_router(tipo_pago.router)
app.include_router(pago.router)
app.include_router(mora.router)
app.include_router(reporte.router)
app.include_router(auditoria_router)