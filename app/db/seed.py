# Seed : crea datos de prueba predeterminados en la base de datos
# Ejecutar con: python -m app.db.seed

from app.db.database import SessionLocal, init_db
from app.models.models import Usuario, TipoPrestamo, Cliente, MovimientoCapital, Capital, ConfiguracionSistema
from app.core.security import hash_password
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
            print("Usuario admin creado")
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
                print(f"Tipo de préstamo '{t['nombre']}' creado")
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
            print("Cliente de prueba creado")
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
            print("Capital inicial de 10,000,000 creado")
        else:
            print("- Capital ya existe")

        # Crear configuraciones del sistema
        configs = [
            {
                "clave": "tasa_mora_diaria",
                "valor": "0.5",
                "descripcion": "Porcentaje de mora diaria por cuota vencida",
                "tipo_valor": "float"
            },
            {
                "clave": "interes_minimo",
                "valor": "2.5",
                "descripcion": "Tasa de interés mínima por defecto para nuevos préstamos",
                "tipo_valor": "float"
            },
            {
                "clave": "dias_gracia_mora",
                "valor": "3",
                "descripcion": "Días de gracia antes de aplicar mora",
                "tipo_valor": "int"
            },
        ]
        for cfg in configs:
            if not db.query(ConfiguracionSistema).filter(ConfiguracionSistema.clave == cfg["clave"]).first():
                db.add(ConfiguracionSistema(**cfg))
                print(f"Configuración '{cfg['clave']}' creada")
            else:
                print(f"- Configuración '{cfg['clave']}' ya existe")

        db.commit()

        print("\nSeed completado exitosamente")
        print("   Email: admin@test.com")
        print("   Password: 123456")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Error en seed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()