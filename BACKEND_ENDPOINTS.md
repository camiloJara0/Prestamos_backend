
## Avance

### FASE 1 ✅ COMPLETADA
#### 1. Agregar `saldo_pendiente` a tabla `prestamos` ✅ REALIZADA
- Campo agregado exitosamente a la tabla `prestamos`
- Se utiliza para rastrear el monto que falta por pagar en cada préstamo
- Se actualiza automáticamente cuando se registran pagos

#### 2. Agregar `monto_interes` y `estado` a tabla `prestamos_cuota` ✅ REALIZADA
- Campo `monto_interes`: registra el interés correspondiente a cada cuota individual
- Campo `estado`: ahora usa Enum con valores: "pendiente", "pagado", "vencido", "parcial"
- Permite un mejor control del estado de cada cuota

#### 3. Crear tabla `configuracion_sistema` ✅ REALIZADA
- Nueva tabla para almacenar parámetros globales del sistema
- Estructura:
  - `clave`: identificador único (ej: "tasa_mora_diaria")
  - `valor`: valor de la configuración
  - `descripcion`: descripción del parámetro
  - `tipo_valor`: tipo de dato (float, int, string, boolean)
  - `activo`: booleano para habilitar/deshabilitar
- Seed inicial con 3 configuraciones:
  - `tasa_mora_diaria`: 0.5 (porcentaje diario de mora)
  - `interes_minimo`: 2.5 (tasa mínima de interés)
  - `dias_gracia_mora`: 3 (días antes de aplicar mora)

---

### FASE 2 ✅ COMPLETADA
#### 4. Endpoints GET/PUT `/mora/config` ✅ REALIZADA

**Cómo usar los endpoints de configuración:**

**GET `/moras/config/todas`**
- Obtiene todas las configuraciones activas del sistema
- No requiere parámetros
- Respuesta: lista de todas las configuraciones con sus valores actuales
- Útil para ver el estado completo de todos los parámetros

**GET `/moras/config/{clave}`**
- Obtiene una configuración específica por su clave
- Parámetro: `clave` (string) — ejemplo: "tasa_mora_diaria"
- Respuesta: la configuración solicitada con su valor actual
- Ejemplo de uso: si necesitas obtener solo la tasa de mora diaria, usas `GET /moras/config/tasa_mora_diaria`

**PUT `/moras/config/{clave}`**
- Actualiza una configuración existente
- Parámetro: `clave` (string) — ejemplo: "tasa_mora_diaria"
- Body JSON:
  ```json
  {
    "valor": "1.5",
    "descripcion": "Nueva descripción (opcional)"
  }
  ```
- Respuesta: la configuración actualizada con el nuevo valor
- Nota: Solo administradores pueden actualizar configuraciones
- Ejemplo: cambiar la tasa de mora de 0.5 a 1.5 diario

---

### FASE 3 ⏳ PENDIENTE
#### 5. Mejorar lógica de mora en `app/services/mora.py`

**Descripción:**
Actualizar la función `procesar_moras()` para:
- Leer automáticamente los parámetros de `configuracion_sistema` en lugar de valores hardcodeados
- Usar `tasa_mora_diaria` para calcular mora
- Respetar `dias_gracia_mora` antes de aplicar mora
- Aplicar mora solo a cuotas en estado "vencido" o "parcial"

**Pasos:**
1. Modificar `app/services/mora.py` para que lea de `ConfiguracionSistema`
2. Actualizar el cálculo de mora dinámicamente
3. Registrar las moras calculadas en la tabla `mora`

---

### FASE 4 ⏳ PENDIENTE
#### 6. Validar cuotas vencidas antes de crear préstamos

**Descripción:**
Antes de crear un nuevo préstamo, validar que el cliente no tenga cuotas vencidas sin pagar.
- Prevenir sobreendeudamiento
- Garantizar que haya capacidad de pago

#### 7. Endpoint PUT `/prestamos/{id}/ajustar-capital`

**Descripción:**
Endpoint para correcciones si hay errores en el cálculo del capital.
- Requiere rol de admin
- Permite ajustar el capital de un préstamo
- Recalcula todas las cuotas automáticamente

---

### FASE 5 ⏳ PENDIENTE
#### 8. Reporte de cobranza

**Descripción:**
Reporte que muestre:
- Cuotas por vencer (próximos 7 días)
- Cuotas vencidas (sin pagar)
- Cuotas pagadas (este período)
- Monto total a cobrar
- Monto cobrado vs. pendiente

#### 9. Reporte de cartera

**Descripción:**
Reporte que muestre:
- Préstamos activos (cantidad y monto total)
- Préstamos renovados (cantidad y monto)
- Préstamos perdidos (cantidad y pérdida total)
- Gráficos de distribución

