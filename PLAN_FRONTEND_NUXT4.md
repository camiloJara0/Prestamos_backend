# Plan de Creación de Frontend en Nuxt 4 — Sistema de Gestión de Préstamos

> Documento generado a partir del análisis del backend (`FastAPI + SQLAlchemy + SQLite/MySQL`).
> Fecha: agosto 2026 · Nuxt 4 estable (v4.4.x).
> Nota: las correcciones del backend (sección 1.3) ya fueron aplicadas y verificadas con pruebas funcionales.

---

## 1. Análisis del backend actual

### 1.1 Stack del backend

| Capa | Tecnología |
|------|------------|
| API | FastAPI (Python 3.13/3.14) |
| ORM | SQLAlchemy 2.0 |
| DB | SQLite (dev) / MySQL (prod) |
| Auth | JWT firmado (HS256) + encriptado (JWE AES-256) |
| Hash | bcrypt |
| Exportación | openpyxl (Excel), reportlab (PDF) |
| Validación | Pydantic v2 |

### 1.2 Estructura de la base de datos (13 tablas)

```
usuarios ──< tokens
capital (fila única, monto_total)

clientes ──< prestamos ──< prestamo_cuotas ──< pagos >── tipos_pago
            │      │            └────< moras
            │      └────< prestamos_renovaciones (prestamo_anterior/nuevo)
            │      └────< prestamos_perdidos
            └────< pagos

movimientos_capital (historial: inversion, retiro, prestamo_otorgado, pago_recibido, perdida)
```

| Tabla | Campos principales | Observaciones |
|-------|-------------------|---------------|
| `usuarios` | id, nombre(100), email(100, unique), hashed_password(255), rol(`admin`/`usuario`), estado(`activo`/`inactivo`) | Sin `updated_at` |
| `tokens` | id, usuario_id, access_token(500), refresh_token(500), activo(0/1), expires_at | Guarda ambos tokens para invalidación |
| `capital` | id, monto_total, updated_at | Fila única |
| `clientes` | id, nombre(100, req), cedula(20, unique, req), telefono(20), direccion(200), persona_referencia(100), telefono_referencia(20), observaciones, estado(`activo`/`inactivo`) | Listado y soft-delete por `estado` |
| `tipos_prestamo` | id, nombre(100, req), descripcion, interes_mensual(Float), max_cuotas(Int), estado | Listado y soft-delete por `estado` |
| `tipos_pago` | id, nombre(50, req), descripcion, estado, created_at, updated_at | Estado añadido para soft-delete |
| `prestamos` | id, cliente_id, tipo_prestamo_id, fecha_prestamo, capital_prestado, porcentaje_interes, interes_total, monto_total, numero_cuotas, valor_cuota, saldo_pendiente, estado(`activo`/`pagado`/`perdido`/`renovado`), observaciones | |
| `prestamo_cuotas` | id, prestamo_id, numero_cuota, fecha_vencimiento, valor_cuota, capital, interes, mora, estado(`pendiente`/`pagado`/`vencido`/`parcial`) | Generadas automáticamente al crear/renovar |
| `pagos` | id, prestamo_id, cliente_id, cuota_id, tipo_pago_id, fecha_pago, valor_pagado, capital_pagado, interes_pagado, mora_pagada, observaciones | |
| `movimientos_capital` | id, tipo_movimiento(`inversion`/`retiro`/`prestamo_otorgado`/`pago_recibido`/`perdida`), descripcion, valor, fecha, prestamo_id(nullable) | Historial del negocio |
| `prestamos_renovaciones` | id, prestamo_anterior_id, prestamo_nuevo_id, fecha, observaciones | |
| `prestamos_perdidos` | id, prestamo_id, fecha, valor_perdido, motivo | |
| `moras` | id, prestamo_id, cuota_id, fecha, valor, estado(`generada`), created_at | Listado por estado `generada` |

---

