from typing import Optional
from pydantic import BaseModel, EmailStr

# --- Esquemas de Autenticación Básica ---

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Esquemas de Cambio y Recuperación de Contraseña  ---

class ChangePasswordRequest(BaseModel):
    password_actual: str
    password_nuevo: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class MessageResponse(BaseModel):
    message: str