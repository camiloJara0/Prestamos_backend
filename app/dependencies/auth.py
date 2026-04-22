# Al usar Endpoint FastApi exige que traiga Token valido o no vencido en el header, sino devuelve 401

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.db.database import SessionLocal
from app.models.models import Token

bearer_scheme = HTTPBearer()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o vencido"
        )
    
    # Verifica que el token esté activo en la DB
    db_token = db.query(Token).filter(Token.access_token == token, Token.activo == 1).first()
    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalidado, inicia sesion nuevamente"
        )
    
    return payload

# requerimiento de rol superior, sirve en caso de querer restringir el acceso a ciertos endpoints a usuarios con roles específicos

def require_rol(rol_requerido: str):
    def verificar_rol(current_user: dict = Depends(get_current_user)):
        if current_user.get("rol") != rol_requerido:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado : no tienes permiso para realizar esta accion"
            )
        return current_user
    return verificar_rol