## 2. Documentación de la API (base para el frontend)

Formato genérico:
- **Auth**: `Authorization: Bearer <access_token>` (excepto donde se indique `PÚBLICO`).
- **Roles**: `ADMIN` = solo rol `admin`. Sin marca = cualquier usuario autenticado.
- **Errores**: `{"detail": "mensaje"}`. Códigos: `400` validación/negocio, `401` token inválido, `403` sin permisos, `404` no encontrado, `500` error interno.
- **Paginación**: `?skip=0&limit=10` (defaults).

### 2.1 Autenticación — `/auth`

#### POST `/auth/login` · PÚBLICO
Inicia sesión y devuelve tokens.
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `email` | string | ✅ | Email registrado |
| `password` | string | ✅ | Se compara contra el hash bcrypt |

**200** → `{ "access_token": str, "refresh_token": str, "token_type": "bearer" }`
**401** → "Email o contraseña incorrectos".

#### POST `/auth/logout`
Invalida el access token en BD.
**Header**: Bearer token. **200** → `{ "mensaje": "Sesión cerrada correctamente" }` · **401** → token no encontrado/invalidado.

#### POST `/auth/refresh`
Renueva el access token.
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `refresh_token` | string | ✅ | Debe estar activo en BD y tener `type: "refresh"` |

**200** → `{ "access_token": str, "token_type": "bearer" }` · **401** → token inválido/expirado/invalidado.

#### GET `/auth/me`
Información del usuario autenticado.
**200** → `{ "id": int, "nombre": str, "email": str, "rol": "admin"|"usuario", "estado": "activo"|"inactivo" }` · **401** · **404**.

### 2.2 Clientes — `/clientes`

#### POST `/clientes/`
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `nombre` | string | ✅ | Max 100 |
| `cedula` | string | ✅ | Max 20, **única** |
| `telefono` | string | ❌ | Max 20 |
| `direccion` | string | ❌ | Max 200 |
| `persona_referencia` | string | ❌ | Max 100 |
| `telefono_referencia` | string | ❌ | Max 20 |
| `observaciones` | text | ❌ | — |
| `estado` | string | ❌ | `activo`/`inactivo` (default `activo`) |

**201** → `ClienteOut` (lo anterior + `id`). **400** → "Ya existe un cliente con esa cedula".

#### GET `/clientes/?skip=&limit=`
Solo clientes **activos**. **200** → `[ClienteOut]`.

#### GET `/clientes/{id}`
**200** → `ClienteOut` · **404** → "Cliente no encontrado".

#### PUT `/clientes/{id}`
Mismos campos que POST (todos opcionales en la práctica; el schema los exige todos). **400** si cedula duplicada · **404**.

#### DELETE `/clientes/{id}`
Soft-delete: cambia `estado` a `inactivo`. **200** → `{ "mensaje": "Cliente eliminado" }` · **404**.

### 2.3 Tipos de préstamo — `/tipo_prestamo`

#### POST `/tipo_prestamo/` · ADMIN
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `nombre` | string | ✅ | Max 100 |
| `descripcion` | string | ✅ | — |
| `interes_mensual` | float | ✅ | Porcentaje (ej. 2.5 = 2.5%) |
| `max_cuotas` | int | ✅ | Máximo de cuotas permitido |
| `estado` | string | ❌ | `activo`/`inactivo` (default `activo`) |

**201** → `TipoPrestamoOut` (+`id`). **403** si no eres admin.

#### GET `/tipo_prestamo/?skip=&limit=`
Solo activos, requiere autenticación. **200** → `[TipoPrestamoOut]`.

#### GET `/tipo_prestamo/{id}`
**200** → `TipoPrestamoOut` · **404** "Tipo de prestamo no encontrado".

#### PUT `/tipo_prestamo/{id}` · ADMIN · DELETE `/tipo_prestamo/{id}` · ADMIN
PUT → `TipoPrestamoOut` · **404**. DELETE (soft) → `{ "mensaje": "Tipo de prestamo eliminado" }`.

