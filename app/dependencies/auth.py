# Al usar Endpoint FastApi exige que traiga Token valido o no vencido en el header, sino devuelve 401

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from app.core.security import decode_token

bearer_scheme = HTTPBearer()

def get_current_user(credentials : HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        payload = decode_token(token)
        return payload
    except JWTError:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail="token invalido o vencido",
        )
    
# requerimiento de rol superior, sirve en caso de querer restringir el acceso a ciertos endpoints a usuarios con roles específicos

def require_rol(rol_requerido: str):
    def verificar_rol(current_user: dict = Depends(get_current_user)):
        if current_user.get("rol") != rol_requerido:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail= "Acceso denegado : no tienes permiso para realizar esta accion"
            )
        return current_user
    return verificar_rol