---

### FASE 6 ⏳ PENDIENTE (Baja prioridad)
#### 10. Crear tabla `auditoria` y registrar cambios
#### 11. Endpoint GET `/auditoria`
#### 12. Reportes por rango de fechas
#### 13. API Pública (sin autenticación)

---

## Notas Importantes

- Todos los endpoints requieren autenticación JWT excepto los de FASE 6
- Las configuraciones solo pueden ser modificadas por administradores
- Los cambios en `configuracion_sistema` se aplican inmediatamente a nuevos cálculos de mora
- Mantener commits limpios y descriptivos
- Usar convenciones: `feat:`, `fix:`, `refactor:` en los mensajes









# Backend — Endpoints y funcionalidades faltantes

Documento de requerimientos para el backend de LoanSoft (`prestamos_backend`).
Cada item corresponde a un `REQUIERE_BACKEND` marcado en el frontend.

---

## B1 — Idempotencia en `POST /pagos`

**Prioridad:** Importante
**Motivo:** La cola offline (outbox) puede reenviar el mismo pago múltiples veces al reconectar.

### Endpoints a modificar

```
POST /pagos
```

### Cambio

- Aceptar header opcional `X-Idempotency-Key: <uuid>` **o** campo `idempotency_key` en el body.
- Si se recibe una key ya procesada, retornar la respuesta original (200 con el pago existente) en lugar de crear un duplicado.
- Almacenar la key en la tabla `pagos` o en una tabla auxiliar `idempotency_keys(key, response, created_at)`.

### Tabla sugerida

```sql
CREATE TABLE idempotency_keys (
    key UUID PRIMARY KEY,
    response JSONB NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Limpiar claves mayores a 24h
DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours';
```

### Front actual

```typescript
// services/api/pago.ts — cuando B1 exista, enviar key
await apiPost('/pagos', { ...data, idempotency_key: crypto.randomUUID() })
```

---

## B2 — Historial de movimientos de capital

**Prioridad:** Importante
**Motivo:** La página `/capital` necesita mostrar el historial de movimientos.

### Endpoint nuevo

```
GET /capital/movimientos?skip=0&limit=50
```

### Response

```json
[
  {
    "id": 1,
    "tipo_movimiento": "inversion",
    "descripcion": "Inversión inicial",
    "valor": 5000000,
    "fecha": "2025-01-15",
    "prestamo_id": null
  }
]
```

### Notas

- Los datos ya existen en la tabla `movimientos_capital`.
- Solo falta el endpoint GET con paginación.

---

## B3 — Dashboard con KPIs agregados

**Prioridad:** Mejora
**Motivo:** Reduce de 4 llamadas paralelas a 1 sola; el backend puede calcular aggregates más eficientemente.

### Endpoint nuevo

```
GET /dashboard/resumen
```

### Response

```json
{
  "capital_actual": 5000000,
  "prestamos_activos": 12,
  "saldo_pendiente_total": 3200000,
  "ganancia_neta": 1500000,
  "total_prestado_periodo": 8000000,
  "mora_acumulada": 45000,
  "prestamos_por_estado": {
    "activo": 12,
    "pagado": 8,
    "perdido": 2,
    "renovado": 3
  }
}
```

### Notas

- Reemplaza las 4 llamadas actuales: GET /capital, GET /prestamos?estado=activo, GET /reportes/ganancias, GET /reportes/perdidas.
- `saldo_pendiente_total` se calcula como `SUM(saldo_pendiente)` de préstamos activos.
- `prestamos_por_estado` evita traer todos los préstamos solo para contar.

---

## B4 — Búsqueda server-side de clientes

**Prioridad:** Mejora
**Motivo:** Cuando la data crezca, la búsqueda client-side ya no es viable.

### Endpoint a modificar

```
GET /clientes?busqueda=nombre
```

### Cambio

- Aceptar parámetro `busqueda` (o `q`) que filtre por `nombre ILIKE %q%` o `cedula LIKE %q%`.
- Ya existe en prestamos (`busqueda`), replicar en clientes.

---

## B5 — Cambio de contraseña

**Prioridad:** Mejora
**Motivo:** Los usuarios necesitan cambiar su contraseña desde el perfil.

### Endpoints nuevos

```
POST /auth/password
Body: { "password_actual": "...", "password_nuevo": "..." }
Response: 200 { "mensaje": "Contraseña actualizada" }
```

```
POST /auth/password/reset
Body: { "email": "..." }
Response: 200 { "mensaje": "Si el email existe, se envió un enlace de recuperación" }
```

