from .base import Base
from .clientes import Cliente
from .prestamo import Prestamo
from .pago import Pago
from .models import Usuario

# Exporta Base para que database.py pueda usarlo
from sqlalchemy.orm import declarative_base
Base = declarative_base()
