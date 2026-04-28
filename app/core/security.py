# Funciones : 
# hash_password encripta las contraseñas antes de guardarlas
# verify_password compara la contraseña ingresada por el usuario con el hash guardado en la base de datos
# create_access_token crea un token de acceso firmado y encriptado para autenticar al usuario
# create_refresh_token crea un token de refresco firmado y encriptado de larga duracion
# decode_token desencripta y verifica la validez y expiracion del token

from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from jwcrypto import jwk, jwe
from jwcrypto.common import json_encode
from dotenv import load_dotenv
import os
import json

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

ENCRYPTION_KEY = jwk.JWK(kty="oct", k=SECRET_KEY[:43])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _encrypt_token(signed_token: str) -> str:
    token = jwe.JWE(
        signed_token.encode("utf-8"),
        json_encode({"alg": "A256KW", "enc": "A256CBC-HS512"})
    )
    token.add_recipient(ENCRYPTION_KEY)
    return token.serialize(compact=True)

def _decrypt_token(encrypted_token: str) -> str:
    token = jwe.JWE()
    token.deserialize(encrypted_token, key=ENCRYPTION_KEY)
    return token.payload.decode("utf-8")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    signed = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return _encrypt_token(signed)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    signed = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return _encrypt_token(signed)

def decode_token(token: str) -> dict:
    signed = _decrypt_token(token)
    return jwt.decode(signed, SECRET_KEY, algorithms=[ALGORITHM])