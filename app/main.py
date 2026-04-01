from fastapi import FastAPI
from routers import clientes, tipo_prestamo


app = FastAPI()

@app.get("/")
def read_root():
    return {"mensaje": "Hola FastAPI"}

app.include_router(clientes.router)
app.include_router(tipo_prestamo.router)


