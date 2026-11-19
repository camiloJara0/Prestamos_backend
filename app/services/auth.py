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


def _parametro_int(db: Session, clave: str, default: int) -> int:
    """Lectura de un parámetro global de configuración como entero."""
    try:
        from app.services.configuracion import resolver_parametro

        valor, _ = resolver_parametro(db, clave, str(default))
        return int(valor) if valor is not None else default
    except (TypeError, ValueError):
        return default


def _contexto_auditoria(ip_address, user_agent, request_id) -> dict:
    return {
        "ip_address": ip_address,
        "user_agent": user_agent,
        "request_id": request_id,
    }


def login_usuario(
    db: Session,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> dict:
    # Rate limit por IP + correo (RF de fuerza bruta). Los intentos
    # bloqueados también quedan auditados.
    from app.services.rate_limit import verificar_rate_limit

    max_intentos = _parametro_int(db, "login_max_intentos", 10)
    ventana_min = _parametro_int(db, "login_ventana_min", 15)
    try:
        verificar_rate_limit(
            f"login:{ip_address or 'sin-ip'}:{email.lower()}",
            maximo=max_intentos,
            ventana_segundos=ventana_min * 60,
        )
    except HTTPException:
        from app.services.auditoria import registrar_auditoria

        registrar_auditoria(
            db,
            tabla_afectada="usuarios",
            tipo_operacion="login_bloqueado",
            descripcion=f"Rate limit de login superado: {email}",
            resultado="fallido",
            **_contexto_auditoria(ip_address, user_agent, request_id),
        )
        raise

    usuario = (
        db.query(Usuario)
        .filter(Usuario.email == email, Usuario.estado == "activo")
        .first()
    )

    if not usuario or not verify_password(password, usuario.hashed_password):
        from app.services.auditoria import registrar_auditoria

        registrar_auditoria(
            db,
            tabla_afectada="usuarios",
            tipo_operacion="login_fallido",
            usuario_id=usuario.id if usuario else None,
            registro_id=usuario.id if usuario else None,
            descripcion=f"Credenciales incorrectas o usuario inactivo: {email}",
            resultado="fallido",
            **_contexto_auditoria(ip_address, user_agent, request_id),
        )
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
        ip_address=ip_address,
        user_agent=(user_agent or None) and str(user_agent)[:255],
    )
    db.add(db_token)
    # Primero se persiste la credencial NUEVA: cualquier fallo posterior deja
    # al usuario con una sesión válida.
    db.commit()
    db.refresh(db_token)

    # Política de sesiones: conservar las N activas más recientes (la nueva
    # siempre está entre ellas) y purgar tokens expirados de este usuario.
    revocadas = _limitar_sesiones(db, usuario.id, sesiones_maximas=_parametro_int(db, "sesiones_maximas", 5))

    from app.services.auditoria import registrar_auditoria

    if revocadas:
        registrar_auditoria(
            db,
            tabla_afectada="tokens",
            tipo_operacion="revocacion_sesiones",
            usuario_id=usuario.id,
            registro_id=db_token.id,
            descripcion=f"{revocadas} sesiones anteriores revocadas por límite de sesiones",
            resultado="ok",
            **_contexto_auditoria(ip_address, user_agent, request_id),
        )
    registrar_auditoria(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="login",
        usuario_id=usuario.id,
        registro_id=usuario.id,
        descripcion=f"Inicio de sesión exitoso: {email}",
        resultado="ok",
        **_contexto_auditoria(ip_address, user_agent, request_id),
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def _limitar_sesiones(db: Session, usuario_id: int, sesiones_maximas: int = 5) -> int:
    """Purga tokens expirados y revoca activos que excedan el límite.

    Devuelve el número de sesiones revocadas. La sesión recién creada nunca
    se revoca (es la más reciente).
    """
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    eliminados = (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id, Token.expires_at < ahora)
        .delete(synchronize_session=False)
    )

    activos = (
        db.query(Token)
        .filter(Token.usuario_id == usuario_id, Token.activo == 1)
        .order_by(Token.created_at.desc(), Token.id.desc())
        .all()
    )
    excedentes = activos[max(int(sesiones_maximas), 1):]
    revocadas = 0
    for token in excedentes:
        token.activo = 0
        revocadas += 1
    db.commit()
    if eliminados:
        # Solo informativo; no se registran valores de tokens.
        pass
    return revocadas


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
    db_token.ultimo_uso_at = datetime.utcnow()
    db.commit()

    return {"access_token": nuevo_access_token, "token_type": "bearer"}


def logout_usuario(
    db: Session,
    refresh_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> bool:
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
        usuario_id = db_token.usuario_id
        db_token.activo = 0
        db.commit()
        from app.services.auditoria import registrar_auditoria

        registrar_auditoria(
            db,
            tabla_afectada="usuarios",
            tipo_operacion="logout",
            usuario_id=usuario_id,
            registro_id=usuario_id,
            descripcion="Cierre de sesión",
            resultado="ok",
            **_contexto_auditoria(ip_address, user_agent, request_id),
        )
        return True
    return False


def cambiar_password(
    db: Session,
    usuario_id: int,
    password_actual: str,
    password_nuevo: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
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

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="cambio_password",
        usuario_id=usuario.id,
        registro_id=usuario.id,
        descripcion="Cambio de contraseña propio; sesiones anteriores revocadas",
        resultado="ok",
        **_contexto_auditoria(ip_address, user_agent, request_id),
    )
    return True


def solicitar_reset_password(
    db: Session,
    email: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> str:
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

    from app.services.auditoria import registrar_auditoria

    # Nunca se registra el valor del token.
    registrar_auditoria(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="solicitud_reset_password",
        usuario_id=usuario.id,
        registro_id=usuario.id,
        descripcion="Solicitud de restablecimiento de contraseña",
        resultado="ok",
        **_contexto_auditoria(ip_address, user_agent, request_id),
    )

    _enviar_correo_reset(usuario, reset_token)
    return mensaje_estandar


def _enviar_correo_reset(usuario: Usuario, reset_token: str) -> None:
    """Envía el enlace de restablecimiento por correo (RF-006)."""
    import os

    from app.services.email import enviar_correo

    base_url = (os.getenv("FRONTEND_URL") or "https://taskflow.ctsantaisabel.com").rstrip("/")
    enlace = f"{base_url}/restablecer?token={reset_token}"
    asunto = "Recupera tu contraseña de LoanSoft"
    texto = (
        f"Hola {usuario.nombre}, solicitaste restablecer tu contraseña. "
        f"Este enlace vence en 1 hora: {enlace}"
    )
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto;">
      <h2 style="color:#5B2D8E">Recuperación de contraseña</h2>
      <p>Hola <b>{usuario.nombre}</b>,</p>
      <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta LoanSoft.</p>
      <p><a href="{enlace}" style="background:#5B2D8E;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;display:inline-block">Restablecer contraseña</a></p>
      <p>Si el botón no funciona, copia este enlace en tu navegador:</p>
      <p style="word-break:break-all;color:#5B2D8E">{enlace}</p>
      <p>El enlace vence en <b>1 hora</b> y solo puede usarse una vez. Si no solicitaste este cambio, ignora este correo.</p>
    </div>
    """
    enviar_correo(usuario.email, asunto, html, texto_plano=texto)


def resetear_password(
    db: Session,
    token: str,
    new_password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> bool:
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

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="reset_password",
        usuario_id=usuario.id,
        registro_id=usuario.id,
        descripcion="Contraseña restablecida por enlace de recuperación; sesiones revocadas",
        resultado="ok",
        **_contexto_auditoria(ip_address, user_agent, request_id),
    )
    return True