```
POST /auth/password/confirm
Body: { "token": "...", "password_nuevo": "..." }
Response: 200 { "mensaje": "Contraseña restablecida" }
```

### Notas

- El reset envía un email con un token de un solo uso (expira en 1h).
- La tabla `usuarios` debe tener campos `reset_token` y `reset_token_expires`.

---

## B6 — Gestión de usuarios (admin)

**Prioridad:** Mejora
**Motivo:** El admin necesita gestionar usuarios del sistema.

### Endpoints nuevos

```
GET    /usuarios              → lista de usuarios (admin)
POST   /usuarios              → crear usuario (admin)
PUT    /usuarios/{id}         → actualizar usuario (admin)
DELETE /usuarios/{id}         → eliminar/desactivar usuario (admin)
POST   /usuarios/{id}/reset-password  → resetear contraseña (admin)
```

### Tabla `usuarios`

```sql
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(20) DEFAULT 'usuario',
    estado VARCHAR(20) DEFAULT 'activo',
    reset_token VARCHAR(255),
    reset_token_expires TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Notas

- Rotación de refresh tokens: guardar `refresh_token` en tabla `refresh_tokens` para poder revocar.
- Refresh en cookie httpOnly: cuando B6 exista, mover refresh_token de localStorage a cookie httpOnly + CSRF token.

---

## B7 — Scheduler de moras automático

**Prioridad:** Mejora
**Motivo:** Actualmente las moras se procesan manualmente. Un cron automático sería más confiable.

### Opción A: Cron en el backend

```python
# En main.py o como background task
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=0, minute=0)  # Todos los días a medianoche
async def procesar_moras_diario():
    # Lógica de procesar_moras
    pass

scheduler.start()
```

### Opción B: Endpoint que el frontend puede llamar

```
POST /moras/procesar-moras
```

Este endpoint ya existe. La mejora sería ejecutarlo automáticamente con un cron interno del backend.

### Notas

- Revisar cuotas con `estado = 'pendiente'` y `fecha_vencimiento < hoy`.
- Calcular mora al 1% diario sobre `valor_cuota`.
- Crear registro en tabla `moras` si no existe uno ya para esa cuota/fecha.

---

## B8 — Ajuste automático de capital al renovar/perder

**Prioridad:** Decisión de negocio
**Motivo:** Renovar un préstamo o marcarlo como perdido debería ajustar `capital.monto_total`.

### Comportamiento esperado

1. **Al renovar:** se descuenta el abono del capital (si lo hay).
2. **Al marcar perdido:** el saldo pendiente se resta del capital.
3. **Al recibir pago:** la parte capital del pago se suma al capital.

### Endpoint a modificar

```
POST /prestamos/{id}/renovar
POST /prestamos/{id}/marcar_perdido
POST /pagos
```

### Cambios

- En `renovar_prestamo`: después de crear el nuevo préstamo, actualizar `capital.monto_total -= abono`.
- En `marcar_prestamo_perdido`: `capital.monto_total -= saldo_pendiente`.
- En `crear_pago`: `capital.monto_total += capital_pagado`.

---

## B9 — Consistencia: Σ cuotas = monto_total

**Prioridad:** Mejora
**Motivo:** Actualmente la última cuota puede tener un valor redondeado diferente.

### Endpoint a modificar

```
POST /prestamos
```

### Cambio

- Al crear un préstamo, calcular la última cuota como: `valor_ultima_cuota = monto_total - (valor_cuota * (numero_cuotas - 1))`.
- Esto garantiza que la suma de todas las cuotas sea exactamente `monto_total`.

---

## B10 — Web Push + Tabla de auditoría

**Prioridad:** Mejora
**Motivo:** Notificaciones push para recordatorios de vencimiento y trazabilidad de acciones.

### 1. Servicio de Web Push

#### Dependencia

```bash
pip install pywebpush
```

#### Variable de entorno

```bash
VAPID_PUBLIC_KEY=<generada con py_vapid>
VAPID_PRIVATE_KEY=<generada con py_vapid>
VAPID_CLAIM_EMAIL=mailto:admin@loansoft.com
```

#### Tabla `push_subscriptions`

```sql
CREATE TABLE push_subscriptions (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id),
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Endpoints

```
POST /push/subscribe
Body: { "endpoint": "...", "p256dh": "...", "auth": "..." }
Response: 200 { "mensaje": "Suscripción registrada" }
Auth: requiere token válido

DELETE /push/subscribe
Body: { "endpoint": "..." }
Response: 200 { "mensaje": "Suscripción eliminada" }

POST /push/test
Body: { "usuario_id": 1 }
Response: 200 { "mensaje": "Notificación de prueba enviada" }
Auth: solo admin
```

