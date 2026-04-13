from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from app.models._init_ import Base

class PrestamoPerdido(Base):
    __tablename__ = "prestamos_perdidos"

    id = Column(Integer, primary_key=True, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(Date)
    valor_perdido = Column(Float)
    motivo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)