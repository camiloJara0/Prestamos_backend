# Sistema de Gestión de Préstamos Personales 

**Backend profesional en FastAPI para gestionar préstamos, pagos, moras y reportes financieros.**

Universidad del Valle - Proyecto Académico

---

## 📋 Tabla de Contenidos

- [Características](#características)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejecutar](#ejecutar)
- [API Endpoints](#api-endpoints)
- [Autenticación](#autenticación)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Ejemplos de Uso](#ejemplos-de-uso)
- [Troubleshooting](#troubleshooting)

---

## ✨ Características

### Core
- ✅ **Gestión completa de préstamos** con cuotas automáticas
- ✅ **Registro de pagos** con validaciones detalladas
- ✅ **Cálculo automático de moras** con parámetros configurables
- ✅ **Renovación de préstamos** con abono opcional
- ✅ **Marcado de préstamos perdidos** con auditoría

### Seguridad
- ✅ **Autenticación JWT** con encriptación JWE (A256KW/A256CBC-HS512)
- ✅ **Roles y permisos** (admin/usuario)
- ✅ **Auditoria completa** de cambios críticos
- ✅ **Tokens invalidables** (almacenados en BD)
- ✅ **Validaciones robustas** en todos los endpoints

### Reportes
- ✅ **Reportes financieros** (ganancias, pérdidas, cobranza, cartera)
- ✅ **Exportación a Excel** con diseño profesional (paleta morado)
- ✅ **Exportación a PDF** con tablas formateadas
- ✅ **Filtros por rango de fechas** flexibles
- ✅ **Distribución por tipo de préstamo**

### Sistema
- ✅ **Configuración dinámica** sin reiniciar servidor
- ✅ **Migraciones automáticas** de BD
- ✅ **CORS mejorado** para frontend
- ✅ **Documentación interactiva** (Swagger/OpenAPI)
- ✅ **Seed idempotente** para datos de prueba

---

## 🔧 Requisitos

- Python 3.10+
- MySQL 5.7+ (o SQLite para desarrollo local)
- pip
- Git

---

## 📥 Instalación

### 1. Clonar repositorio
```bash
git clone https://github.com/tu-usuario/Prestamos_backend.git
cd Prestamos_backend
```

### 2. Crear y activar entorno virtual
```bash
# Crear
python -m venv venv

# Activar (Windows)
venv\Scripts\activate

# Activar (Linux/Mac)
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuración

### Crear archivo `.env`

En la raíz del proyecto, crea un archivo `.env` con las siguientes variables:

```env
# ===== SEGURIDAD =====
SECRET_KEY=tu-clave-secreta-muy-larga-y-segura-cambiar-en-produccion
ENCRYPTION_KEY=clave-encriptacion-32-caracteres-cambiar-produccion

# ===== BASE DE DATOS =====
# Opción 1: MySQL (producción)
DATABASE_URL=mysql+pymysql://usuario:password@localhost:3306/prestamos_db

# Opción 2: SQLite (desarrollo local)
# DATABASE_URL=sqlite:///./prestamos.db

# ===== FRONTEND =====
FRONTEND_URL=http://localhost:3000
```

**⚠️ IMPORTANTE:** 
- `SECRET_KEY` debe ser muy largo y aleatorio (generar con `openssl rand -hex 32`)
- `ENCRYPTION_KEY` debe tener exactamente 32 caracteres
- En producción, usar valores diferentes y seguros

### Base de Datos MySQL (Opcional)

Si usas MySQL, crea la BD primero:

```sql
CREATE DATABASE prestamos_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

## ▶️ Ejecutar Servidor

### 1. Inicializar base de datos (primera vez)
```bash
python -m app.db.seed
```

Esto crea automáticamente:
- ✅ Usuario admin: `admin@admin.com` / `admin123`
- ✅ 3 tipos de préstamo (Personal, Empresarial, Emergencia)
- ✅ 1 cliente de prueba: Carlos Rodríguez
- ✅ Capital inicial: $10,000,000
- ✅ Configuraciones del sistema (mora, interés, gracia)

### 2. Iniciar servidor
```bash
uvicorn app.main:app --reload
```

**Servidor disponible en:** `http://127.0.0.1:8000`

### 3. Acceder a documentación interactiva

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

Credenciales de prueba:
- **Email:** admin@test.com
- **Contraseña:** 123456

---

## 🔐 Autenticación

### Flujo JWT

Todos los endpoints (excepto `/auth/login`) requieren token JWT:

```
1. POST /auth/login
   ↓
2. Recibe: access_token (60 min) + refresh_token (7 días)
   ↓
3. Guardar token en localStorage/sessionStorage
   ↓
4. Incluir en header: Authorization: Bearer <access_token>
   ↓
5. Token expira → POST /auth/refresh → Nuevo token
   ↓
6. POST /auth/logout → Invalida token
```

### Headers requeridos
```bash
Authorization: Bearer eyJhbGciOiJFQ0RILUVTK0E1MTIiLCJlbmMiOiJBMjU2Q0JDLUhTNTEyIn0...
Content-Type: application/json
```

---

## 📚 API Endpoints

### Autenticación (Públicos)
```
POST   /auth/login              Iniciar sesión → devuelve tokens
POST   /auth/logout             Cerrar sesión → invalida token
POST   /auth/refresh            Renovar token → nuevo access_token
GET    /auth/me                 Datos del usuario autenticado
```

### Gestión de Préstamos
```
POST   /prestamos               Crear préstamo (valida cuotas vencidas)
GET    /prestamos               Listar (filtros: estado, cliente_id, fecha)
GET    /prestamos/{id}          Detalle completo con cuotas y pagos
POST   /prestamos/{id}/renovar  Renovar préstamo con abono
POST   /prestamos/{id}/marcar_perdido  Marcar como perdido
PUT    /prestamos/{id}/ajustar-capital Ajustar capital (admin)
```

### Pagos
```
POST   /pagos                   Registrar pago (valida desglose)
GET    /pagos                   Listar pagos registrados
```

### Moras
```
GET    /moras                   Listar todas las moras
GET    /moras/prestamo/{id}     Moras de un préstamo
GET    /moras/{id}              Detalle de una mora
POST   /moras/procesar-moras    Calcular moras automáticas (admin)
```

### Configuración (Admin)
```
GET    /moras/config/todas      Ver todas las configuraciones
GET    /moras/config/{clave}    Ver configuración específica
PUT    /moras/config/{clave}    Actualizar configuración
```

Parámetros configurables:
- `tasa_mora_diaria` — % diario de mora (default: 0.5)
- `interes_minimo` — tasa mínima (default: 2.5)
- `dias_gracia_mora` — días antes de aplicar mora (default: 3)

### Reportes
```
GET    /reportes/ganancias      Reporte de ganancias
GET    /reportes/ganancias/excel Exportar Excel
GET    /reportes/ganancias/pdf   Exportar PDF

GET    /reportes/perdidas       Reporte de pérdidas
GET    /reportes/perdidas/excel Exportar Excel
GET    /reportes/perdidas/pdf   Exportar PDF

GET    /reportes/cobranza       Cuotas por vencer/vencidas/pagadas
GET    /reportes/cartera        Préstamos activos/renovados/perdidos
```

Filtros disponibles: `desde=2026-08-01&hasta=2026-08-31`

### Auditoria (Admin)
```
GET    /auditoria/              Todas las auditorias
GET    /auditoria/usuario/{id}  Por usuario específico
GET    /auditoria/tabla/{nombre} Por tabla (prestamos, pagos, etc)
GET    /auditoria/operacion/{tipo} Por tipo (CREATE, UPDATE, DELETE)
```

---

## 📊 Estructura del Proyecto

```
app/
├── main.py                        # Configuración principal de FastAPI
│
├── core/
│   └── security.py               # JWT, encriptación, hash de passwords
│
├── db/
│   ├── database.py               # Conexión y migraciones
│   └── seed.py                   # Datos iniciales
│
├── models/
│   ├── base.py                   # Base declarativa
│   └── models.py                 # 13 tablas SQLAlchemy
│
├── schemas/                       # Validación Pydantic
│   ├── auth.py
│   ├── prestamo.py
│   ├── pago.py
│   ├── mora.py
│   ├── reporte.py
│   ├── auditoria.py
│   ├── configuracion.py
│   └── ...
│
├── routes/                        # Endpoints FastAPI
│   ├── auth.py
│   ├── prestamo.py
│   ├── pago.py
│   ├── mora.py
│   ├── reporte.py
│   ├── auditoria.py
│   └── ...
│
├── services/                      # Lógica de negocio
│   ├── prestamo.py
│   ├── pago.py
│   ├── mora.py
│   ├── reporte.py
│   ├── auditoria.py
│   └── ...
│
└── dependencies/
    └── auth.py                   # Dependencias (autenticación)
```

### Base de Datos (13 tablas)
- `usuarios` — Usuarios del sistema
- `tokens` — Tokens invalidados
- `capital` — Capital disponible
- `clientes` — Clientes (soft-delete)
- `tipos_prestamo` — Tipos disponibles
- `tipos_pago` — Métodos de pago
- `prestamos` — Préstamos otorgados
- `prestamo_cuotas` — Cuotas de cada préstamo
- `pagos` — Pagos registrados
- `movimientos_capital` — Historial financiero
- `moras` — Moras calculadas
- `prestamos_renovaciones` — Renovaciones
- `prestamos_perdidos` — Préstamos perdidos
- `configuracion_sistema` — Parámetros globales
- `auditoria` — Registro de cambios

---

## 📝 Ejemplos de Uso

### 1. Login y obtener token
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "123456"
  }'

# Response:
{
  "access_token": "eyJhbGciOiJFQ0RILUVTK0E1MTIi...",
  "refresh_token": "eyJhbGciOiJFQ0RILUVTK0E1MTIi...",
  "token_type": "bearer"
}
```

### 2. Crear préstamo
```bash
curl -X POST "http://localhost:8000/prestamos" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_id": 1,
    "tipo_prestamo_id": 1,
    "capital_prestado": 500000,
    "porcentaje_interes": 2.5,
    "numero_cuotas": 6
  }'

# Response: Préstamo creado con 6 cuotas automáticas
```

### 3. Registrar pago
```bash
curl -X POST "http://localhost:8000/pagos" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "prestamo_id": 1,
    "cliente_id": 1,
    "cuota_id": 1,
    "tipo_pago_id": 1,
    "fecha_pago": "2026-08-28",
    "valor_pagado": 82500,
    "capital_pagado": 75000,
    "interes_pagado": 5000,
    "mora_pagada": 0
  }'
```

### 4. Ver reporte de cartera
```bash
curl -X GET "http://localhost:8000/reportes/cartera?desde=2026-08-01&hasta=2026-08-31" \
  -H "Authorization: Bearer <access_token>"

# Response: Distribución de préstamos por estado
```

### 5. Exportar a Excel
```bash
curl -X GET "http://localhost:8000/reportes/ganancias/excel?desde=2026-08-01&hasta=2026-08-31" \
  -H "Authorization: Bearer <access_token>" \
  -o reporte_agosto.xlsx
```

### 6. Cambiar parámetro de mora (Admin)
```bash
curl -X PUT "http://localhost:8000/moras/config/tasa_mora_diaria" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "valor": "1.5",
    "descripcion": "Tasa aumentada a 1.5% diario"
  }'
