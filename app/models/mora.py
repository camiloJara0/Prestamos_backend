from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from app.models._init_ import Base

class Mora(Base):
    __tablename__ = "moras"

    id = Column(Integer, primary_key=True, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    cuota_id = Column(Integer, ForeignKey("prestamo_cuotas.id"))
    fecha = Column(Date)
    valor = Column(Float)
    estado = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)