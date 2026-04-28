from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from app.routes import clientes, tipo_prestamo, tipo_pago, pago
from app.db.database import init_db
from app.routes.auth import router as auth_router
from app.routes.capital import router as capital_router
from app.routes.prestamo import router as prestamo_router
from app.routes.reporte import router as reporte_router
import os

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "*")],
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
app.include_router(capital_router)
app.include_router(prestamo_router)
app.include_router(tipo_pago.router)
app.include_router(pago.router)
app.include_router(reporte_router)