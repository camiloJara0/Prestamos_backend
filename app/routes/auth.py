from datetime import datetime

from fastapi import APIRouter, Depends, Request, status, HTTPException
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


def _contexto_request(request: Request) -> dict:
    """Metadatos de seguridad de la request para auditoría (IP/UA/correlación)."""
    from app.core.observabilidad import obtener_request_id

    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": obtener_request_id(),
    }


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Inicia sesión con email y password mediante JSON."""
    return auth_service.login_usuario(db, req.email, req.password, **_contexto_request(request))


@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh_token(req: TokenRefreshRequest, db: Session = Depends(get_db)):
    """Renueva el token de acceso usando un refresh token válido."""
    return auth_service.refrescar_token(db, req.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(req: TokenRefreshRequest, request: Request, db: Session = Depends(get_db)):
    """Invalida el token activo y cierra sesión."""
    auth_service.logout_usuario(db, req.refresh_token, **_contexto_request(request))
    return {"message": "Sesión cerrada correctamente."}


@router.get("/me")
def obtener_perfil(current_user: dict = Depends(get_current_user)):
    """Devuelve los datos del usuario autenticado."""
    return current_user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    req: ChangePasswordRequest,
    request: Request,
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
        password_nuevo=req.password_nuevo,
        **_contexto_request(request),
    )
    _notificar_cambio_password(db, usuario_id)
    return {"message": "Contraseña cambiada exitosamente."}


def _notificar_cambio_password(db, usuario_id):
    """RF-061: aviso por correo del cambio de contraseña; un fallo no revierte la operación."""
    try:
        from app.models.models import Usuario
        from app.services.canales import enviar_por_canal

        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            return
        enviar_por_canal(
            db,
            canal="email",
            destinatario=usuario.email,
            clave="password_cambiada",
            contexto={
                "nombre": usuario.nombre,
                "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
            },
        )
    except Exception:  # noqa: BLE001 - el fallo de correo no revierte el cambio
        pass


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Genera un token de recuperación de contraseña."""
    mensaje = auth_service.solicitar_reset_password(db, req.email, **_contexto_request(request))
    return {"message": mensaje}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(req: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Valida el token de recuperación y actualiza la contraseña."""
    auth_service.resetear_password(db, req.token, req.new_password, **_contexto_request(request))
    return {"message": "Contraseña actualizada exitosamente."}