### 2.4 Tipos de pago — `/tipo_pago`

#### POST `/tipo_pago/` · ADMIN
| Campo | Tipo | Requerido |
|-------|------|-----------|
| `nombre` | string | ✅ (max 50) |
| `descripcion` | string | ✅ |

**201** → `TipoPagoOut` (+`id`). **403** si no eres admin.

#### GET `/tipo_pago/?skip=&limit=`
Solo activos. **200** → `[TipoPagoOut]`.

#### GET `/tipo_pago/{id}`
**200** → `TipoPagoOut` · **404** "Tipo de pago no encontrado".

#### PUT `/tipo_pago/{id}` · ADMIN · DELETE `/tipo_pago/{id}` · ADMIN
PUT → `TipoPagoOut` · **404**. DELETE (soft) → `{ "mensaje": "Tipo de pago eliminado" }`.

### 2.5 Capital — `/capital`

#### POST `/capital/` · ADMIN
Registra inversión o retiro y actualiza `monto_total`.
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `tipo_movimiento` | string | ✅ | Solo `"inversion"` o `"retiro"` |
| `descripcion` | string | ❌ | — |
| `valor` | float | ✅ | > 0; en retiro ≤ capital actual |
| `fecha` | date | ✅ | `YYYY-MM-DD` |

**200** → `{ "movimiento": MovimientoCapitalOut, "capital_actual": float }`.
**400** → "Tipo de movimiento debe ser inversion o retiro" / "Capital insuficiente para realizar el retiro". **403** si no eres admin.

#### GET `/capital/`
**200** → `{ "id": int, "monto_total": float }` (crea el registro con 0.0 si no existe).

### 2.6 Préstamos — `/prestamos`

#### POST `/prestamos/`
Crea préstamo + cuotas automáticas mensuales y descuenta capital.
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `cliente_id` | int | ✅ | Debe existir |
| `tipo_prestamo_id` | int | ✅ | Debe existir |
| `fecha_prestamo` | date | ✅ | `YYYY-MM-DD` |
| `capital_prestado` | float | ✅ | > 0 y ≤ capital disponible |
| `porcentaje_interes` | float | ✅ | Porcentaje mensual |
| `numero_cuotas` | int | ✅ | ≥ 1 |
| `observaciones` | string | ❌ | — |

**Fórmulas**: `interes_total = capital × (porcentaje/100) × numero_cuotas` · `monto_total = capital + interes_total` · `valor_cuota = round(monto_total / numero_cuotas, 2)` · `saldo_pendiente = monto_total`. Vencimientos = `fecha_prestamo + 1..n meses`.
**201** → `PrestamoOut` (`id, cliente_id, tipo_prestamo_id, fecha_prestamo, capital_prestado, porcentaje_interes, interes_total, monto_total, numero_cuotas, valor_cuota, saldo_pendiente, estado, observaciones`).
**400** → "Capital insuficiente para otorgar el prestamo". **500** → error genérico.

#### GET `/prestamos/?skip=&limit=`
Filtros (todos opcionales):
| Query | Tipo | Default | Uso |
|-------|------|---------|-----|
| `estado` | string | `activo` | `activo`/`pagado`/`perdido`/`renovado` o `todos` |
| `cliente_id` | int | — | Filtra por cliente |
| `fecha_desde` / `fecha_hasta` | date | — | Rango de fechas de otorgamiento |
| `busqueda` | string | — | Nombre o cédula del cliente (ilike) |

Ordenado por `id` descendente. **200** → `[PrestamoOut]`.

