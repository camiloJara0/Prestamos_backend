from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

TipoRecordatorio = Literal["proximos", "vencidos"]


class DestinatarioOut(BaseModel):
    cuota_id: int
    prestamo_id: int
    cliente_id: int
    cliente_nombre: str
    telefono: str
    email: str
    numero_cuota: int
    monto: float
    fecha_vencimiento: date
    dias: int
    referencia: str


class DestinatariosOut(BaseModel):
    tipo: str
    dias: int
    total: int
    destinatarios: list[DestinatarioOut]


class RecordatorioPreviewOut(BaseModel):
    plantilla: str
    canal: str
    asunto: str
    cuerpo: str
    variables: list[str]
    destinatarios_total: int


class RecordatorioEnvioIn(BaseModel):
    tipo: TipoRecordatorio
    dias: int = Field(default=3, ge=1, le=30)
    plantilla_id: int


class RecordatorioEnvioOut(BaseModel):
    destinatarios: int
    enviados: int
    omitidos: int
    fallidos: int
