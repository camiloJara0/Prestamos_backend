# Sistema de Gestión de Préstamos

Backend FastAPI para gestión integral de préstamos personales, pagos, moras y reportes financieros.

---

## Descripción

Aplicación backend profesional que proporciona una API REST completa para administrar préstamos personales. Incluye autenticación segura con JWT, cálculo automático de moras, generación de reportes financieros (JSON/Excel/PDF) y auditoría de cambios.

**Stack:** Python 3.10+ | FastAPI | SQLAlchemy | MySQL/SQLite | JWT

---

## Características Principales

| Funcionalidad | Descripción |
|---------------|------------|
| **Gestión de Préstamos** | Crear, renovar y marcar préstamos como perdidos |
| **Cuotas Automáticas** | Generación automática de cuotas con cálculos precisos |
| **Registro de Pagos** | Validación detallada de pagos con desglose capital/interés/mora |
| **Moras Automáticas** | Cálculo dinámico de moras con parámetros configurables |
| **Reportes Financieros** | Ganancias, pérdidas, cobranza, cartera (JSON/Excel/PDF) |
| **Autenticación JWT** | Encriptación JWE con tokens invalidables |
| **Auditoria** | Registro de cambios en operaciones críticas |
| **Configuración Dinámica** | Ajuste de parámetros sin reiniciar servidor |

---

## Requisitos

- Python 3.10+
- MySQL 5.7+ o SQLite (desarrollo)
- pip

---

## Instalación Rápida

```bash
# 1. Clonar
git clone https://github.com/camiloJara0/Prestamos_backend.git
cd Prestamos_backend

# 2. Entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate     # Windows

# 3. Dependencias
pip install -r requirements.txt

# 4. Configurar .env
# Ver sección "Configuración" más abajo

# 5. Inicializar BD
python -m app.db.seed

# 6. Ejecutar
uvicorn app.main:app --reload
```

**Servidor disponible en:** http://127.0.0.1:8000/docs

---

## Configuración

### Archivo `.env`

Crear en la raíz del proyecto:

```env
SECRET_KEY=tu-clave-secreta-muy-larga-cambiar-en-produccion
ENCRYPTION_KEY=clave-encriptacion-32-caracteres
DATABASE_URL=mysql+pymysql://usuario:password@localhost:3306/prestamos_db
FRONTEND_URL=http://localhost:3000
```

**Opciones de BD:**
- **MySQL:** `mysql+pymysql://user:pass@localhost:3306/prestamos_db`
- **SQLite:** `sqlite:///./prestamos.db`

---

## API Endpoints

### Autenticación
| Método | Endpoint | Descripción |
|--------|----------|------------|
| POST | `/auth/login` | Iniciar sesión |
| POST | `/auth/logout` | Cerrar sesión |
| POST | `/auth/refresh` | Renovar token |
| GET | `/auth/me` | Usuario actual |

### Préstamos
| Método | Endpoint | Descripción |
|--------|----------|------------|
| POST | `/prestamos` | Crear préstamo |
| GET | `/prestamos` | Listar préstamos |
| GET | `/prestamos/{id}` | Detalles completos |
| POST | `/prestamos/{id}/renovar` | Renovar préstamo |
| POST | `/prestamos/{id}/marcar_perdido` | Marcar como perdido |
| PUT | `/prestamos/{id}/ajustar-capital` | Ajustar capital (admin) |

### Pagos
| Método | Endpoint | Descripción |
|--------|----------|------------|
| POST | `/pagos` | Registrar pago |
| GET | `/pagos` | Listar pagos |

### Moras
| Método | Endpoint | Descripción |
|--------|----------|------------|
| GET | `/moras` | Listar moras |
| POST | `/moras/procesar-moras` | Calcular moras (admin) |

### Configuración (Admin)
| Método | Endpoint | Descripción |
|--------|----------|------------|
| GET | `/moras/config/todas` | Ver todas las configuraciones |
| GET | `/moras/config/{clave}` | Ver configuración específica |
| PUT | `/moras/config/{clave}` | Actualizar configuración |

**Parámetros configurables:**
- `tasa_mora_diaria` — Porcentaje diario de mora (default: 0.5)
- `interes_minimo` — Tasa mínima de interés (default: 2.5)
- `dias_gracia_mora` — Días antes de aplicar mora (default: 3)

