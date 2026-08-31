import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.models.models import Token, Usuario


def login_usuario(db: Session, email: str, password: str) -> dict:
    usuario = (
        db.query(Usuario)
        .filter(Usuario.email == email, Usuario.estado == "activo")
        .first()
    )

    if not usuario or not verify_password(password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas o usuario inactivo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    data_token = {
        "sub": usuario.email,
        "id": usuario.id,
        "rol": getattr(usuario, "rol", "usuario"),
    }

    access_token = create_access_token(data=data_token)
    refresh_token = create_refresh_token(data=data_token)

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = ahora + timedelta(days=7)

    db_token = Token(
        usuario_id=usuario.id,
        access_token=access_token,
        refresh_token=refresh_token,
        activo=1,
        expires_at=expires_at,
    )
    db.add(db_token)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def refrescar_token(db: Session, refresh_token: str) -> dict:
    db_token = (
        db.query(Token)
        .filter(Token.refresh_token == refresh_token, Token.activo == 1)
        .first()
    )

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado.",
        )

    usuario = db.query(Usuario).filter(Usuario.id == db_token.usuario_id).first()
    if not usuario or usuario.estado != "activo":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no encontrado.",
        )

    data_token = {
        "sub": usuario.email,
        "id": usuario.id,
        "rol": getattr(usuario, "rol", "usuario"),
    }
    nuevo_access_token = create_access_token(data=data_token)

    db_token.access_token = nuevo_access_token
    db.commit()

    return {"access_token": nuevo_access_token, "token_type": "bearer"}


def logout_usuario(db: Session, refresh_token: str) -> bool:
    db_token = (
        db.query(Token)
        .filter(
            (Token.refresh_token == refresh_token)
            | (Token.access_token == refresh_token),
            Token.activo == 1,
        )
        .first()
    )

    if db_token:
        db_token.activo = 0
        db.commit()
        return True
    return False


def cambiar_password(
    db: Session, usuario_id: int, password_actual: str, password_nuevo: str
) -> bool:
    usuario = (
        db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.estado == "activo")
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado o inactivo.",
        )

    if not verify_password(password_actual, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta.",
        )

    usuario.hashed_password = get_password_hash(password_nuevo)

    # Invalidate old sessions for security
    db.query(Token).filter(
        Token.usuario_id == usuario.id, Token.activo == 1
    ).update({"activo": 0})

    db.commit()
    return True


def solicitar_reset_password(db: Session, email: str) -> str:
    usuario = (
        db.query(Usuario)
        .filter(Usuario.email == email, Usuario.estado == "activo")
        .first()
    )
    mensaje_estandar = "Si el correo está registrado, recibirás las instrucciones para restablecer tu contraseña."

    if not usuario:
        return mensaje_estandar

    reset_token = secrets.token_urlsafe(32)
    usuario.reset_token = reset_token

    ahora = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    usuario.reset_token_expires = ahora + timedelta(hours=1)

    db.commit()
    return mensaje_estandar


def resetear_password(db: Session, token: str, new_password: str) -> bool:
    ahora = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    usuario = db.query(Usuario).filter(Usuario.reset_token == token).first()

    if (
        not usuario
        or not usuario.reset_token_expires
        or usuario.reset_token_expires < ahora
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperación inválido o expirado.",
        )

    usuario.hashed_password = get_password_hash(new_password)
    usuario.reset_token = None
    usuario.reset_token_expires = None

    # Invalidate active tokens upon reset
    db.query(Token).filter(
        Token.usuario_id == usuario.id, Token.activo == 1
    ).update({"activo": 0})

    db.commit()
    return True