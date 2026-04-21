# El endpoint /login. recibe email y contraseña, busca el usuario en la BD, verifica la contraseña con bcrypt
# si todo esta correcto devuelve el token JWT

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.models import Usuario
from app.schemas.auth import LoginRequest, TokenResponse, TokenRefreshRequest, TokenRefreshResponse 
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.dependencies.auth import get_current_user

router = APIRouter()

def get_db():
    db = SessionLocal()
    try: 
        yield db
    finally:
        db.close()

@router.post("/login", response_model = TokenResponse)
def login(data : LoginRequest, db : Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == data.email).first()
    if not usuario or not verify_password(data.password, usuario.hashed_password):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Email o contraseña incorrectos"
        )
    access_token = create_access_token({"sub" : usuario.email, "rol" : usuario.rol})
    refresh_token = create_refresh_token({"sub" : usuario.email, "rol" : usuario.rol})

    return {"access_token" : access_token, "refresh_token" : refresh_token}

@router.get("/me")
def perfil (current_user : dict = Depends(get_current_user)):
    return {"usuario" : current_user}

@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh(data: TokenRefreshRequest):
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="token invalido")
        nuevo_token = create_access_token({"sub": payload["sub"], "rol": payload["rol"]})
        return {"access_token": nuevo_token}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Refresh token invalido o expirado")