#### GET `/prestamos/{id}`
Detalle completo.
**200** → `PrestamoDetalleOut`:
```
PrestamoOut (id, cliente_id, tipo_prestamo_id, fecha_prestamo, capital_prestado,
             porcentaje_interes, interes_total, monto_total, numero_cuotas,
             valor_cuota, saldo_pendiente, estado, observaciones)
+ cliente: ClienteOut|null
+ tipo_prestamo: TipoPrestamoOut|null
+ cuotas: [ { id, prestamo_id, numero_cuota, fecha_vencimiento, valor_cuota,
              capital, interes, mora, estado } ]
+ pagos: [ PagoOut ]
```
**404** → "Prestamo no encontrado".

#### POST `/prestamos/{id}/renovar`
Renueva un préstamo activo con saldo pendiente.
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `porcentaje_interes` | float | ✅ | — |
| `numero_cuotas` | int | ✅ | ≥ 1 |
| `abono` | float | ❌ | Default 0.0; ≤ saldo pendiente |
| `fecha_renovacion` | date | ✅ | — |
| `observaciones` | string | ❌ | — |

**201** → nuevo `PrestamoOut` (el original pasa a estado `renovado`). **404** → "Prestamo no encontrado". **400** → "No se puede renovar un prestamo en estado X" / "El abono no puede ser mayor al saldo pendiente".

#### POST `/prestamos/{id}/marcar_perdido`
| Campo | Tipo | Requerido |
|-------|------|-----------|
| `motivo` | string | ❌ |
| `fecha` | date | ✅ |

**200** → `{ "prestamo": PrestamoOut, "valor_perdido": float, "motivo": str|null, "fecha": date }`.
**404** · **400** → "No se puede marcar como perdido un prestamo en estado X".

### 2.7 Pagos — `/pagos`

#### POST `/pagos/`
| Campo | Tipo | Requerido | Restricciones |
|-------|------|-----------|---------------|
| `prestamo_id` | int | ✅ | Debe existir |
| `cliente_id` | int | ✅ | Debe coincidir con el del préstamo |
| `cuota_id` | int | ✅ | Debe pertenecer al préstamo y estar `pendiente` |
| `tipo_pago_id` | int | ✅ | Debe existir |
| `fecha_pago` | date | ✅ | — |
| `valor_pagado` | float | ✅ | ≥ 0; ≤ valor_cuota + mora |
| `capital_pagado` | float | ✅ | ≥ 0 |
| `interes_pagado` | float | ✅ | ≥ 0 |
| `mora_pagada` | float | ✅ | ≥ 0 |
| `observaciones` | string | ❌ | — |

**Validaciones**: `capital + interes + mora ≈ valor_pagado` (tolerancia 0.01); cuota pertenece al préstamo; cliente coincide; no se excede el valor de la cuota.
**Lógica**: cuota → `pagado` si `valor_pagado ≥ valor_cuota`, `parcial` si `0 < valor < valor_cuota`; `saldo_pendiente -= capital_pagado`; registra movimiento `pago_recibido`.
**201** → `PagoOut`. **404** → "Cuota no encontrada" / "Prestamo no encontrado" / "Tipo de pago no encontrado". **400** → validaciones.

#### GET `/pagos/?skip=&limit=`
**200** → `[PagoOut]`.

### 2.8 Moras — `/moras`

#### GET `/moras/?skip=&limit=`
Solo moras con `estado == "generada"`, ordenadas por fecha descendente. **200** → `[MoraOut]`.

#### GET `/moras/prestamo/{prestamo_id}`
Moras de un préstamo. **200** → `[MoraOut]`.

#### GET/PUT/DELETE `/moras/{id}`
**200** · **404** "Mora no encontrada".

#### POST `/moras/procesar-moras`
Ejecuta cálculo de mora manual (tasa diaria 1% sobre `valor_cuota × días de atraso`). **200** → `{ "moras_actualizadas": [id, ...] }`.

### 2.9 Reportes — `/reportes`

Filtros opcionales en **todos**: `?mes=1-12&anio=2026`. Sin filtros → todos los periodos.

