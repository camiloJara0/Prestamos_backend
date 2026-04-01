from .clientes import Cliente
from .prestamos import Prestamo
from .pagos import Pago

# Exporta Base para que database.py pueda usarlo
from sqlalchemy.orm import declarative_base
Base = declarative_base()
