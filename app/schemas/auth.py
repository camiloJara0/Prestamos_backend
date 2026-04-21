# Define forma de los datos que entran y salen. Pydantic los valida automaticamente.

from pydantic import BaseModel

class LoginRequest(BaseModel):
    email : str
    password : str

class TokenResponse(BaseModel):
    access_token : str
    refresh_token : str
    token_type: str = "bearer"

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"