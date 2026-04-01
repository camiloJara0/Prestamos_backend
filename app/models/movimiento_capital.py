from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from models._init_ import Base

class MovimientoCapital(Base):
    __tablename__ = "movimientos_capital"

    id = Column(Integer, primary_key=True, index=True)
    tipo_movimiento = Column(Enum("inversion", "retiro", "prestamo_otorgado", "pago_recibido", "perdida", name="tipo_movimiento"))
    descripcion = Column(Text)
    valor = Column(Float)
    fecha = Column(Date)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)