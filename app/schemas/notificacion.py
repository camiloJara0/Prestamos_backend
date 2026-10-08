from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional

# --- ESQUEMAS EXISTENTES (PUSH NOTIFICATIONS) ---

class PushSubscriptionCreate(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PushSubscriptionOut(BaseModel):
    id: int
    usuario_id: int
    endpoint: str

    class Config:
        from_attributes = True


# --- BANDEJA DE NOTIFICACIONES INTERNAS (RF-023) ---

class NotificacionOut(BaseModel):
    id: int
    titulo: str
    mensaje: str
    url: Optional[str] = None
    tipo: str
    leida: bool
    push_enviado: bool
    fecha: datetime

    class Config:
        from_attributes = True


class NotificacionCountOut(BaseModel):
    no_leidas: int


class PushNotificationPayload(BaseModel):
    title: str
    body: str
    icon: Optional[str] = None
    url: Optional[str] = None


# --- NUEVOS ESQUEMAS PARA RECORDATORIOS Y COBROS WHATSAPP ---

class RecordatorioCuotaResponse(BaseModel):
    cuota_id: int
    prestamo_id: int
    cliente_nombre: str
    cliente_telefono: str
    numero_cuota: int
    monto: float
    fecha_vencimiento: date
    dias_para_vencer: int
    referencia_pago: str
    mensaje_whatsapp: str
    whatsapp_url: str

    class Config:
        from_attributes = True