#### GET `/reportes/ganancias`
**200** → `{ "periodo": str, "total_invertido": float, "total_prestado": float, "total_pagos_recibidos": float, "total_intereses": float, "ganancia_neta": float }`.
`ganancia_neta = pagos_recibidos − prestado + invertido` (fórmula actual, revisar en mejora).

#### GET `/reportes/perdidas`
**200** → `{ "periodo": str, "total_perdidas": float, "cantidad_prestamos_perdidos": int, "detalle": [{ "prestamo_id": int, "fecha": date, "valor_perdido": float, "motivo": str|null }] }`.

#### GET `/reportes/ganancias/excel`, `/ganancias/pdf`, `/perdidas/excel`, `/perdidas/pdf`
Descarga binaria (`StreamingResponse`). `Content-Disposition: attachment; filename=...`. En el frontend deben consumirse como blob (ver sección 3.6).

---

## 3. Plan de construcción del frontend en Nuxt 4

### 3.1 Stack recomendado

| Capa | Elección | Por qué |
|------|----------|---------|
| Framework | **Nuxt 4** (4.4.x, `compatibilityVersion: 4`) | SSR + estructura `app/`, fetch singleton, TS nativo |
| Lenguaje | **TypeScript** | Tipado de la API, seguridad |
| UI | **Tailwind CSS v4** + componentes propios (o **Nuxt UI v4**) | Rápido y consistente |
| Estado | **Pinia** (solo auth + sesión) | El resto con `useFetch`/`useAsyncData` |
| Validación | **Zod** (o valibot) en formularios | Reglas reflejo de los esquemas Pydantic |
| Charts | **ApexCharts** (`vue3-apexcharts`) o **ECharts** | Dashboard |
| HTTP | `$fetch`/`ofetch` con interceptor propio | Refresh automático + manejo 401 |

### 3.2 Estructura de directorios (Nuxt 4)

```
prestamos_frontend/
├── nuxt.config.ts
├── package.json
├── tsconfig.json
├── .env                     # NUXT_PUBLIC_API_BASE
├── shared/                  # Tipos compartidos (espejo de schemas)
│   └── types/api.ts
├── app/
│   ├── app.vue
│   ├── error.vue
│   ├── assets/css/main.css
│   ├── components/
│   │   ├── AppSidebar.vue
│   │   ├── AppHeader.vue
│   │   ├── DataTable.vue
│   │   ├── Pagination.vue
│   │   ├── ModalDialog.vue
│   │   ├── MoneyInput.vue
│   │   ├── ConfirmDialog.vue
│   │   ├── EstadoBadge.vue
│   │   ├── clientes/ClienteForm.vue
│   │   ├── prestamos/PrestamoForm.vue
│   │   ├── prestamos/PrestamoCuotas.vue
│   │   ├── prestamos/RenovarModal.vue
│   │   ├── prestamos/MarcarPerdidoModal.vue
│   │   └── pagos/PagoForm.vue
│   ├── composables/
│   │   ├── useApi.ts        # fetch con token + refresh
│   │   ├── useAuth.ts       # sesión, login, logout
│   │   ├── useClientes.ts
│   │   ├── usePrestamos.ts
│   │   ├── usePagos.ts
│   │   ├── useCapital.ts
│   │   ├── useTipos.ts
│   │   ├── useReportes.ts
│   │   └── useFormatters.ts # COP (Intl) + fechas
│   ├── layouts/
│   │   ├── default.vue      # sidebar + header + <NuxtPage/>
│   │   └── auth.vue         # pantalla de login
│   ├── middleware/
│   │   ├── auth.ts          # redirige a /login si no hay sesión
│   │   └── guest.ts         # redirige a / si ya hay sesión
│   ├── pages/
│   │   ├── login.vue
│   │   ├── index.vue                        # Dashboard
│   │   ├── clientes/index.vue               # listado + CRUD
│   │   ├── tipos-prestamo/index.vue
│   │   ├── tipos-pago/index.vue
│   │   ├── capital/index.vue
│   │   ├── prestamos/index.vue              # listado con filtros
│   │   ├── prestamos/nuevo.vue              # crear préstamo
│   │   ├── prestamos/[id].vue               # detalle + cuotas + renovar/perdido
│   │   ├── pagos/index.vue                  # registrar + historial
│   │   ├── moras/index.vue
│   │   └── reportes/index.vue               # ganancias/pérdidas + export
│   ├── plugins/
│   │   └── pinia.ts
│   └── stores/
│       └── auth.ts          # token, user, rol, estado
```