```

---

## 🧪 Testing/Pruebas

### Filtrar préstamos
```bash
# Todos activos
GET /prestamos?estado=activo

# De un cliente específico
GET /prestamos?cliente_id=1

# Rango de fechas
GET /prestamos?fecha_desde=2026-08-01&fecha_hasta=2026-08-31

# Con búsqueda
GET /prestamos?busqueda=Carlos

# Con paginación
GET /prestamos?skip=0&limit=10
```

---

## 🔒 Seguridad

### Implementado
- ✅ JWT encriptado (JWE no es solo firmado)
- ✅ Contraseñas con bcrypt (rounds=12)
- ✅ CORS configurado para frontend
- ✅ Validación con Pydantic en todos los inputs
- ✅ Auditoria de operaciones críticas
- ✅ Soft deletes (no borrar datos)
- ✅ Roles y permisos (admin/usuario)

---

## 🚀 Deployment

### En desarrollo
```bash
uvicorn app.main:app --reload
```

### En producción
```bash
# Instalar gunicorn
pip install gunicorn

# Ejecutar
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Variables de entorno producción
```env
SECRET_KEY=<generar-aleatorio-seguro>
ENCRYPTION_KEY=<32-caracteres-aleatorios>
DATABASE_URL=mysql+pymysql://prod_user:strong_pass@prod_host:3306/prestamos_prod
FRONTEND_URL=https://tupagina.com
```

