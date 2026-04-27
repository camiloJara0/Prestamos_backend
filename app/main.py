from fastapi import FastAPI
from app.routes import clientes, tipo_prestamo, tipo_pago, pago
from app.db.database import init_db
from app.routes.auth import router as auth_router
from app.routes.capital import router as capital_router
from app.routes.prestamo import router as prestamo_router

app = FastAPI()
@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def read_root():
    return {"mensaje": "Hola FastAPI"}

app.include_router(clientes.router)
app.include_router(tipo_prestamo.router)
app.include_router(auth_router, prefix = "/auth", tags = ["Authentication"])
app.include_router(capital_router)
app.include_router(prestamo_router)
app.include_router(tipo_pago.router)
app.include_router(pago.router)


