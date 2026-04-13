from fastapi import FastAPI
from app.routes import clientes, tipo_prestamo
from app.db.database import init_db
from app.routes.auth import router as auth_router

app = FastAPI()
init_db()

@app.get("/")
def read_root():
    return {"mensaje": "Hola FastAPI"}

app.include_router(clientes.router)
app.include_router(tipo_prestamo.router)
app.include_router(auth_router, prefix = "/auth", tags = ["Authentication"])