### Reportes
| Método | Endpoint | Descripción |
|--------|----------|------------|
| GET | `/reportes/ganancias` | Reporte de ganancias (JSON) |
| GET | `/reportes/ganancias/excel` | Exportar Excel |
| GET | `/reportes/ganancias/pdf` | Exportar PDF |
| GET | `/reportes/perdidas` | Reporte de pérdidas (JSON) |
| GET | `/reportes/cobranza` | Estado de cuotas |
| GET | `/reportes/cartera` | Distribución de préstamos |

**Filtros:** `?desde=2026-08-01&hasta=2026-08-31`

### Auditoria (Admin)
| Método | Endpoint | Descripción |
|--------|----------|------------|
| GET | `/auditoria/` | Todas las auditorias |
| GET | `/auditoria/usuario/{id}` | Por usuario |
| GET | `/auditoria/tabla/{nombre}` | Por tabla |

---

## Autenticación

Todos los endpoints requieren token JWT (excepto `/auth/login`):

```bash
Authorization: Bearer <access_token>
```

**Flujo:**
1. POST `/auth/login` → Recibe `access_token` (60 min) + `refresh_token` (7 días)
2. Incluir token en header `Authorization: Bearer <token>`
3. Token expira → POST `/auth/refresh` → Nuevo token
4. POST `/auth/logout` → Invalida token

---

## Ejemplos

### Login
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "123456"
  }'
```

### Crear Préstamo
```bash
curl -X POST "http://localhost:8000/prestamos" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_id": 1,
    "tipo_prestamo_id": 1,
    "capital_prestado": 500000,
    "porcentaje_interes": 2.5,
    "numero_cuotas": 6
  }'
```

### Exportar Reporte
```bash
curl -X GET "http://localhost:8000/reportes/cartera?desde=2026-08-01&hasta=2026-08-31" \
  -H "Authorization: Bearer <token>" \
  -o reporte.xlsx
```

---

## Estructura del Proyecto

```
app/
├── main.py                      Configuración FastAPI
├── core/security.py             JWT y autenticación
├── db/database.py               Conexión a BD
├── db/seed.py                   Datos iniciales
├── models/models.py             13 tablas SQLAlchemy
├── schemas/                     Validación Pydantic
├── routes/                      Endpoints
├── services/                    Lógica de negocio
└── dependencies/auth.py         Autenticación
```

---

## Base de Datos

13 tablas SQLAlchemy:

- `usuarios` — Usuarios del sistema
- `tokens` — Tokens invalidados
- `capital` — Capital disponible
- `clientes` — Clientes
- `tipos_prestamo` — Tipos de préstamo
- `tipos_pago` — Métodos de pago
- `prestamos` — Préstamos otorgados
- `prestamo_cuotas` — Cuotas
- `pagos` — Pagos registrados
- `movimientos_capital` — Historial financiero
- `moras` — Moras calculadas
- `prestamos_renovaciones` — Renovaciones
- `prestamos_perdidos` — Préstamos perdidos
- `configuracion_sistema` — Parámetros globales
- `auditoria` — Registro de cambios

---

## Seguridad

- ✅ JWT encriptado (JWE)
- ✅ Contraseñas con bcrypt
- ✅ CORS configurado
- ✅ Validación con Pydantic
- ✅ Auditoria de cambios
- ✅ Soft deletes
- ✅ Roles y permisos (admin/usuario)

---

## Datos de Prueba

**Usuario admin:**
- Email: `admin@test.com`
- Contraseña: `123456`

**BD de prueba:**
- 3 tipos de préstamo
- 1 cliente: Carlos Rodríguez
- Capital inicial: $10,000,000

Ejecutar: `python -m app.db.seed`

---

## Documentación Interactiva

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

---

## Dependencias Principales

```
fastapi==0.135.1
uvicorn==0.42.0
sqlalchemy==2.0.48
pymysql==1.1.2
python-jose[cryptography]
jwcrypto
bcrypt
python-dotenv
openpyxl
reportlab
pydantic==2.12.5
```

Ver `requirements.txt` para versiones exactas.

---

## Deployment

### Desarrollo
```bash
uvicorn app.main:app --reload
```

### Producción
```bash
pip install gunicorn
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## Estado del Proyecto

| Componente | Estado |
|-----------|--------|
| Autenticación | ✅ Completado |
| CRUD Préstamos | ✅ Completado |
| Pagos | ✅ Completado |
| Moras | ✅ Completado |
| Reportes | ✅ Completado |
| Auditoria | ✅ Completado |
| Documentación | ✅ Completado |

