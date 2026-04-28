from sqlalchemy.orm import Session
from app.db.database import engine, SessionLocal, init_db
from app.models.models import Usuario
from datetime import datetime
import bcrypt

def seed_usuario():
    # Inicializa la BD (crea tablas si no existen)
    init_db()

    db: Session = SessionLocal()

    # Verifica si ya existe un usuario admin
    usuario_existente = db.query(Usuario).filter_by(email="admin@admin.com").first()
    if usuario_existente:
        print("El usuario por defecto ya existe")
        return

    # Hashear la contraseña
    hashed_password = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Crear usuario por defecto
    usuario = Usuario(
        nombre="Administrador",
        email="admin@admin.com",
        hashed_password=hashed_password,
        rol="admin",
        estado="activo",
        created_at=datetime.utcnow()
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    print("Usuario por defecto creado:", usuario.email)

if __name__ == "__main__":
    seed_usuario()