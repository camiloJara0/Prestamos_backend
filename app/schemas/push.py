# app/schemas/push.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class PushSubscriptionResponse(BaseModel):
    id: int
    usuario_id: int
    endpoint: str
    created_at: datetime

    class Config:
        from_attributes = True


class PushNotificationSend(BaseModel):
    titulo: str = Field(..., example="Recordatorio de Pago")
    mensaje: str = Field(
        ..., example="Tienes cuotas pendientes por vencer hoy."
    )
    url: Optional[str] = Field(default="/", example="/prestamos")