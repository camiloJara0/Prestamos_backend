# El endpoint /login recibe email y contraseña, busca el usuario en la BD, verifica la contraseña con bcrypt
# si todo esta correcto devuelve el token JWT y lo guarda en la base de datos
# el endpoint /logout invalida el token en la base de datos

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.db.database import SessionLocal
from app.models.models import Usuario, Token
from app.schemas.auth import LoginRequest, TokenResponse, TokenRefreshRequest, TokenRefreshResponse
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.dependencies.auth import get_current_user

router = APIRouter()
bearer_scheme = HTTPBearer()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == data.email).first()
    if not usuario or not verify_password(data.password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    access_token = create_access_token({"sub": usuario.email, "rol": usuario.rol})
    refresh_token = create_refresh_token({"sub": usuario.email, "rol": usuario.rol})

    # Guarda el token en la base de datos
    db_token = Token(
        usuario_id=usuario.id,
        access_token=access_token,
        refresh_token=refresh_token,
        activo=1,
        expires_at=datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    db.add(db_token)
    db.commit()

    return {"access_token": access_token, "refresh_token": refresh_token}

@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: Session = Depends(get_db)):
    token = credentials.credentials
    # Busca el token en la DB y lo invalida
    db_token = db.query(Token).filter(Token.access_token == token, Token.activo == 1).first()
    if not db_token:
        raise HTTPException(status_code=401, detail="Token no encontrado o ya invalidado")
    db_token.activo = 0
    db.commit()
    return {"mensaje": "Sesión cerrada correctamente"}

@router.get("/me")
def perfil(current_user: dict = Depends(get_current_user)):
    return {"usuario": current_user}

@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh(data: TokenRefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token invalido")
        
        # Verifica que el refresh token esté activo en la DB
        db_token = db.query(Token).filter(Token.refresh_token == data.refresh_token, Token.activo == 1).first()
        if not db_token:
            raise HTTPException(status_code=401, detail="Refresh token invalidado")
        
        nuevo_token = create_access_token({"sub": payload["sub"], "rol": payload["rol"]})
        
        # Actualiza el access token en la DB
        db_token.access_token = nuevo_token
        db_token.expires_at = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        db.commit()
        
        return {"access_token": nuevo_token}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Refresh token invalido o expirado")