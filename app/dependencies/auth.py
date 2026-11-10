# Al usar Endpoint FastApi exige que traiga Token valido o no vencido en el header, sino devuelve 401

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.core.context import usuario_actual_id, usuario_actual_rol
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

    # Registra el usuario actual en el contexto (aislamiento multiusuario).
    try:
        uid = payload.get("id")
        if uid is None:
            sub = payload.get("sub")
            uid = int(sub) if sub is not None and str(sub).isdigit() else None
        usuario_actual_id.set(uid)
        usuario_actual_rol.set(payload.get("rol"))
    except Exception:  # noqa: BLE001 - el contexto no debe romper la autenticación
        pass

    return payload

# requerimiento de rol superior, sirve en caso de querer restringir el acceso a ciertos endpoints a usuarios con roles específicos

def get_usuario_id(current_user: dict) -> int:
    """Extrae el id numérico del payload del token (sub es el email)."""
    if current_user.get("id") is not None:
        try:
            return int(current_user["id"])
        except (TypeError, ValueError):
            pass
    sub = current_user.get("sub")
    if sub is not None and str(sub).isdigit():
        return int(sub)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token sin identificador de usuario",
    )


def require_rol(*roles: str):
    """Permite el paso solo a los roles indicados.

    Ejemplos:
        require_rol("admin")                 -> solo administrador
        require_rol("admin", "prestamista")  -> equipo y prestamistas
    """
    def verificar_rol(current_user: dict = Depends(get_current_user)):
        if current_user.get("rol") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado : no tienes permiso para realizar esta accion"
            )
        return current_user
    return verificar_rol