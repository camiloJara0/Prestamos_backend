# Prestamos Backend

Backend para sistema de gestión de préstamos personales desarrollado con **FastAPI** y **SQLite**.

---

## Tecnologías

- Python 3.14
- FastAPI
- SQLAlchemy
- SQLite (desarrollo) / MySQL (producción)
- JWT con encriptación JWE (python-jose + jwcrypto)
- bcrypt para hash de contraseñas
- Pydantic para validación de datos

---

## Estructura del proyecto

```
app/
├── main.py
├── core/          # Configuración de seguridad y JWT
├── db/            # Conexión y sesión de base de datos
├── models/        # Modelos SQLAlchemy
├── schemas/       # Schemas Pydantic
├── services/      # Lógica de negocio
├── routes/        # Endpoints
├── utils/         # Helpers
├── dependencies/  # Autenticación y dependencias
```

---

## Instalación

1. Clona el repositorio:
```bash
git clone <url-del-repositorio>
cd Prestamos_backend
```

2. Instala las dependencias:
```bash
pip install -r requirements.txt
```

3. Inicia el servidor:
```bash
uvicorn app.main:app --reload
```

4. Poblar la base de datos con datos de prueba:
```bash
python -m app.db.seed
```

5. Abre la documentación interactiva:
```
http://127.0.0.1:8000/docs
```

---

## Datos de prueba (seed)

El seed crea automáticamente:
- **Usuario admin** — email: `admin@test.com` / password: `123456`
- **3 tipos de préstamo** — Personal, Empresarial y Emergencia
- **1 cliente de prueba** — Carlos Rodríguez
- **Capital inicial** — 10,000,000

El seed es seguro de ejecutar varias veces — no duplica datos existentes.

---

## Endpoints disponibles

### Autenticación
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/auth/login` | Iniciar sesión, devuelve access y refresh token |
| POST | `/auth/logout` | Cerrar sesión, invalida el token |
| POST | `/auth/refresh` | Renovar access token con refresh token |
| GET | `/auth/me` | Obtener información del usuario autenticado |

### Clientes
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/clientes` | Crear cliente |
| GET | `/clientes` | Listar clientes activos |
| GET | `/clientes/{id}` | Obtener cliente por ID |
| PUT | `/clientes/{id}` | Actualizar cliente |
| DELETE | `/clientes/{id}` | Eliminar cliente |

### Tipo de Préstamos
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/tipo_prestamo` | Crear tipo de préstamo |
| GET | `/tipo_prestamo` | Listar tipos activos |
| GET | `/tipo_prestamo/{id}` | Obtener tipo por ID |
| PUT | `/tipo_prestamo/{id}` | Actualizar tipo |
| DELETE | `/tipo_prestamo/{id}` | Eliminar tipo |

### Capital
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/capital` | Registrar inversión o retiro |
| GET | `/capital` | Consultar capital disponible |

### Préstamos
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/prestamos` | Crear préstamo con cuotas automáticas |
| GET | `/prestamos` | Listar préstamos activos |
| POST | `/prestamos/{id}/renovar` | Renovar préstamo existente |

---

## Seguridad

- Contraseñas hasheadas con **bcrypt** — nunca se almacena la contraseña en texto plano
- Tokens **JWT firmados y encriptados** con JWE (AES-256)
- **Access token** con expiración de 60 minutos
- **Refresh token** con expiración de 7 días
- Tokens almacenados en base de datos para poder invalidarlos en logout
- Todos los endpoints protegidos requieren token válido en el header
- Control de roles (admin/usuario) con respuesta 403 para accesos no autorizados

---

## Lógica financiera

Al crear un préstamo el sistema automáticamente:
1. Verifica que haya capital disponible
2. Calcula el interés total: `capital × (porcentaje / 100) × número de cuotas`
3. Calcula el monto total: `capital + interés`
4. Calcula el valor de cada cuota: `monto total / número de cuotas`
5. Genera las cuotas con fechas de vencimiento mensuales
6. Descuenta el capital otorgado
7. Registra el movimiento en el historial de capital

---

Al renovar un préstamo el sistema:
1. Verifica que el préstamo esté activo
2. Calcula el saldo pendiente
3. Descuenta el abono si hay uno
4. Crea un nuevo préstamo con el saldo restante
5. Marca el préstamo original como renovado
6. Registra la relación en la tabla de renovaciones
7. Genera nuevas cuotas

---

## Estado del proyecto

### Semana 1 y 2 — Backend
| Tarea | Estado |
|-------|--------|
| Arquitectura base del proyecto FastAPI | ✅ Completado |
| Sistema de autenticación JWT | ✅ Completado |
| CRUD de clientes | ✅ Completado |
| CRUD de tipo de préstamos | ✅ Completado |
| CRUD tipos de pago | 🔄 En progreso |
| Registro de movimientos de capital | ✅ Completado |
| Creación de préstamo con lógica financiera | ✅ Completado |
| Generación de cuotas | ✅ Completado |
| Renovación de préstamo | ✅ Completado |
| Préstamo Perdido | ⏳ Pendiente |
| Registro de pagos | ⏳ Pendiente |
| Cálculo automático de mora | ⏳ Pendiente |
| Reportes financieros + exportaciones | ⏳ Pendiente |

### Semana 3 — Frontend
| Tarea | Estado |
|-------|--------|
| Arquitectura base frontend | ⏳ Pendiente |
| Dashboard financiero | ⏳ Pendiente |

---

## Variables de entorno recomendadas para producción

```env
SECRET_KEY=tu_clave_secreta_larga
DATABASE_URL=mysql+pymysql://usuario:password@host/db
```

---

## Notas de desarrollo

- La base de datos SQLite se genera automáticamente al iniciar el servidor
- El archivo `test.db` está excluido del repositorio vía `.gitignore`
- Para producción se recomienda migrar a MySQL o PostgreSQL