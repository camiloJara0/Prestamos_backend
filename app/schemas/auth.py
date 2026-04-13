# Define forma de los datos que entran y salen. Pydantic los valida automaticamente.

from pydantic import BaseModel

class LoginRequest(BaseModel):
    email : str
    password : str

class TokenResponse(BaseModel):
    access_token : str
    token_type: str = "bearer"