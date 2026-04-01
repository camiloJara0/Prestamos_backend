from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from models._init_ import Base

class PrestamoRenovacion(Base):
    __tablename__ = "prestamos_renovaciones"

    id = Column(Integer, primary_key=True, index=True)
    prestamo_anterior_id = Column(Integer, ForeignKey("prestamos.id"))
    prestamo_nuevo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(Date)
    observaciones = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)