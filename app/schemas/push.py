# app/schemas/push.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    """Acepta la forma anidada {endpoint, keys:{...}} y la plana {endpoint, p256dh, auth}."""

    endpoint: str
    keys: Optional[PushSubscriptionKeys] = None
    p256dh: Optional[str] = None
    auth: Optional[str] = None

    @model_validator(mode="after")
    def unificar_forma(self) -> "PushSubscriptionCreate":
        if self.keys is None:
            if not self.p256dh or not self.auth:
                raise ValueError("Se requiere 'keys' o los campos planos 'p256dh' y 'auth'")
            self.keys = PushSubscriptionKeys(p256dh=self.p256dh, auth=self.auth)
        return self


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