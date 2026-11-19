# Seeder del usuario administrador (Backoffice).
# Ejecutar con: python -m app.db.seed_admin
#
# Variables requeridas en .env:
#   ADMIN_EMAIL     - correo del administrador
#   ADMIN_PASSWORD  - contraseña en texto plano (se almacena hasheada)
# Variable opcional:
#   ADMIN_NOMBRE    - nombre visible (por defecto "Administrador")
#
# Reglas de seguridad:
#   - Nunca se crea una cuenta con contraseña por defecto hardcodeada.
#   - Si la cuenta ya existe NO se sobrescribe (no invalida sesiones ni
#     cambia credenciales de forma inesperada).
#   - Idempotente: se puede ejecutar tantas veces como sea necesario.

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def seed_admin() -> int:
    from app.db.database import SessionLocal, init_db
    from app.core.security import hash_password
    from app.models.models import Usuario

    email = (os.getenv("ADMIN_EMAIL") or "").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""

    if not email or not password:
        print(
            "[SEED-ADMIN] No se ejecutó: define ADMIN_EMAIL y ADMIN_PASSWORD "
            "en el archivo .env antes de crear el administrador."
        )
        return 1

    init_db()
    db = SessionLocal()
    try:
        existente = db.query(Usuario).filter(Usuario.email == email).first()
        if existente:
            print(f"[SEED-ADMIN] El usuario '{email}' ya existe; no se modifica.")
            return 0

        nombre = (os.getenv("ADMIN_NOMBRE") or "Administrador").strip()
        db.add(
            Usuario(
                nombre=nombre,
                email=email,
                hashed_password=hash_password(password),
                rol="admin",
                estado="activo",
            )
        )
        db.commit()
        print(f"[SEED-ADMIN] Administrador creado: {email}")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"[SEED-ADMIN] Error: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(seed_admin())
