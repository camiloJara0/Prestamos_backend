# Seed : crea datos de prueba predeterminados en la base de datos
# Ejecutar con: python -m app.db.seed

from app.db.database import SessionLocal, init_db
from app.models.models import Usuario, TipoPrestamo, Cliente
from app.core.security import hash_password
from app.services.capital import get_or_create_capital
from app.models.models import MovimientoCapital, Capital
from datetime import date

def seed():
    init_db()
    db = SessionLocal()

    try:
        # Usuario admin
        if not db.query(Usuario).filter(Usuario.email == "admin@test.com").first():
            usuario = Usuario(
                nombre="Administrador",
                email="admin@test.com",
                hashed_password=hash_password("123456"),
                rol="admin",
                estado="activo"
            )
            db.add(usuario)
            print("✓ Usuario admin creado")
        else:
            print("- Usuario admin ya existe")

        # Tipos de prestamo
        tipos = [
            {"nombre": "Préstamo Personal", "descripcion": "Préstamo para uso personal", "interes_mensual": 2.5, "max_cuotas": 12},
            {"nombre": "Préstamo Empresarial", "descripcion": "Préstamo para negocios", "interes_mensual": 2.0, "max_cuotas": 24},
            {"nombre": "Préstamo de Emergencia", "descripcion": "Préstamo rápido para emergencias", "interes_mensual": 3.0, "max_cuotas": 6},
        ]
        for t in tipos:
            if not db.query(TipoPrestamo).filter(TipoPrestamo.nombre == t["nombre"]).first():
                db.add(TipoPrestamo(**t, estado="activo"))
                print(f"✓ Tipo de préstamo '{t['nombre']}' creado")
            else:
                print(f"- Tipo de préstamo '{t['nombre']}' ya existe")

        # Cliente de prueba
        if not db.query(Cliente).filter(Cliente.cedula == "123456789").first():
            cliente = Cliente(
                nombre="Carlos Rodríguez",
                cedula="123456789",
                telefono="3001234567",
                direccion="Calle 123 #45-67",
                estado="activo"
            )
            db.add(cliente)
            print("✓ Cliente de prueba creado")
        else:
            print("- Cliente de prueba ya existe")

        db.commit()

        # Capital inicial
        capital = db.query(Capital).first()
        if not capital or capital.monto_total == 0:
            capital_inicial = Capital(monto_total=10000000.0)
            db.add(capital_inicial)
            movimiento = MovimientoCapital(
                tipo_movimiento="inversion",
                descripcion="Capital inicial de prueba",
                valor=10000000.0,
                fecha=date.today()
            )
            db.add(movimiento)
            db.commit()
            print("✓ Capital inicial de 10,000,000 creado")
        else:
            print("- Capital ya existe")

        print("\n✅ Seed completado exitosamente")
        print("   Email: admin@test.com")
        print("   Password: 123456")

    except Exception as e:
        db.rollback()
        print(f"❌ Error en seed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()