#### Servicio de envío

```python
from pywebpush import webpush, WebPushException

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {"sub": "mailto:admin@loansoft.com"}

def enviar_notificacion(subscription_info: dict, titulo: str, cuerpo: str, data: dict = None):
    payload = {
        "title": titulo,
        "body": cuerpo,
        "data": data or {},
        "icon": "/icons/icon-192.png",
        "badge": "/icons/badge-72.png"
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        return True
    except WebPushException as e:
        print(f"Error push: {e}")
        return False
```

#### Recordatorios de vencimiento

```python
# Cron job o endpoint programado
def enviar_recordatorios_vencimiento():
    """Envía notificaciones 3 y 1 días antes del vencimiento."""
    from datetime import date, timedelta
    hoy = date.today()
    
    cuotas_3_dias = db.query(PrestamoCuota).filter(
        PrestamoCuota.estado == "pendiente",
        PrestamoCuota.fecha_vencimiento == hoy + timedelta(days=3)
    ).all()
    
    cuotas_1_dia = db.query(PrestamoCuota).filter(
        PrestamoCuota.estado == "pendiente",
        PrestamoCuota.fecha_vencimiento == hoy + timedelta(days=1)
    ).all()
    
    for cuota in cuotas_3_dias + cuotas_1_dias:
        # Buscar suscripciones del usuario dueño del préstamo
        # Enviar notificación push
        pass
```

### 2. Tabla de auditoría

#### Tabla `auditoria`

```sql
CREATE TABLE auditoria (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id),
    accion VARCHAR(50) NOT NULL,     -- 'crear', 'editar', 'eliminar', 'pago', 'renovacion', 'perdida'
    entidad VARCHAR(50) NOT NULL,    -- 'prestamo', 'pago', 'cliente', 'capital', etc.
    entidad_id INTEGER,
    detalles JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_auditoria_usuario ON auditoria(usuario_id);
CREATE INDEX idx_auditoria_entidad ON auditoria(entidad, entidad_id);
CREATE INDEX idx_auditoria_fecha ON auditoria(created_at);
```

#### Endpoint de consulta

```
GET /auditoria?usuario_id=1&entidad=prestamo&desde=2025-01-01&hasta=2025-12-31&skip=0&limit=50
Auth: solo admin
```

#### Middleware de auditoría (sugerencia)

```python
from fastapi import Request
from datetime import datetime

async def middleware_auditoria(request: Request, call_next):
    response = await call_next(request)
    
    # Registrar solo mutaciones
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Extraer usuario del token
        # Guardar en tabla auditoria
        pass
    
    return response
```

---

## B11 — Paginación con totales

**Prioridad:** Mejora
**Motivo:** Los listados necesitan saber el total de registros para la paginación del lado del cliente.

### Endpoints a modificar

```
GET /pagos?skip=0&limit=20
GET /clientes?skip=0&limit=20
GET /prestamos?skip=0&limit=20
GET /moras?skip=0&limit=20
```

### Response actual

```json
[{ ... }, { ... }]
```

### Response mejorado

```json
{
  "items": [{ ... }, { ... }],
  "total": 150,
  "page": 1,
  "pages": 8
}
```

### Front actual

```typescript
// El frontend actualmente asume respuesta como array
const pagos = await apiGet<Pago[]>('/pagos', { query })
```

### Front cuando B11 exista

```typescript
const response = await apiGet<{ items: Pago[], total: number, page: number, pages: number }>('/pagos', { query })
pagos.value = response.items
totalRegistros.value = response.total
```

---

## Resumen de prioridad

| ID | Endpoint | Prioridad | Fase frontend |
|----|----------|-----------|---------------|
| B1 | `POST /pagos` idempotencia | Importante | Fase 7 (offline) |
| B2 | `GET /capital/movimientos` | Importante | Fase 3 (capital) |
| B3 | `GET /dashboard/resumen` | Mejora | Fase 6 (dashboard) |
| B4 | `GET /clientes?busqueda=` | Mejora | Fase 3 (clientes) |
| B5 | `POST /auth/password` | Mejora | Fase 7 (perfil) |
| B6 | CRUD `/usuarios` | Mejora | Fase 8 (usuarios) |
| B7 | Scheduler moras | Mejora | Fase 5 (moras) |
| B8 | Ajuste capital automático | Decisión | Fase 4 (préstamos) |
| B9 | Σ cuotas = monto_total | Mejora | Fase 4 (préstamos) |
| B10 | Web Push + auditoría | Mejora | Fase 7 (notificaciones) |
| B11 | Paginación con totales | Mejora | Todas las fases |
