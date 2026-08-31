from pydantic import BaseModel
from typing import Optional


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


class PushNotificationPayload(BaseModel):
    title: str
    body: str
    icon: Optional[str] = None
    url: Optional[str] = None