### 3.3 Configuración clave

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  compatibilityVersion: 4,
  modules: ['@pinia/nuxt', '@nuxt/ui'],
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000',
    },
  },
  css: ['~/app/assets/css/main.css'],
  app: {
    head: {
      title: 'Gestión de Préstamos',
      htmlAttrs: { lang: 'es' },
    },
  },
})
```

### 3.4 Sesión y manejo de tokens

- Guardar `access_token` y `refresh_token` en `localStorage` (persistencia) y en el store Pinia junto con el perfil (`GET /auth/me`) y el `rol`.
- **Interceptor** en `useApi`: añade `Authorization: Bearer` a cada request. Ante `401`, intenta `POST /auth/refresh` una vez; si falla, cierra sesión y redirige a `/login`.
- **Rol**: ocultar/bloquear acciones de administración (tipos, capital) en la UI cuando `rol !== 'admin'`, ya que el backend responde `403`.
- Las sesiones sobreviven reinicios del backend (la clave de encriptación es determinística).
- Usar middleware `auth` global (definePageMeta) en todas las páginas salvo `login`.

### 3.5 Mapeo páginas → endpoints

| Página | Endpoints usados |
|--------|------------------|
| `login.vue` | `POST /auth/login`, luego `GET /auth/me` |
| `index.vue` (Dashboard) | `GET /capital`, `GET /prestamos?estado=activo`, `GET /reportes/ganancias`, `GET /reportes/perdidas` (combinados) |
| `clientes/index.vue` | `GET /clientes`, `POST`, `PUT`, `DELETE /clientes/{id}` |
| `tipos-prestamo/index.vue` | `GET /tipo_prestamo`, CRUD (admin) |
| `tipos-pago/index.vue` | `GET /tipo_pago`, CRUD (admin) |
| `capital/index.vue` | `GET /capital`, `POST /capital` (admin) |
| `prestamos/index.vue` | `GET /prestamos` con filtros |
| `prestamos/nuevo.vue` | `GET /clientes`, `GET /tipo_prestamo`, `POST /prestamos` |
| `prestamos/[id].vue` | `GET /prestamos/{id}` (detalle con cuotas y pagos), `POST .../renovar`, `POST .../marcar_perdido` |
| `pagos/index.vue` | `GET /pagos`, `GET /prestamos`, `GET /prestamos/{id}` (cuotas), `POST /pagos`, `GET /tipo_pago` |
| `moras/index.vue` | `GET /moras`, `GET /moras/prestamo/{id}`, `POST /moras/procesar-moras` |
| `reportes/index.vue` | `GET /reportes/ganancias`, `/perdidas` + descargas Excel/PDF |

### 3.6 Descarga de archivos (Excel/PDF)

Los endpoints de exportación devuelven binario. Consumir como blob:

```ts
const { apiBase } = useRuntimeConfig().public
const { accessToken } = useAuth()

