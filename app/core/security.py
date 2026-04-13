# Funciones : 
# hash_password encripta las contraseñas antes de guardarlas
# verify_password compara la contraseña ingresada por el usuario con el hash guardado en la base de datos
# create_access_token crea un token de acceso para autenticar al usuario
# decode_token accede al ticket y verifica su validez y que no haya expirado

from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = "f3b2a1c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password : str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password : str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data : dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes = ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm = ALGORITHM)

def decode_token(token : str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms = [ALGORITHM])