---

## ❓ Troubleshooting

### Error: "ModuleNotFoundError: No module named 'app'"
```bash
# Solución: Instalar dependencias
pip install -r requirements.txt
```

### Error: "Can't connect to MySQL server"
```bash
# Verificar:
# 1. MySQL está corriendo
# 2. Credenciales en .env son correctas
# 3. BD existe: CREATE DATABASE prestamos_db;
```

### Error: "401 Unauthorized"
```bash
# Solución: Token expirado o falta header
# Incluir en todos los requests:
Authorization: Bearer <access_token>
```

### Error en seed: "Duplicate entry for email"
```bash
# Solución: BD ya tiene datos
# Limpiar y reintentar (desarrollo solo):
# DELETE FROM usuarios;
# python -m app.db.seed
```

---

## 📦 Dependencias Principales

```
fastapi==0.135.1          # Framework web
uvicorn==0.42.0           # ASGI server
sqlalchemy==2.0.48        # ORM
pymysql==1.1.2            # Driver MySQL
python-jose[cryptography] # JWT
jwcrypto                  # Encriptación JWE
bcrypt                    # Hash passwords
python-dotenv             # Variables de entorno
openpyxl                  # Exportar Excel
reportlab                 # Exportar PDF
pydantic==2.12.5          # Validación
```

Ver `requirements.txt` para versiones exactas.

---
## ✅ Estado Actual

| Componente | Estado | Notas |
|-----------|--------|-------|
| Autenticación JWT | ✅ Listo | JWE encriptado |
| CRUD Préstamos | ✅ Listo | Con validaciones |
| Pagos | ✅ Listo | Desglose validado |
| Moras | ✅ Listo | Parámetros dinámicos |
| Reportes | ✅ Listo | JSON/Excel/PDF |
| Auditoria | ✅ Listo | Operaciones críticas |
| Configuración | ✅ Listo | Sin reiniciar |
| Frontend | 🔄 En desarrollo | Nuxt/Vue |
| Documentación | ✅ Completa | OpenAPI + README |

---

## 🔗 Enlaces Útiles

- **API Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **GitHub:** https://github.com/tu-usuario/Prestamos_backend
- **Documento Análisis:** Ver `ANALISIS_FRONTEND_BACKEND.md`
- **Resumen Backend:** Ver `RESUMEN_BACKEND_COMPLETADO.md`

---