export async function descargarReporte(tipo: 'ganancias'|'perdidas', formato: 'excel'|'pdf', mes?: number, anio?: number) {
  const res = await $fetch(`${apiBase}/reportes/${tipo}/${formato}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${accessToken.value}` },
    query: { mes, anio },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(res)
  const a = document.createElement('a')
  a.href = url
  a.download = `${tipo}.${formato === 'excel' ? 'xlsx' : 'pdf'}`
  a.click()
  URL.revokeObjectURL(url)
}
```

### 3.7 Formularios: validación espejo de la API

- **Cliente**: nombre y cedula obligatorios (cedula única → capturar 400 y mostrar en el campo), teléfono máx 20, etc.
- **Préstamo**: `capital_prestado` no puede exceder capital disponible (consultar `GET /capital` y validar en vivo); `numero_cuotas` ≥ 1; `porcentaje_interes` numérico.
- **Pago**: validar que la cuota esté `pendiente`, que `capital + interes + mora` cuadre con `valor_pagado`, y que `valor_pagado` no exceda `valor_cuota + mora`. Mostrar los desgloses calculados por el frontend (el backend los valida).
- **Renovar**: `abono ≤ saldo_pendiente`.
- **Retiro de capital**: `valor ≤ monto_total` (traer `GET /capital` y comparar antes de enviar).

### 3.8 Estados del sistema a representar en UI

| Entidad | Estados | Color sugerido |
|---------|---------|----------------|
| Préstamo | `activo` · `pagado` · `perdido` · `renovado` | azul · verde · rojo · gris |
| Cuota | `pendiente` · `pagado` · `vencido` · `parcial` | gris · verde · rojo · ámbar |
| Cliente / Tipo | `activo` · `inactivo` | verde · gris |

### 3.9 Fases de desarrollo del frontend

**Fase 1 — Base (3–4 días)**
1. Scaffold Nuxt 4 + Tailwind + Pinia + estructura de carpetas.
2. `useApi`, `useAuth`, store de auth, middleware `auth`/`guest`, página login.
3. Layout `default` con sidebar y navegación (acciones admin según rol).

**Fase 2 — CRUD administrativo (4–5 días)**
4. Clientes (listado, paginación, formulario modal, editar, eliminar soft).
5. Tipos de préstamo y tipos de pago (CRUD, restringido a admin).
6. Capital (ver monto, registrar inversión/retiro, historial).

**Fase 3 — Núcleo financiero (5–6 días)**
7. Creación de préstamo (selector de cliente + tipo, capital disponible, calculadora de cuotas en vivo).
8. Listado de préstamos con filtros + detalle con cuotas (`GET /prestamos/{id}`).
9. Registro de pagos sobre cuota (con desglose validado) + historial.

**Fase 4 — Reportes y Dashboard (3–4 días)**
10. Dashboard con tarjetas (capital, préstamos activos, ganancia neta, mora) y gráficas.
11. Reportes ganancias/pérdidas con filtros mes/año y descargas Excel/PDF.
12. Módulo de moras (listado por préstamo + botón procesar).

**Total estimado**: 3–4 semanas (1 persona).

---

## 4. Análisis del alcance del proyecto

### 4.1 Qué cubre hoy (funcional)

- ✅ Autenticación completa (login, logout, refresh, perfil).
- ✅ CRUD clientes, tipos de préstamo, tipos de pago (con soft-delete y roles).
- ✅ Capital (inversiones, retiros, historial; movimientos admin).
- ✅ Creación de préstamos con cuotas automáticas y lógica de interés.
- ✅ Detalle de préstamo con cuotas, pagos y cliente (`GET /prestamos/{id}`).
- ✅ Filtros y búsqueda en el listado de préstamos.
- ✅ Renovación de préstamos (relación anterior→nuevo).
- ✅ Préstamos perdidos con impacto en capital.
- ✅ Registro de pagos con desglose validado y actualización de saldo.
- ✅ Reportes de ganancias/pérdidas JSON + exportación Excel/PDF con filtros.
- ✅ Cálculo de mora manual y listado por estado `generada` / por préstamo.

### 4.2 Qué NO cubre (brechas funcionales)

- ❌ Dashboard/estadísticas agregadas en el backend (el frontend las arma combinando llamados).
- ❌ Búsqueda/filtros en listados de clientes y pagos (solo `skip`/`limit`).
- ❌ Calculadora de mora automática programada (solo manual).
- ❌ Gestión de usuarios (crear/editar usuarios y roles) — solo el seed crea el admin.
- ❌ Recuperación de contraseña / cambio de contraseña.
- ❌ Reportes de cobranza (clientes morosos, cuotas por vencer).
- ❌ Notificaciones/recordatorios.
- ❌ Auditoría/historial de acciones (solo existe historial de capital).

---

## 5. Plan de mejora y expansión

### 5.1 Correcciones aplicadas

Ver sección 1.3. Todas las correcciones críticas y de prioridad media fueron implementadas y verificadas (25/25 pruebas funcionales OK).

### 5.2 Endpoints nuevos recomendados (siguientes pasos)

```
GET  /clientes/buscar?q=          → búsqueda por nombre/cedula
GET  /prestamos/{id}/cuotas       → cuotas del préstamo (opcional, ya viaja en detalle)
GET  /prestamos/{id}/pagos        → pagos del préstamo (opcional, ya viaja en detalle)
GET  /dashboard/resumen           → KPIs (capital, préstamos activos, cuotas por vencer, mora acumulada, ganancia periodo)
GET  /moras/pendientes            → moras activas no pagadas
POST /usuarios                    → gestión de usuarios (solo admin)
PUT  /auth/password               → cambio de contraseña
POST /auth/refresh               → (mejora) rotar refresh token e invalidar access viejo
GET  /reportes/vencidas          → reporte de cuotas vencidas / cobranza
```

### 5.3 Expansiones a medio plazo

1. **Automatizar mora**: tarea programada (celery/apscheduler o cron en Nitro del frontend) que ejecute el cálculo de mora diario.
2. **Módulo de cobranza**: agenda de cuotas por vencer, clientes morosos, historial de gestión/llamadas.
3. **Módulo de usuarios y roles**: alta/baja de usuarios, permisos por rol (`admin`/`cobrador`/`consulta`).
4. **Auditoría**: tabla `auditoria` registrando quién y cuándo creó/editó préstamos, pagos, capital.
5. **Notificaciones**: recordatorios de vencimiento (email/WhatsApp) vía proveedor.
6. **Pagos parciales inteligentes**: el backend calcula desglose capital/interés/mora automáticamente (pago a pago o por paquete de cuotas).
7. **Reportes avanzados**: flujo de caja, cartera por antigüedad, proyección de intereses, comparativo mensual.
8. **Redondeo de cuotas**: ajustar la última cuota para que la suma cuadre con `monto_total`.

### 5.4 Expansiones a largo plazo

- Migración a **PostgreSQL** + migraciones **Alembic** (hoy `create_all` con mini-migración de columnas).
- **Multi-empresa / multi-sucursal** (tenant en `usuarios`, `capital`, `prestamos`).
- **App móvil o PWA** reutilizando los tipos de `shared/` y la API.
- **Cobros con pasarela** (PSE, tarjeta) integrados al módulo de pagos.
- **Reportes en la nube / programados** (enviar Excel/PDF por email cada mes).

---

## 6. Checklist de verificación antes de empezar el frontend

- [ ] Backend arranca con `DATABASE_URL` correcta (SQLite por defecto; MySQL en producción).
- [ ] Las sesiones sobreviven reinicios (clave de encriptación determinística).
- [ ] `POST /auth/login` + `GET /auth/me` responden correctamente.
- [ ] `GET /prestamos/{id}` devuelve detalle con cuotas, pagos y cliente.
- [ ] CORS incluye `http://localhost:3000` (ya está en `main.py`).
- [ ] Definir los tipos TypeScript en `shared/types/api.ts` espejo de los schemas Pydantic.
- [ ] Ocultar acciones de administración (tipos, capital) cuando `rol !== 'admin'`.
