from fastapi import FastAPI
from app.routes import clientes, tipo_prestamo
from app.db.database import init_db

app = FastAPI()
init_db()

@app.get("/")
def read_root():
    return {"mensaje": "Hola FastAPI"}

app.include_router(clientes.router)
app.include_router(tipo_prestamo.router)



