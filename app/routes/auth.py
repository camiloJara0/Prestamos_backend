from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.schemas.auth import (
    LoginRequest,
    ChangePasswordRequest,  # <--- Nuevo esquema importado
    ForgotPasswordRequest, 
    ResetPasswordRequest, 
    TokenResponse, 
    TokenRefreshRequest,
    TokenRefreshResponse,
    MessageResponse
)
from app.dependencies.auth import get_current_user
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Inicia sesión con email y password mediante JSON."""
    return auth_service.login_usuario(db, req.email, req.password)


@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh_token(req: TokenRefreshRequest, db: Session = Depends(get_db)):
    """Renueva el token de acceso usando un refresh token válido."""
    return auth_service.refrescar_token(db, req.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(req: TokenRefreshRequest, db: Session = Depends(get_db)):
    """Invalida el token activo y cierra sesión."""
    auth_service.logout_usuario(db, req.refresh_token)
    return {"message": "Sesión cerrada correctamente."}


@router.get("/me")
def obtener_perfil(current_user: dict = Depends(get_current_user)):
    """Devuelve los datos del usuario autenticado."""
    return current_user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    req: ChangePasswordRequest, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    """Permite al usuario autenticado cambiar su propia contraseña validando la actual."""
    # current_user contiene el payload del token ('id' o 'sub')
    usuario_id = current_user.get("id") or current_user.get("sub")
    auth_service.cambiar_password(
        db, 
        usuario_id=usuario_id, 
        password_actual=req.password_actual, 
        password_nuevo=req.password_nuevo
    )
    return {"message": "Contraseña cambiada exitosamente."}


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Genera un token de recuperación de contraseña."""
    mensaje = auth_service.solicitar_reset_password(db, req.email)
    return {"message": mensaje}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Valida el token de recuperación y actualiza la contraseña."""
    auth_service.resetear_password(db, req.token, req.new_password)
    return {"message": "Contraseña actualizada exitosamente."}