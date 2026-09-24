# BLUEPRINT — LoanSoft · Sistema de Gestión de Préstamos (Nuxt 4)

> Blueprint completo y operativo del frontend. Validado contra el backend real (`C:\Proyectos\Prestamos\prestamos_backend`, FastAPI + SQLAlchemy) y contra el scaffold Nuxt existente en este repositorio.
>
> **Uso:** el proyecto se implementa **por módulos** (Fase 0 → Fase 9). Cada Fase contiene Tasks numeradas. Cada Task es un **prompt autocontenido** que puede entregarse a una IA de programación. Ejecutar en orden estricto: cada task depende de la anterior. Al terminar cada task, la IA debe verificar su **Definition of Done**.
>
> **Stack:** Nuxt 4 · Vue 3 · TypeScript estricto · Pinia · Tailwind CSS v4 · Nuxt UI v4 · Zod · Dexie/IndexedDB · `@vite-pwa/nuxt` · ApexCharts · $fetch/ofetch · Vitest + Playwright.

---

## Índice

1. [Análisis del sistema actual (hechos verificados)](#1-análisis-del-sistema-actual)
2. [Requerimientos de backend adicionales](#2-requerimientos-de-backend-adicionales)
3. [Arquitectura frontend](#3-arquitectura-frontend)
4. [Design System y UX](#4-design-system-y-ux)
5. [Estrategia Offline-First](#5-estrategia-offline-first)
6. [PWA y notificaciones](#6-pwa-y-notificaciones)
7. [Seguridad y confiabilidad](#7-seguridad-y-confiabilidad)
8. [Convenciones para IAs (leer siempre primero)](#8-convenciones-para-ias)
9. [Fases, Tasks, Prompts y DoD](#9-fases-tasks-prompts-y-dod)
10. [Roadmap y prioridades](#10-roadmap-y-prioridades)
11. [Checklist global de verificación](#11-checklist-global-de-verificación)

---

## 1. Análisis del sistema actual

### 1.1 Backend (validado contra código fuente)

| Hallazgo | Detalle | Impacto frontend |
|---|---|---|
| **Todos los POST/PUT/DELETE responden `200`** | No existe `status_code=201` en ninguna ruta | Tratar `200` como éxito; no asumir `201` |
| **Sin header `Authorization` → `403`** | HTTPBearer por defecto. `401` = expirado/invalidado. `500` = token corrupto | El interceptor debe normalizar `403/401/500` |
| **Refresh token NO se rota** | 7 días de vida; logout inactiva la fila `tokens` (mata ambos tokens) | Al hacer refresh el access viejo queda invalidado; guardar ambos tokens |
| **Pagos: la cuota debe estar `pendiente`** | Cuotas `vencido`/`parcial`/`pagado` NO pueden pagarse (400) | La UI no ofrece pagar cuotas vencidas con la API actual |
| **Backend NO auto-distribuye capital/interés/mora** | El cliente envía el desglose; solo valida cuadre (tol 0.01) y `valor ≤ cuota + mora` | Formulario de pago con desglose asistido |
| **`saldo_pendiente -= capital_pagado`** | Solo el capital reduce saldo; movimiento `pago_recibido` registra `valor = capital_pagado` | Impacto en reportes |
| **Renovación NO toca capital** | No descuenta `capital.monto_total` ni crea movimiento | Mostrar sin inventar; flag de mejora backend |
| **Marcar perdido NO reduce capital** | Solo registra movimiento `perdida` | Ídem |
| **No hay transición automática a `pagado`** | El préstamo nunca se cierra solo | No inventar estados |
| **Mora: 1%/día sobre `valor_cuota × días_atraso`** | Solo cálculo manual; filas `moras` quedan `generada` para siempre | Mostrar mora acumulada por cuota |
| **`GET /pagos` sin filtros/orden/metadatos** | `GET /clientes`, `/tipo_prestamo`, `/tipo_pago` filtran `estado=activo`, solo `skip/limit` | Paginación en frontend |
| **No existe historial de movimientos de capital** | `GET /capital/movimientos` no existe | No construir esa pantalla con datos inventados |
| **`/reportes/ganancias`:** `ganancia_neta = pagos_recibidos − prestado + invertido` | Respuesta real incluye campo `periodo` | Mostrar tal cual; flag de revisión |
| **`MoraOut.fecha` es `string`** (`"2026-08-11"`) | No es `date` | Tipo TS correcto |
| **`POST /capital` y `marcar_perdido` devuelven ORM crudo** | Campos extra: `prestamo_id`, `created_at`, `updated_at` | Tiparlos opcionales |
| **Redondeo Python banker's; última cuota no ajustada** | `Σ cuotas ≠ monto_total` puede diferir en centavos | Replicar fórmulas exactas |
| **Seed** | `admin@test.com` / `123456`; capital inicial `10.000.000` | Datos de QA |

**Flujo de negocio:** Inversión de capital → otorgamiento de préstamo (descuenta capital, genera cuotas mensuales) → cobro de cuotas (reduce saldo solo por parte capital) → mora sobre cuotas vencidas → renovación del saldo remanente o préstamo perdido → reportes de ganancia/pérdida.

### 1.2 Scaffold Nuxt existente (a evolucionar, NO reconstruir)

- ✅ Nuxt 4.4 + Nuxt UI v4.8 + Pinia + Tailwind v4 + eslint + TS strict.
- ✅ `components/Layout/Aside.vue` (sidebar colapsable con estética púrpura), `components/Layout/Table.vue` (tabla reutilizable con orden/filtros/paginación), `stores/varView.ts`, página `Clientes.vue` parcial, 12 archivos de tipos en `app/types`.
- ❌ Deuda técnica a corregir: `services/api.ts` con axios + URL hardcodeada; `services/api/login.ts` usa axios directo (sin interceptor); `composables/table/*.js` en JavaScript; `pages/index.vue` es el login en `/`; `pages/Home.vue` placeholder; componentes de starter (`TemplateMenu`, `Layout/Navbar`, `AppLogo`); `app.vue` con metadata del starter en inglés; **`SECRET_KEY` expuesto en `runtimeConfig.public`**; rutas del sidebar apuntan a páginas inexistentes; `middleware/`, `plugins/`, `offline/` vacíos.

### 1.3 Brechas funcionales (no cubiertas por backend)

Dashboard agregado, búsqueda server-side, gestión de usuarios, recuperación/cambio de contraseña, auditoría, reportes de cobranza, notificaciones, mora automática.

---

## 2. Requerimientos de backend adicionales

> Flag explícito. Ninguno bloquea el MVP; cada uno está mapeado a la fase que lo necesita. **El frontend NO debe asumir que existen.**

| # | Requerimiento | Necesario para | Prioridad |
|---|---|---|---|
| B1 | **Idempotencia en `POST /pagos`** (header/body `idempotency_key`) | Fase 7 (cola offline sin duplicados) | Importante |
| B2 | `GET /capital/movimientos` (historial; los datos ya existen) | Módulo Capital | Importante |
| B3 | `GET /dashboard/resumen` (KPIs agregados) | Fase 6 (reduce N llamadas) | Mejora |
| B4 | `GET /clientes/buscar?q=` (búsqueda server-side) | Cuando la data crezca | Mejora |
| B5 | `POST /auth/password` + reset por email | Módulo Perfil | Mejora |
| B6 | CRUD `/usuarios` (admin) + rotación de refresh / refresh en cookie `httpOnly` | Módulo Usuarios + hardening | Mejora |
| B7 | Scheduler de moras (o cron de Nitro que llame `procesar-moras`) | Módulo Moras | Mejora |
| B8 | Renovación y préstamo perdido deben ajustar `capital.monto_total` | Integridad financiera | Decisión de negocio |
| B9 | Ajustar la última cuota (`Σ cuotas = monto_total`) | Consistencia | Mejora |
| B10 | Servicio de Web Push + tabla `auditoria` | Fase 7 notificaciones | Mejora |
| B11 | Paginación con totales (`total`, `page`) en `GET /pagos` y listados | Escalabilidad | Mejora |

---

## 3. Arquitectura frontend

### 3.1 Stack

Nuxt 4 (SSR) · Vue 3 `<script setup>` · TypeScript estricto · Pinia (auth, ui, sync, outbox) · Tailwind CSS v4 + Nuxt UI v4 · Zod (validación espejo de schemas Pydantic) · Dexie/IndexedDB · `@vite-pwa/nuxt` (Workbox) · ApexCharts (`vue3-apexcharts`) · `$fetch`/ofetch (reemplazar axios) · Vitest + Playwright.

### 3.2 Principios de arquitectura

1. **Capas:** `pages → composables/domain → services/api → backend`. Los componentes NUNCA llaman a la API directamente.
2. **Fuente de verdad:** tipos en `shared/types` (espejo de schemas), services tipados, stores solo para estado global.
3. **Bajo acoplamiento:** los composables de dominio envuelven los services y exponen refs reactivas; las vistas consumen composables.
4. **Regla de oro para IAs:** si algo no está en `shared/types` ni en `services/api`, **no existe**. No inventar endpoints, campos ni entidades.

### 3.3 Estructura de carpetas (evoluciona el scaffold actual)

```
loan-soft-frontend/
├── nuxt.config.ts
├── app.config.ts
├── .env.example
├── shared/
│   └── types/                 # TIPOS (mover desde app/types y completar)
├── app/
│   ├── app.vue                # metadata, SEO, htmlAttrs lang="es"
│   ├── error.vue              # página de error global
│   ├── assets/css/            # tokens de diseño, glass, fuentes
│   ├── components/
│   │   ├── app/               # AppShell, AppSidebar, AppHeader, ConnectionBanner, SyncIndicator
│   │   ├── ui/                # kit base: DataTable, ModalDialog, ConfirmDialog, MoneyInput,
│   │   │                      # EstadoBadge, StatCard, EmptyState, Skeleton, FormField,
│   │   │                      # CommandPalette, DateRangePicker
│   │   └── <domain>/          # clientes/ · prestamos/ · pagos/ · moras/ · capital/ · reportes/ · dashboard/
│   ├── composables/
│   │   ├── useApi.ts          # cliente HTTP (ofetch) con refresh y errores
│   │   ├── useAuth.ts         # sesión, login, logout, rol
│   │   ├── useSync.ts         # estado de sincronización
│   │   ├── useOffline.ts      # detección de conexión
│   │   ├── useShortcuts.ts    # atajos de teclado
│   │   ├── domain/            # useClientes · usePrestamos · usePagos · useCapital · useTipos · useReportes · useMoras
│   │   └── useFormatters.ts   # COP (Intl), fechas es-CO, porcentajes
│   ├── layouts/
│   │   ├── default.vue        # AppShell (sidebar + header + contenido)
│   │   └── auth.vue           # login
│   ├── middleware/
│   │   ├── auth.ts            # redirige a /login si no hay sesión
│   │   ├── guest.ts           # redirige a / si ya hay sesión
│   │   └── admin.ts           # bloquea si rol !== 'admin'
│   ├── pages/
│   │   ├── login.vue
│   │   ├── index.vue                       # Dashboard
│   │   ├── clientes/index.vue
│   │   ├── prestamos/index.vue
│   │   ├── prestamos/nuevo.vue
│   │   ├── prestamos/[id].vue
│   │   ├── pagos/index.vue
│   │   ├── moras/index.vue
│   │   ├── capital/index.vue
│   │   ├── tipos-prestamo/index.vue
│   │   ├── tipos-pago/index.vue
│   │   ├── reportes/index.vue
│   │   ├── cobranza/index.vue              # avanzado
│   │   └── usuarios/index.vue              # avanzado (requiere backend B6)
│   ├── plugins/
│   │   ├── api.ts              # registra useApi
│   │   ├── toast.ts            # notificaciones toast
│   │   └── offline.ts          # listeners online/offline
│   ├── services/
│   │   ├── api/                # auth · clientes · prestamo · pago · capital · tipo · reporte · mora
│   │   └── db/                 # Dexie: cache (lecturas) + outbox (cola de pagos)
│   ├── stores/
│   │   ├── auth.ts             # token, refresh, usuario, rol, estado
│   │   ├── ui.ts               # sidebar, tema, paleta de comandos
│   │   ├── sync.ts             # estado de conexión y sincronización
│   │   └── outbox.ts           # operaciones pendientes offline
│   ├── utils/
│   │   ├── format.ts
│   │   ├── money.ts
│   │   ├── fecha.ts
│   │   └── calculadoraPrestamo.ts   # réplica exacta de fórmulas del backend
│   └── public/                 # iconos, manifest, fuentes self-hosted
```

**Responsabilidades:** `shared/types` = contrato de la API · `services/api` = HTTP puro (auth, errores, blob) · `services/db` = persistencia offline · `composables/domain` = estado + cache + lógica de negocio de vista · `components/ui` = kit de diseño · `components/<domain>` = piezas de negocio · `stores` = sesión/UI/sync globales.

---

## 4. Design System y UX

### 4.1 Dirección visual

**Glassmorphism moderno + SaaS/Fintech premium**, sobrio y orientado a productividad. Transmite confianza, elegancia, control, claridad y seguridad.

### 4.2 Paleta

| Rol | Color | Uso |
|---|---|---|
| Primario (Morado) | `#7c3aed` → `#a78bfa` | Acciones, navegación activa, foco |
| Acento (Amarillo/Oro) | `#f59e0b` / `#d4af37` | Alertas, ganancia, destacados, "próximo a vencer" |
| Neutros (Gris) | escala cálida | Superficies, texto, bordes |
| Semánticos | Nuxt UI `success/warning/error/info` | Estados (activo/pagado/vencido/perdido) |

### 4.3 Reglas de estilo

- **Superficies glass:** `backdrop-blur`, bordes `rgba(124, 58, 237, 0.18)`, sombra suave. Blur solo en header/sidebar/banners; las tablas densas deben ser opacas (legibilidad).
- **Tipografía:** Poppins (marcas, números, KPIs) + Inter (cuerpo, densidad). **Self-hosted** (importante para PWA offline; no usar Google Fonts CDN).
- **Dark/Light** con `useColorMode`. Dark = experiencia fintech por defecto.
- **Densidad:** tablas `text-sm`, filas compactas, resumen de saldos en cabecera de sección. Optimizado para uso prolongado.
- **Componentes de datos:** `DataTable` con orden por columna, filtros (global + por columna + fechas), paginación, columnas configurables, exportación, estados (cargando/error/vacío).
- **Badges de estado:** préstamo `activo`(azul)/`pagado`(verde)/`perdido`(rojo)/`renovado`(gris); cuota `pendiente`(gris)/`pagado`(verde)/`vencido`(rojo)/`parcial`(ámbar); cliente/tipo `activo`(verde)/`inactivo`(gris).
- **Microinteracciones:** transiciones CSS (ya existe el fade del aside), feedback de guardado (toast), skeletons en carga, spinner de sincronización. `prefers-reduced-motion` respetado.
- **Productividad:** Command Palette (Ctrl+K), atajos, búsqueda por cédula/nombre en selectores, accesos rápidos en dashboard.
- **Accesibilidad (WCAG AA):** foco visible, `aria` en tablas/menús/modales, contraste de badges, navegación por teclado.
- **Responsive:** sidebar colapsable → drawer en móvil; tablas con scroll horizontal; formularios grid 1–2 columnas.

### 4.4 Mapa de rutas y permisos

| Ruta | Acceso | Módulo |
|---|---|---|
| `/login` | guest | Auth |
| `/` | auth | Dashboard |
| `/clientes` | auth | Clientes |
| `/prestamos`, `/prestamos/nuevo`, `/prestamos/[id]` | auth | Préstamos |
| `/pagos` | auth | Pagos |
| `/moras` | auth | Moras |
| `/capital` | **admin** | Capital |
| `/tipos-prestamo`, `/tipos-pago` | **admin** | Configuración |
| `/reportes` | auth | Reportes |
| `/cobranza` | auth | Cobranza (avanzado) |
| `/usuarios` | **admin** | Usuarios (avanzado, backend B6) |

---

## 5. Estrategia Offline-First

**Modelo elegido:** *Lecturas cacheadas + cola de pagos*. El backend es la fuente de verdad para las operaciones financieras críticas.

### 5.1 Escenarios

| Escenario | Comportamiento |
|---|---|
| **Con conexión** | Lecturas `network-first` con caché `stale-while-revalidate` en IndexedDB (TTL por entidad). Escrituras directas al API; al éxito se actualiza la cache. |
| **Sin conexión** | Lecturas desde cache con etiqueta "Última sincronización: hh:mm" y banner "Sin conexión". La app sigue funcionando. |
| **Operaciones offline** | Solo **pagos**. La cuota/prestamo afectado muestra badge "pendiente de sincronizar". Préstamos, capital, tipos y configuración requieren conexión (bloqueados con mensaje claro). |
| **Regresa la conexión** | Evento `online` + Background Sync → reprocesar la cola en orden. |
| **Sync exitosa** | Cada operación: mark-synced, refresh de cache local, toast, limpieza de badges. |
| **Sync falla** | Clasificar: `400/409` validación → `conflict` (requiere revisión del usuario con el detalle); `4xx` permanente → `failed`; `5xx/network` → reintento con backoff exponencial. El **backend gana** en el estado final. |
| **Operaciones pendientes** | Contador persistente en header + pantalla "Sincronización" con detalle por operación. |
| **Cerrar/reabrir** | La cola persiste en IndexedDB; al abrir se re-ejecuta; sesión y cache sobreviven. |

### 5.2 Anti-duplicados y consistencia financiera

- **Idempotency key** (UUID) por operación de pago. Mientras el backend no la soporte (B1), usar el **guard natural**: una cuota `pendiente→pagado` no se paga dos veces; si el servidor responde `400 "La cuota ya ha sido pagada"`, re-fetchear el detalle del préstamo y reconciliar el estado local con el real.
- **Read-modify-write** en el desglose de pagos; nunca optimismo ciego sobre saldos.
- Las operaciones financieras críticas **siempre** se validan en el servidor.

---

## 6. PWA y notificaciones

- **`@vite-pwa/nuxt` + Workbox:** precache del app shell; runtime cache: assets cache-first, GETs de API network-first con fallback stale. Manifest + iconos (morado/oro).
- **Instalación:** botón propio + `beforeinstallprompt`.
- **Actualizaciones:** SW con control de versión; al detectar SW nuevo → prompt "Actualización disponible / Recargar".
- **Background Sync:** para la cola de pagos.
- **Web Push:** flujo de permiso, suscripción, recordatorios de vencimiento (3 y 1 días antes). Sin backend de push (B10), usar **notificaciones locales** (`Notification API`).
- **Comunicación al usuario:** barra global de conexión (verde/ámbar/rojo) + indicador de sync en header con contador y spinner.

---

## 7. Seguridad y confiabilidad

- **Sesión:** tokens en store + persistencia. Interceptor: Bearer → `401` → refresh una vez → reintentar → logout. No guardar `SECRET_KEY` ni secretos en `runtimeConfig.public`.
- **Normalización de errores:** `ApiError { status, detail, field? }`. 400/403/404 mostrados por campo; nunca exponer stack traces.
- **Rutas:** middleware `auth` global (salvo login), `guest`, `admin`. Ocultar Y bloquear acciones admin cuando `rol !== 'admin'` (el backend ya devuelve 403).
- **Validación:** Zod espejo de schemas Pydantic en formularios; validación financiera (cuadre, topes) replicada en `utils/calculadoraPrestamo.ts`. La validación real la hace el backend.
- **Auditoría:** log local de acciones relevantes (exportable) mientras no exista la tabla `auditoria` backend (B10).
- **Trazabilidad:** cada operación de pago/renovación/perdida muestra quién (de `/auth/me`) y cuándo.
- **CSP + headers de seguridad** al build.

---

## 8. Convenciones para IAs

> **PROMPT BASE — anteponer a TODAS las tasks.** La IA receptora de una task debe recibir siempre este bloque más el bloque específico de la task.

```
CONTEXTO OBLIGATORIO PARA CUALQUIER TASK:
- Repositorio: loan-soft-frontend (Nuxt 4, Vue 3, TypeScript estricto, Pinia, Tailwind v4, Nuxt UI v4).
- ANTES de escribir código: analiza los archivos existentes relacionados (services/api/*, composables/domain/*, stores/*, shared/types/*, components/ui/*) y reutilízalos. NO dupliques funcionalidad.
- NO inventes endpoints, campos, entidades ni reglas de negocio. Solo usa lo que exista en shared/types y services/api. Si necesitas algo que no existe, marca REQUIERE_BACKEND: <descripción> en lugar de implementarlo con datos falsos.
- Respeta la arquitectura por capas: pages → composables/domain → services/api. Los componentes no llaman a la API directamente.
- TypeScript estricto: sin `any` ni `@ts-ignore`. Tipos definidos en shared/types.
- Todo formulario usa validación con Zod espejo de los schemas de la API.
- Considera SIEMPRE los estados: carga (skeleton), error (mensaje claro + acción) y vacío (empty state).
- Responsive y accesible (WCAG AA): foco visible, aria, teclado, prefers-reduced-motion.
- Mantén el design system: paleta morado #7c3aed / amarillo #f59e0b / grises; glass solo en superficies flotantes; Poppins (display) + Inter (cuerpo).
- Formatea dinero con useFormatters (COP, Intl 'es-CO') y fechas con fecha.ts.
- Al finalizar ejecuta y DEJA VERDE: pnpm typecheck && pnpm lint. Si existen tests del módulo, corre pnpm test.
- Responde con un resumen: qué creaste/modificaste, archivos, verificación, y DoD cumplida/no cumplida.
```

---

## 9. Fases, Tasks, Prompts y DoD

> Cada Task = **PROMPT BASE (§8) + bloque específico + DEFINITION OF DONE**. Ejecutar en orden; no pasar a la siguiente sin DoD cumplida.

---

### FASE 0 — Higiene y base técnica

**Objetivo:** dejar un proyecto limpio, sin deuda del starter, con tipos exactos y utilidades base.
**Resultado esperado:** build limpio, sin secretos públicos, tipos correctos, calculadora validada.
**Criterios de fase terminada:** `pnpm build` OK · `pnpm typecheck` OK · `pnpm lint` OK · sin imports de starter.

#### T0.1 — Limpieza del starter y configuración base

```
TASK: Limpieza del starter y configuración base.
- Revisa y corrige nuxt.config.ts:
  - Quita SECRET_KEY del runtimeConfig.public. Define runtimeConfig.public.apiBase desde NUXT_PUBLIC_API_BASE (con fallback http://localhost:8000). Elimina claves login/cliente del runtimeConfig (se usarán rutas de servicio, no config).
  - Asegura compatibilityVersion: 4, modules: ['@nuxt/eslint', '@nuxt/ui', '@pinia/nuxt'].
  - Prepara estructura para fuentes self-hosted (carpeta app/public/fonts y @fontsource en package.json si no están).
- app.vue: reemplaza la metadata del starter (título en inglés, ogImage del template) por metadata propia: title 'LoanSoft — Gestión de Préstamos', htmlAttrs lang="es", meta description y theme-color morado. Quita el ogImage del starter.
- Elimina componentes de starter que no se usen: components/TemplateMenu.vue, components/Layout/Navbar.vue (se reconstruirá en T2.2), components/AppLogo.vue si no se usa en la nueva marca (crea un AppLogo simple con las siglas "LS" usando el token --color-primary).
- Elimina pages/Home.vue (placeholder).
- Crea app/error.vue con estados: error de red, 404, 500; usa Nuxt UI, en español.
- Crea .env.example con NUXT_PUBLIC_API_BASE=http://localhost:8000.
- No rompas components/Layout/Aside.vue, Layout/Table.vue, stores/varView.ts, pages/Clientes.vue: se evolucionarán en fases siguientes.

DEFINITION OF DONE:
- pnpm typecheck y pnpm lint en verde.
- grep 'SECRET_KEY' no aparece en nuxt.config.ts ni en código cliente.
- No quedan componentes TemplateMenu/Navbar/AppLogo de starter ni pages/Home.vue.
- app.vue tiene lang="es" y metadata propia.
- .env.example existe y se documenta su copia a .env.
```

#### T0.2 — Tipos TypeScript exactos (espejo del backend)

```
TASK: Tipos TypeScript exactos en shared/types.
- Crea la carpeta shared/types y MUEVE los archivos existentes de app/types/* (clientes, prestamo, prestamo_cuota, pago, capital, mora, tipo_prestamo, tipo_pago, movimiento_capital, prestamo_perdido, prestamo_renovacion, usuario).
- Revisa y corrige CADA tipo contra el backend real (ver BLUEPRINT_LOANSOFT.md §1.1):
  - Mora.fecha: string (no Date). Mora.estado: string.
  - Pago: todos los campos del POST (capital_pagado, interes_pagado, mora_pagada son requeridos, no opcionales). Pago.created_at/updated_at existe en PagoOut (ORM), mantenlos.
  - Prestamo: sin created_at/updated_at en PrestamoOut (son opcionales solo si vienen de marcar_perdido). PrestamoDetalle = Prestamo + cliente + tipo_prestamo + cuotas + pagos.
  - Capital: { id: number; monto_total: number; updated_at?: string }.
  - TipoPago: incluye estado ('activo'|'inactivo') e id.
  - Usuario: el campo hashed_password NO debe exponerse; define UsuarioMe { id, nombre, email, rol, estado }.
- Agrega tipos nuevos faltantes (contrato real):
  - AuthTokenResponse { access_token, refresh_token, token_type }.
  - AuthRefreshResponse { access_token, token_type }.
  - ApiError { status: number; detail: string; field?: string }.
  - ReporteGanancias { periodo, total_invertido, total_prestado, total_pagos_recibidos, total_intereses, ganancia_neta }.
  - ReportePerdidas { periodo, total_perdidas, cantidad_prestamos_perdidos, detalle: [{ prestamo_id, fecha: string, valor_perdido, motivo: string|null }] }.
  - RespuestaMovimientoCapital { movimiento: MovimientoCapital & { prestamo_id?: number | null; created_at?: string }; capital_actual: number }.
  - RespuestaMarcarPerdido { prestamo: Prestamo & { created_at?: string; updated_at?: string }; valor_perdido: number; motivo: string | null; fecha: string }.
  - RespuestaProcesarMoras { moras_actualizadas: number[] }.
  - LoginPayload { email: string; password: string }.
- Exporta todo desde shared/types/index.ts para importación limpia.

DEFINITION OF DONE:
- pnpm typecheck OK (strict, sin any).
- Cada tipo está respaldado por el backend (ver §1.1 y §2 de la API real).
- No hay campos inventados ni tipos de 'stub'.
```

#### T0.3 — Utilidades base: formatters y calculadora de préstamo

```
TASK: Utilidades base (app/utils y composables).
- Crea app/utils/format.ts: formateo de dinero COP (Intl.NumberFormat 'es-CO', COP, min/max 0 decimales para pesos), número decimal con separador.
- Crea app/utils/fecha.ts: parsear 'YYYY-MM-DD' a Date local (evitar desfase de zona), formatear a 'dd/mm/yyyy', calcular 'hace X días', añadir meses (usar lógica calendario: día 31 → último día del mes, replicando relativedelta).
- Crea app/utils/calculadoraPrestamo.ts con réplica EXACTA de las fórmulas del backend:
  - redondear(x) = Math.round((x + Number.EPSILON) * 100) / 100 (aproxima banker's del backend; documentar divergencia).
  - calcularPrestamo({ capital_prestado, porcentaje_interes, numero_cuotas }): devuelve interes_total, monto_total, valor_cuota, saldo_pendiente con las fórmulas del backend.
  - calcularCuotas({ capital_prestado, interes_total, numero_cuotas, fecha_prestamo }): genera la lista de cuotas con capital=round(capital/num), interes=round(interes_total/num), fecha_vencimiento = fecha + i meses. Incluye el mismo comportamiento (última cuota NO ajustada).
  - validarCuadrePago({ capital_pagado, interes_pagado, mora_pagada, valor_pagado }): tolerancia 0.01.
  - topePago(cuota, mora) = cuota.valor_cuota + mora + 0.01.
- Crea app/composables/useFormatters.ts que expone refs/helpers usando los utils (formatoMoneda, formatoPorcentaje, formatoFecha, formatearCedula si aplica).
- Escribe tests unitarios (Vitest) de calculadoraPrestamo: al menos 5 casos (valores redondos, decimales, alto número de cuotas, capital alto) y verifica que el desglose suma.
- Agrega vitest y @vue/test-utils a devDependencies si no están; script "test": "vitest run" en package.json.

DEFINITION OF DONE:
- Tests de la calculadora pasan (pnpm test).
- pnpm typecheck y pnpm lint OK.
- useFormatters disponible con auto-import.
- La calculadora replica el backend en casos típicos (comprobar contra /prestamos/ creación real en Fase 4).
```

---

### FASE 1 — Infraestructura de sesión y datos

**Objetivo:** capa HTTP robusta, autenticación completa, rutas protegidas y manejo global de errores.
**Dependencias:** Fase 0.
**Criterios de fase terminada:** login/logout/refresh funcionales contra la API real; rutas protegidas; errores normalizados.

#### T1.1 — Cliente HTTP (useApi) y migración de services

```
TASK: Cliente HTTP central (reemplaza axios).
- Crea app/composables/useApi.ts (auto-importable):
  - baseURL desde runtimeConfig.public.apiBase.
  - $fetch con interceptor de request: añade Authorization: Bearer <access_token>.
  - Interceptor de response: 
    - 401 → intentar POST /auth/refresh con refresh_token una vez → reintentar request original → si falla, cerrar sesión (useAuthStore.logout) y redirigir a /login.
    - Normalizar errores a ApiError { status, detail, field? }. Extraer detail de { detail } o { mensaje } o 'Error inesperado'.
    - 403 (sin sesión/permiso): enrutar a login o mostrar mensaje de permisos según contexto.
    - soporte responseType: 'blob' para descargas.
  - Expón helpers: apiGet, apiPost, apiPut, apiDelete, apiDownload (blob).
- Migra services/api/*:
  - services/api/login.ts: usar useApi; eliminar axios y withCredentials; guardar tokens en el store (no solo localStorage).
  - services/api/clientes.ts: usar useApi con tipos de shared/types; agregar updateCliente, deleteCliente (soft), getClienteById ya existe.
  - Elimina services/api.ts (axios) una vez todo migrado.
- No olvides que services se ejecutan también del lado servidor (SSR): protege el acceso a localStorage con isClient().

DEFINITION OF DONE:
- Ningún import de 'axios' en el código de la app.
- useApi maneja refresh-once y logout automático.
- pnpm typecheck, pnpm lint OK.
```

#### T1.2 — Store de autenticación completo

```
TASK: Store de autenticación (stores/auth.ts) completo.
- Estado: accessToken, refreshToken, user (UsuarioMe), status: 'idle'|'loading'|'authenticated'|'unauthenticated'.
- Persistencia: localStorage (claves prefijadas, p.ej. 'loansoft:access', 'loansoft:refresh'); hidratación al iniciar la app (getters/isClient).
- Actions:
  - async login(email, password): POST /auth/login → guardar tokens → GET /auth/me → setear user.
  - async fetchMe(): GET /auth/me (revalida el rol/estado).
  - async refresh(): POST /auth/refresh → actualiza accessToken.
  - async logout(): POST /auth/logout (best-effort) → limpiar estado y localStorage.
  - getters: isAuthenticated, isAdmin (rol === 'admin'), hasAccess(rolRequerido).
- El store debe ser la ÚNICA fuente de tokens. useApi lee de aquí.
- En pages/Clientes.vue y otros existentes, elimina el uso directo de localStorage.

DEFINITION OF DONE:
- Sesión sobrevive recarga (se hidrata y llama fetchMe).
- logout limpia tokens y usuario.
- pnpm typecheck y lint OK.
- Login contra la API real funciona (seed: admin@test.com / 123456).
```

#### T1.3 — Página de login + layouts + middleware de rutas

```
TASK: Login, layouts y middleware de rutas.
- Crea app/middleware/auth.ts: si no isAuthenticated → redirect('/login'). Define definePageMeta({ middleware: 'auth' }) en las páginas protegidas (global en layout default también sirve).
- Crea app/middleware/guest.ts: si isAuthenticated → redirect('/').
- Crea app/middleware/admin.ts: si !isAdmin → redirigir a '/' (y ocultar navegación).
- Refactoriza pages/login.vue (hoy es index.vue):
  - Define pageMeta: layout 'auth', middleware 'guest'.
  - Diseño: centrado, tarjeta glass sobre fondo morado degradado, logo, título 'Inicia sesión', campos email + contraseña (UInput con iconos i-lucide-mail / i-lucide-lock), botón Ingresar con estado loading, mensaje de error (401 → 'Email o contraseña incorrectos'), soporta Enter para enviar.
  - Validación Zod: email formato, password min 6.
  - Al loguear: redirige a '/'.
- Crea layouts/auth.vue (existe, refina): mantén el fondo con imagen (public/assets/img/fondo.png si existe) o degradado morado; layout centrado; slot.
- pages/index.vue deja de ser login: queda como placeholder del Dashboard (se implementa en Fase 6) con layout default y middleware auth.
- pages/Clientes.vue: agrega definePageMeta middleware 'auth' y layout default (si aplica).

DEFINITION OF DONE:
- Acceso a rutas protegidas sin sesión → /login; con sesión → no se puede ver /login.
- Login con credenciales inválidas muestra error 401 en español.
- pnpm typecheck, lint OK.
```

#### T1.4 — Toasts y manejo global de errores

```
TASK: Toasts y manejo global de errores.
- Crea app/plugins/toast.ts: registra toast success/error/info/warning global (usa useToast de Nuxt UI). Expón useToast o un composable useAppToast.
- Crea un helper en useApi para registrar automáticamente errores de red/5xx como toast de error global (pero no los 400 de validación, que se muestran en el formulario).
- Maneja 'sesión expirada': al hacer logout automático por refresh fallido, mostrar toast 'Tu sesión expiró, inicia sesión nuevamente'.
- Aplica toast en el login (éxito y error).

DEFINITION OF DONE:
- Errores 5xx/red muestran toast amigable; 400 de formulario NO hacen toast duplicado.
- pnpm typecheck, lint OK.
```

---

### FASE 2 — Design System y AppShell

**Objetivo:** tema visual, shell de la app y kit de componentes reutilizables.
**Dependencias:** Fase 1.
**Criterios de fase terminada:** shell funcional, kit documentado, estados de UI consistentes.

#### T2.1 — Tokens, tema y fuentes

```
TASK: Tokens de diseño y tema (morado/amarillo/gris + glass).
- app.config.ts: ui.colors primary 'purple', neutral 'slate' (ya existe; verifica coherencia).
- assets/css/main.css:
  - Define/refuerza tokens CSS: --accent-purple, --accent-gold (#d4af37), --accent-gold-soft, escala de neutros, --color-primary (#7c3aed).
  - Glass: utilidad/referencia .glass { background: rgba(255,255,255,0.06); backdrop-filter: blur(12px); border: 1px solid rgba(124,58,237,0.18) } y variantes dark/light.
  - Dark mode por defecto vía useColorMode en layout.
- Fuentes self-hosted:
  - Agrega @fontsource-variable/inter y @fontsource/poppins (o similar) a dependencies.
  - Importa en nuxt.config css o main.css: 'Inter Variable' como cuerpo, 'Poppins' como display.
  - Define en @theme: --font-sans: 'Inter Variable', --font-display: 'Poppins'.
  - Clases: .font-display para títulos y números KPI.
- Verifica que los componentes Nuxt UI usan primary/neutral coherentes. No cambies el diseño del Aside existente (se refina en T2.2).

DEFINITION OF DONE:
- Modo dark/light funciona (useColorMode).
- Las fuentes se cargan localmente (sin requests a Google Fonts en el bundle).
- pnpm build OK (fuentes incluidas).
```

#### T2.2 — AppShell: sidebar, header y layout

```
TASK: AppShell (sidebar + header + layout default).
- Evoluciona components/Layout/Aside.vue → usa las rutas REALES del blueprint (§4.4):
  Secciones: Principal (Dashboard '/'), Préstamos ('/prestamos'), Clientes ('/clientes'), Cobranza ('/cobranza'), Reportes ('/reportes'), Configuración (admin: '/tipos-prestamo', '/tipos-pago', '/capital', '/usuarios').
  - Marca items admin con icono candado y solo visibles si isAdmin (useAuthStore).
  - Mantén la animación colapsable y el footer de usuario con datos reales (nombre + rol desde auth store, iniciales del avatar).
  - Logout del footer llama a authStore.logout() y redirige a /login.
  - Acceso rápido: en la sección Principal, item Dashboard y un acceso a 'Crear préstamo' ('/prestamos/nuevo', icono i-lucide-plus).
- Crea components/app/AppHeader.vue:
  - Breadcrumb o título de página actual (useRoute + meta), búsqueda (placeholder, se conecta en fases futuras), SyncIndicator (estado conexión/sync, se implementa T2.4/T7.4), CommandPalette trigger (Ctrl+K, se implementa T8.1; por ahora oculto o mínimo), color mode toggle, menú de usuario (perfil, cerrar sesión).
- layouts/default.vue: integra LayoutAside + AppHeader + <main><slot/></main> manteniendo el sistema de flex/scroll actual.
- Elimina components/Layout/Navbar.vue del starter.

DEFINITION OF DONE:
- Navegación funcional con rutas reales; items admin ocultos para rol 'usuario'.
- Sidebar colapsable y responsive (drawer en móvil si aplica).
- Usuario real en footer (nombre, rol, iniciales).
- pnpm typecheck, lint OK.
```

#### T2.3 — Kit UI base reutilizable

```
TASK: Kit UI base (components/ui).
- DataTable.vue: evolución TS de components/Layout/Table.vue manteniendo su API (Propiedades { titulo, data, columns, filtros, buttons, agregar }) pero:
  - Convierte el archivo y las composables de apoyo a TypeScript (composables/table/useDatosOrdenados.js, usePaginacion.js → .ts con tipos).
  - Mantiene: orden por columna (sorted), filtro global, filtros por columna con opciones, filtros mes/año, paginación, selector de items por página, botones acciones, badge de filtros activos, botón limpiar.
  - Estados: loading (skeleton), vacío (EmptyState), error (mensaje + reintentar).
  - Export: botón exportar CSV/Excel del dataset actual (sin depender del endpoint backend).
- ModalDialog.vue: wrapper de UModal con título, slots body/footer, confirmación de cierre.
- ConfirmDialog.vue: confirmación destructiva (titulo, mensaje, botón confirmar color error, loading).
- EstadoBadge.vue: badge tipado por entidad/estado (prestamo, cuota, cliente, tipo) con los colores del §4.3.
- StatCard.vue: tarjeta KPI { titulo, valor, icono, color, trend?, footer? } con variante glass.
- EmptyState.vue: icono + título + descripción + slot acción.
- Skeleton.vue: bloque de carga (o usa USkeleton).
- FormField.vue: wrapper UFormField + label + error (integra Zod + valida en blur).
- MoneyInput.vue: input monetario (formato COP, entrada numérica, manejo de 0, placeholder '$ 0').
- Documenta el uso de cada componente en un comentario breve de cabecera.

DEFINITION OF DONE:
- DataTable.ts tipado, funcional y reutilizado por pages/Clientes.vue (refactorízalo para que lo use con tipos).
- Componentes con estados (loading/error/vacio).
- pnpm typecheck, lint OK.
```

#### T2.4 — Estados globales de UI (conexión y sincronización)

```
TASK: Estados globales de conexión y sincronización.
- Crea stores/ui.ts: expande stores/varView.ts o crea ui.ts con showAside, cargando, actualizando.
- Crea composables/useOffline.ts: estado reactivo isOffline basado en navigator.onLine + listeners online/offline + heartbeat (fetch ligero a / cada 30s opcional). Expón isOnline.
- Crea components/app/ConnectionBanner.vue: barra global visible cuando isOffline ('Sin conexión — los datos mostrados pueden estar desactualizados. Los pagos se guardarán en cola.') y cuando hay operaciones pendientes de sincronizar ('X pagos pendientes de sincronizar').
- Crea components/app/SyncIndicator.vue: indicador compacto en header (punto verde/ámbar/rojo + tooltip con última sincronización y contador pendiente).
- Crea stores/sync.ts: estado { isOnline, lastSyncAt, pendingCount, syncing }.
- Integra en layouts/default.vue y AppHeader.

DEFINITION OF DONE:
- Al desconectar la red, aparece el banner en <3s; al reconectar, desaparece y dispara sync.
- pnpm typecheck, lint OK.
```

---

### FASE 3 — Módulos administrativos

**Objetivo:** CRUD de clientes, tipos y capital.
**Dependencias:** Fase 2.
**Criterios de fase terminada:** CRUDs funcionales contra API real con gate de roles.

#### T3.1 — Clientes CRUD

```
TASK: Módulo de clientes (listado + formulario + soft delete).
- services/api/clientes.ts: completa las funciones tipadas (getClientes con skip/limit, createCliente, updateCliente, deleteCliente).
- composables/domain/useClientes.ts: estado { clientes, loading, error }, acciones fetch(), crear(data), actualizar(id, data), eliminar(id). Refresca el listado tras cada mutación.
- pages/clientes/index.vue:
  - Usa DataTable con columnas: id, nombre, cedula, telefono, direccion, estado (EstadoBadge), acciones.
  - Búsqueda global por nombre/cédula (cliente-side con useDatosOrdenados; el backend no tiene /clientes/buscar).
  - Botón Agregar → ModalDialog con ClienteForm.
  - Editar → modal pre-cargado; Eliminar → ConfirmDialog (soft-delete, mensaje '¿Eliminar cliente?' con warning de que se desactiva).
  - Manejo de error 400 cédula duplicada: mostrar en el campo cedula ('Ya existe un cliente con esa cédula').
  - Estados loading/error/vacío.
- components/clientes/ClienteForm.vue: formulario con validación Zod espejo de ClienteCreate (nombre y cedula requeridos; max lengths: nombre 100, cedula 20, telefono 20, direccion 200, persona_referencia 100, telefono_referencia 20). Campos opcionales: persona_referencia, telefono_referencia, observaciones.
- Refactoriza pages/Clientes.vue actual para que use el nuevo módulo (o redirige /Clientes a /clientes). Mantén compatibilidad: crea la ruta /clientes y deja que el sidebar apunte ahí.

DEFINITION OF DONE:
- Crear/editar/eliminar funcionan contra la API real (seed: admin@test.com/123456).
- Cédula duplicada muestra error en el campo.
- pnpm typecheck, lint OK.
```

#### T3.2 — Tipos de préstamo CRUD (admin)

```
TASK: Módulo de tipos de préstamo (solo admin).
- services/api/tipo.ts: funciones para tipo_prestamo y tipo_pago tipadas.
- composables/domain/useTipos.ts: useTiposPrestamo y useTiposPago con fetch/crear/editar/eliminar.
- pages/tipos-prestamo/index.vue: definePageMeta middleware 'admin' (y layout default). DataTable con nombre, interes_mensual (%), max_cuotas, estado, acciones. Formulario modal con validación Zod (nombre req, descripcion req, interes_mensual > 0, max_cuotas >= 1). Soft delete con confirmación. Manejar 403 → mensaje de permisos.
- Asegura que la navegación del sidebar solo muestre este item a admins (T2.2).

DEFINITION OF DONE:
- CRUD admin funcional; rol usuario NO ve la ruta y recibe mensaje de permisos si fuerza la URL.
- pnpm typecheck, lint OK.
```

#### T3.3 — Tipos de pago CRUD (admin)

```
TASK: Módulo de tipos de pago (solo admin).
- Igual que T3.2 para /tipos-pago: campos nombre (req, max 50) y descripcion (req). DataTable + formulario modal + soft delete + confirmación.

DEFINITION OF DONE:
- CRUD admin funcional contra /tipo_pago.
- pnpm typecheck, lint OK.
```

#### T3.4 — Capital

```
TASK: Módulo de capital (admin).
- services/api/capital.ts: getCapital(), registrarMovimiento({ tipo_movimiento: 'inversion'|'retiro', descripcion?, valor, fecha }).
- composables/domain/useCapital.ts: estado { capital, loading, error }, fetch(), inversion(datos), retiro(datos).
- pages/capital/index.vue (admin):
  - Tarjeta KPI con monto total (StatCard, formato COP) + última actualización.
  - Formulario de inversión y retiro (tabs o dos tarjetas): tipo de movimiento, descripcion, valor (MoneyInput), fecha (date).
  - Validación en vivo: retiro no puede exceder el monto actual (mostrar aviso y deshabilitar botón si supera).
  - Confirmación para retiro ('Esta acción reduce el capital disponible').
  - Historial de movimientos: NO existe endpoint (REQUIERE_BACKEND B2). Muestra una sección con EmptyState: 'El historial de movimientos estará disponible próximamente' + botón para exportar un resumen local si aplica. NO inventes datos.
  - Actualiza el KPI tras cada operación con la respuesta capital_actual.

DEFINITION OF DONE:
- Inversión y retiro funcionan contra la API real; retiro > monto se bloquea en UI.
- La sección de historial NO muestra datos falsos (EmptyState con nota).
- pnpm typecheck, lint OK.
```

---

### FASE 4 — Núcleo financiero: préstamos

**Objetivo:** listado con filtros, creación con calculadora y detalle con cuotas.
**Dependencias:** Fase 3.
**Criterios de fase terminada:** creación/renovación/perdido contra API real; cálculos cuadran.

#### T4.1 — Listado de préstamos con filtros

```
TASK: Listado de préstamos.
- services/api/prestamo.ts: getPrestamos({ estado, cliente_id, fecha_desde, fecha_hasta, busqueda, skip, limit }), getPrestamoById.
- composables/domain/usePrestamos.ts: estado { prestamos, loading, error, filtros }, fetch(), byId(id).
- pages/prestamos/index.vue:
  - DataTable con columnas: id, cliente.nombre, cedula (cliente.cedula), fecha_prestamo, capital_prestado, monto_total, saldo_pendiente, valor_cuota, numero_cuotas, estado (EstadoBadge), acciones (ver detalle).
  - Filtros SERVER-SIDE (query params reales): estado (todos/activo/pagado/perdido/renovado), búsqueda por nombre/cédula (input que dispara busqueda), rango de fechas fecha_desde/fecha_hasta.
  - Paginación con skip/limit (backend no devuelve total; muestra nota 'Mostrando resultados' y botón cargar más o paginación manual).
  - Botón 'Nuevo préstamo' → /prestamos/nuevo.
  - Estados loading/error/vacío.

DEFINITION OF DONE:
- Filtros funcionan contra los query params reales (verificar contra API).
- Saldo/valores en formato COP con useFormatters.
- pnpm typecheck, lint OK.
```

#### T4.2 — Creación de préstamo con calculadora

```
TASK: Creación de préstamo con calculadora en vivo.
- pages/prestamos/nuevo.vue:
  - Selector de cliente: búsqueda por nombre o cédula (input + dropdown/combobox). Muestra info del seleccionado. Usa useClientes (carga lista).
  - Selector de tipo de préstamo (useTiposPrestamo): al seleccionar, AUTORELLENA porcentaje_interes (interes_mensual) y sugiere numero_cuotas (max_cuotas).
  - Campos: fecha_prestamo (default hoy), capital_prestado (MoneyInput), porcentaje_interes (número, editable), numero_cuotas (número, >= 1), observaciones (opcional).
  - Panel de capital disponible (useCapital): muestra monto actual y valida capital_prestado <= monto (aviso en rojo y botón deshabilitado si excede).
  - CALCULADORA EN VIVO (useCalculadoraPrestamo / calculadoraPrestamo.ts): preview de interes_total, monto_total, valor_cuota, saldo_pendiente + desglose de las primeras cuotas o tabla resumida. Se actualiza en cada cambio.
  - Validación Zod: cliente req, tipo req, capital > 0, porcentaje > 0, numero_cuotas >= 1, fecha válida.
  - Al enviar: POST /prestamos → éxito (200) → redirigir a /prestamos/[id]. Manejar 400 'Capital insuficiente' mostrando el mensaje y resaltando el panel de capital.
  - Estados: loading del submit con overlay en botón.

DEFINITION OF DONE:
- La calculadora en vivo replica el backend (comparar con un préstamo real creado con los mismos datos).
- Flujo completo crear→detalle sin errores.
- pnpm typecheck, lint OK.
```

#### T4.3 — Detalle de préstamo con cuotas y pagos

```
TASK: Detalle de préstamo.
- pages/prestamos/[id].vue:
  - Carga GET /prestamos/{id} (detalle con cliente, tipo, cuotas, pagos).
  - Cabecera: cliente (nombre + cédula), estado (EstadoBadge), KPIs (StatCard): capital_prestado, interes_total, monto_total, saldo_pendiente, valor_cuota, numero_cuotas, fecha.
  - Tabla de cuotas: numero_cuota, fecha_vencimiento, valor_cuota, capital, interes, mora, estado (EstadoBadge), y acción 'Registrar pago' si estado === 'pendiente' (enlaza a /pagos?prestamo_id= o modal, según diseño definido en Fase 5).
  - Sección de pagos del préstamo (de pagos del detalle): fecha, valor, capital, interes, mora, tipo de pago, observaciones.
  - Acciones contextuales: 'Renovar préstamo' (si estado activo), 'Marcar como perdido' (si estado activo), ambas con confirmación → modales de T4.4.
  - Historial de renovaciones: el detalle no lo incluye; muestra nota/EmptyState (REQUIERE_BACKEND: no hay endpoint de renovaciones por préstamo; se puede derivar buscando préstamos del cliente con estado renovado como aproximación, pero NO inventar).
  - Estados loading/error/404.

DEFINITION OF DONE:
- Detalle completo renderiza datos reales.
- Solo se ofrece 'Registrar pago' en cuotas pendientes.
- pnpm typecheck, lint OK.
```

#### T4.4 — Renovar y marcar perdido

```
TASK: Modales de renovación y préstamo perdido.
- components/prestamos/RenovarModal.vue:
  - Campos: porcentaje_interes (req), numero_cuotas (req, >=1), abono (default 0, <= saldo_pendiente, validado en vivo), fecha_renovacion (req, default hoy), observaciones.
  - Preview con la calculadora: muestra capital nuevo (saldo - abono), nuevo monto, nueva cuota.
  - POST /prestamos/{id}/renovar → éxito → recargar detalle. Manejar 400 'El abono no puede ser mayor al saldo pendiente' y 'No se puede renovar un prestamo en estado X'.
  - Advertencia informativa: 'La renovación genera un nuevo préstamo y el original pasa a estado renovado.'
- components/prestamos/MarcarPerdidoModal.vue:
  - Confirmación fuerte (ConfirmDialog o modal con input de motivo): motivo (opcional), fecha (req).
  - Muestra valor a perder = saldo_pendiente (COP) y advertencia clara.
  - POST /prestamos/{id}/marcar_perdido → éxito → recargar. Manejar 400 estado inválido.
- Integra ambos desde pages/prestamos/[id].vue.

DEFINITION OF DONE:
- Renovación crea el nuevo préstamo y muestra el detalle actualizado (original en renovado).
- Marcar perdido cambia estado y registra movimiento.
- pnpm typecheck, lint OK.
```

---

### FASE 5 — Pagos y moras

**Objetivo:** registro de pagos con desglose validado + módulo de moras.
**Dependencias:** Fase 4.
**Criterios de fase terminada:** pago/desglose correctos; moras funcionales.

#### T5.1 — Registro de pagos

```
TASK: Registro de pago con desglose asistido.
- services/api/pago.ts: getPagos({ skip, limit }), createPago(payload).
- pages/pagos/index.vue:
  - Dos vistas (tabs): 'Registrar pago' y 'Historial'.
  - REGISTRAR:
    - Paso 1: seleccionar préstamo (búsqueda por cliente/cédula; muestra saldo y cuotas pendientes). O directamente se llega desde /prestamos/[id] con ?prestamo_id= y se precarga.
    - Paso 2: seleccionar cuota pendiente (select con numero_cuota, vencimiento, valor). SOLO pendiente; las vencidas/parciales muestran 'No pagable con la API actual' (tooltip informativo, REQUIERE_BACKEND: permitir pagar vencidas).
    - Paso 3: desglose — tipo_pago (select), fecha_pago (date), valor_pagado (MoneyInput), capital_pagado, interes_pagado, mora_pagada. Asistente: al elegir valor_pagado <= cuota+mora, sugiere desglose (capital = cuota.capital, interes = cuota.interes, mora = valor - capital - interes) y permite ajustarlo. VALIDA en vivo: capital+interes+mora ≈ valor_pagado (tol 0.01) y valor_pagado <= cuota.valor_cuota + mora + 0.01.
    - Submit habilitado solo si desglose válido. POST /pagos → éxito → limpiar y refrescar. Manejar 400 de cuadre/overpago mostrando el mensaje.
  - HISTORIAL: tabla de pagos (GET /pagos) paginada cliente-side; columnas fecha, cliente, prestamo, cuota, valor, capital, interes, mora, tipo. Nota: el endpoint no ordena/filtra.
- components/pagos/PagoForm.vue: encapsula el formulario de desglose (reutilizable también desde el detalle de préstamo).

DEFINITION OF DONE:
- Un pago con desglose válido se registra y la cuota pasa a pagado/parcial en la API.
- La UI NO permite enviar desgloses inválidos.
- pnpm typecheck, lint OK.
```

#### T5.2 — Módulo de moras

```
TASK: Módulo de moras.
- services/api/mora.ts: getMoras(), getMorasByPrestamo(id), procesarMoras(), updateMora(id, data), deleteMora(id).
- pages/moras/index.vue:
  - Cabecera con explicación: 'La mora se calcula al 1% diario sobre el valor de la cuota por los días de atraso.' + botón 'Procesar moras ahora' (POST /moras/procesar-moras) con confirmación y toast de resultado (X moras actualizadas).
  - Tabla de moras (GET /moras, solo generada): prestamo, cuota, fecha, valor (COP), estado.
  - Filtro por préstamo: GET /moras/prestamo/{id} (input de préstamo opcional).
  - Acciones por fila: editar (modal con los campos de MoraBase: prestamo_id, cuota_id, fecha (string YYYY-MM-DD), valor, estado) y eliminar (soft? no: DELETE real, confirmar).
  - Nota informativa: 'El cálculo automático diario requiere programación en el backend (REQUIERE_BACKEND B7).'
- En pages/prestamos/[id].vue: sección de moras del préstamo usando getMorasByPrestamo (o los datos de cuotas) mostrando mora acumulada por cuota.

DEFINITION OF DONE:
- Procesar moras devuelve resultado y refresca la tabla.
- pnpm typecheck, lint OK.
```

---

### FASE 6 — Dashboard y reportes

**Objetivo:** KPIs, gráficas y reportes con exportación.
**Dependencias:** Fase 5.
**Criterios de fase terminada:** dashboard con datos reales; reportes descargables.

#### T6.1 — Dashboard

```
TASK: Dashboard con KPIs y gráficas.
- Instala vue3-apexcharts (+ apexcharts) si no están. Crea un wrapper components/dashboard/ApexChart.vue que registre los charts una sola vez (opciones reutilizables).
- pages/index.vue:
  - Carga en paralelo: GET /capital, GET /prestamos?estado=activo, GET /reportes/ganancias, GET /reportes/perdidas, y (si existe REQUEST_BACKEND B3 no aplica aún) combina.
  - KPIs (StatCard): Capital actual, Cartera activa (número de préstamos activos), Saldo pendiente total (Σ saldo_pendiente de activos, calculado en cliente — el backend no lo agrega), Ganancia del periodo (reportes/ganancias.ganancia_neta), Total prestado en el periodo, Mora acumulada (suma de moras generadas si datos disponibles).
  - Gráficas:
    - Tendencia de pagos recibidos vs prestado (por mes): el backend no agrega por mes; usa reportes/ganancias por periodo actual como dato puntual y un gráfico simple con datos disponibles. NO inventes series extensas: si no hay datos históricos por mes, muestra una tarjeta con el periodo actual y una nota 'Los datos históricos por mes requieren el endpoint de dashboard (REQUIERE_BACKEND B3)'.
    - Distribución de préstamos por estado (activo/pagado/perdido/renovado): calcular en cliente con GET /prestamos?estado=todos (limit alto) — asume dataset pequeño; si crece, REQUIERE_BACKEND.
  - Accesos rápidos: botones a /prestamos/nuevo, /pagos, /clientes, /reportes.
  - Estados loading (skeletons de tarjetas), error (retry), vacío (primeros pasos si no hay datos).
- Recuerda: el Dashboard en el scaffold actual no existe (index era login). Crea el módulo desde cero.

DEFINITION OF DONE:
- KPIs muestran datos reales de la API (combinando endpoints existentes).
- Gráficas se renderizan sin errores de consola.
- No hay datos fabricados: secciones sin respaldo muestran nota.
- pnpm typecheck, lint OK.
```

#### T6.2 — Reportes de ganancias y pérdidas

```
TASK: Reportes ganancias/pérdidas + exportación.
- services/api/reporte.ts: getReporteGanancias({ mes?, anio? }), getReportePerdidas({ mes?, anio? }), descargarReporte(tipo: 'ganancias'|'perdidas', formato: 'excel'|'pdf', { mes?, anio? }) → blob → descargar archivo con nombre correcto (ganancias.xlsx, ganancias.pdf, perdidas.xlsx, perdidas.pdf). Usa useApi con responseType blob. El content-disposition no se puede leer cross-origin de forma fiable: genera el nombre en cliente.
- pages/reportes/index.vue:
  - Filtros globales: mes (select 1-12 con nombres) y año (select de años disponibles o input), con 'Todos' por defecto. Aplicar recarga.
  - Tab Ganancias: KPIs (total invertido, total prestado, total pagos recibidos, total intereses, ganancia neta) + nota de que la fórmula del backend es pagos_recibidos − prestado + invertido.
  - Tab Pérdidas: total perdidas, cantidad de préstamos perdidos + tabla de detalle (prestamo_id, fecha, valor_perdido, motivo).
  - Botones de exportación Excel/PDF por tab (blob descarga).
  - Estados loading/error/vacio.
- Verifica que el archivo descargado se abre correctamente (prueba manual).

DEFINITION OF DONE:
- Filtros mes/año cambian la respuesta (verificar contra API).
- Excel y PDF se descargan y abren correctamente (ambos formatos, ambos reportes).
- pnpm typecheck, lint OK.
```

#### T6.3 — Exportación genérica de tablas

```
TASK: Exportación de datos desde tablas (CSV/XLSX cliente-side).
- En DataTable.vue: implementa el botón 'Exportar' que ya estaba esbozado: genera CSV (y XLSX si agregas xlsx client-side, p.ej. 'xlsx' package) del dataset filtrado (datosOrdenados) con los nombres de columna legibles.
- Aplica la exportación en: clientes, prestamos (listado), pagos (historial), moras, cuotas del detalle.
- Respeta el diseño del botón Exportar del layout actual.

DEFINITION OF DONE:
- Exportar descarga un archivo con la data filtrada actual.
- pnpm typecheck, lint OK.
```

---

### FASE 7 — PWA, Offline y Sincronización

**Objetivo:** app instalable, offline-first con cola de pagos y reconciliación.
**Dependencias:** Fase 6.
**Criterios de fase terminada:** sin conexión la app funciona para lectura y encola pagos; al reconectar se sincroniza sin duplicados.

#### T7.1 — PWA base (manifest, instalación, actualizaciones)

```
TASK: Integración PWA base con @vite-pwa/nuxt.
- Agrega @vite-pwa/nuxt a modules. Configura en nuxt.config.ts:
  - registerType: 'autoUpdate' (con prompt de recarga) o 'prompt'.
  - manifest: name 'LoanSoft — Gestión de Préstamos', short_name 'LoanSoft', lang 'es', theme_color morado (#7c3aed), background_color, display 'standalone', icons (192, 512, maskable) — genera iconos png en app/public/icons (puedes generarlos con un script o assets).
  - workbox: globPatterns de assets, navigateFallback a '/'.
  - registerWebManifestInRouteRules para precache.
- Crea composables/usePwaInstall.ts: captura beforeinstallprompt, expone canInstall + promptInstall().
- Crea components/app/InstallPrompt.vue o botón en el header (visible solo si canInstall).
- Manejo de actualización: listener en SW (updatefound / registrando) → toast 'Hay una nueva versión disponible' + botón 'Recargar' (location.reload).
- Verifica que se genera el SW en build.

DEFINITION OF DONE:
- `pnpm build` genera manifest + service worker + precache del app shell.
- En dev/preview, la app es instalable y muestra el prompt de actualización.
- No se rompe el SSR (PWA client-only).
```

#### T7.2 — Service Worker: estrategias de cache

```
TASK: Estrategias de caching en el SW.
- Configura workbox en nuxt.config:
  - App shell: precache (automatizado).
  - Assets estáticos (_nuxt): CacheFirst con versión por build.
  - Peticiones a la API (network https://localhost:8000/*): NetworkFirst con fallback a cache de respuestas GET (para datos). Guarda solo GETs. Cache timeout ~10s. Almacena respuestas con cabeceras CORS (cacheableResponse statuses [0,200]).
  - Páginas navegación: NetworkFirst con fallback a index offline (offline.html o '/') para que la SPA offline cargue.
- Asegúrate de que las llamadas con Authorization también se cachean (Workbox maneja query/headers; considera cachear con ignoreVary: ['*'] o por URL).

DEFINITION OF DONE:
- Recargando la app sin red se carga el shell (datos cacheados si ya se consultaron).
- Las GETs a la API que ya se hicieron online se sirven stale offline.
- Las peticiones mutantes NUNCA se cachean.
```

#### T7.3 — Capa de datos offline (IndexedDB + repositorio)

```
TASK: Capa de datos IndexedDB con Dexie.
- Agrega dexie (+ dexie-react-hooks no aplica; usa vueuse/useObservable o manual) a dependencies.
- services/db/db.ts: define la BD 'loansoft' con stores: clientes, prestamos, prestamoDetalles, cuotas, pagos, moras, capital, tiposPrestamo, tiposPago, reportes, cacheMeta, outbox, auditLog.
- services/db/repository.ts: patrón 'stale-while-revalidate':
  - async getCached<T>(store, key, ttlMs): devuelve cache si fresco; si vencido, dispara fetch en segundo plano.
  - async fetchAndCache<T>(store, key, fnFetch): ejecuta fnFetch (network) y actualiza cache; si falla la red y hay cache, devuelve cache con flag stale.
  - getLastSync(store), setLastSync(store).
- Integra en composables/domain: cada useXxx usa el repositorio (ej. usePrestamos.fetch → fetchAndCache('prestamos', 'lista', () => apiGet(...))).
- Maneja que en SSR no exista indexedDB: guarda con guard client-side.

DEFINITION OF DONE:
- Abrir la app sin conexión muestra los últimos datos cacheados por entidad.
- Al volver la conexión, las vistas se refrescan.
- pnpm typecheck, lint OK.
```

#### T7.4 — Estado de conexión y sincronización en UI

```
TASK: UI de conexión y sincronización completa.
- Completar stores/sync.ts e integrar:
  - Banner global (ConnectionBanner) con estados: offline (rojo/ámbar), reconectando, pendientes de sync (contador), syncing (spinner), error de sincronización (con botón 'Reintentar').
  - SyncIndicator en header: tooltip con 'Última sincronización: hh:mm', contador de operaciones pendientes (badge ámbar si >0).
  - Muestra en las vistas offline el aviso de datos 'Última actualización: hh:mm'.
- Toast al cambiar a offline/online.
- Configura listeners en plugins/offline.ts (navigator.onLine + eventos + heartbeat opcional).

DEFINITION OF DONE:
- Transición online↔offline visible en <3s en toda la app.
- El contador de pendientes se actualiza al encolar/despachar.
- pnpm typecheck, lint OK.
```

#### T7.5 — Outbox de pagos offline + Background Sync + reconciliación

```
TASK: Cola de pagos offline (outbox) con sincronización y reconciliación.
- services/db/outbox.ts: tabla outbox con { id (uuid), tipo: 'pago', payload, idempotencyKey, estado: 'pending'|'syncing'|'synced'|'conflict'|'failed', intentos, lastError, createdAt }.
- stores/outbox.ts: acciones encolar(pago), getPendientes, marcarSynced(id), marcarConflict(id, error), marcarFailed(id, error), limpiar.
- Flujo offline:
  - Al registrar un pago con la app sin conexión: VALIDAR localmente el desglose (T5.1) → encolar en outbox → optimizar UI (cuota marcada 'pago pendiente de sincronizar', saldo local ajustado de forma optimista y marcado como provisional) → NO llamar a la API.
  - El badge 'pendiente de sincronizar' se muestra en cuotas/préstamos afectados.
- Sincronización:
  - Al reconectar (online) o por Background Sync (registrar en SW con tag 'loansoft-pagos'): despachar en orden por createdAt.
  - Antes de cada envío: incluir idempotencyKey (REQUIERE_BACKEND B1; mientras no exista, omitir y usar guard natural).
  - Por cada operación:
    - 200 → marcarSynced, actualizar cache local (re-fetch del prestamo detalle), toast.
    - 400 con 'cuota ya pagada o en mora' → RECONCILIAR: re-fetch del prestamo y comparar estado real de la cuota vs local; si ya se pagó en el servidor, marcar como synced (el pago ya existía) y ajustar cache; si es otro 400 de validación → marcar conflict con detalle y avisar al usuario.
    - 401 → refresh y reintentar; si falla, pausar y pedir login.
    - 5xx/network → reintentar con backoff exponencial (30s, 1m, 5m, cap 30m); no exceder X intentos → failed.
  - Conflictos: stores/outbox expone una lista de operaciones en conflicto; crea components/app/SyncIssuesModal.vue para que el usuario las revise (ver error, descartar o reintentar).
- Anti-duplicados garantizado por: idempotencyKey (cuando exista B1) + guard natural de cuota pendiente→pagado. DOCUMENTA este comportamiento en el código.

DEFINITION OF DONE:
- Prueba manual: con red cortada, registrar 2 pagos → aparecen como pendientes; reconectar → se sincronizan en orden y las cuotas quedan pagadas en la API (sin duplicados).
- Un pago rechazado por validación muestra el conflicto con su detalle y requiere acción del usuario.
- pnpm typecheck, lint OK.
```

#### T7.6 — Notificaciones (locales + push)

```
TASK: Notificaciones de vencimiento y permisos.
- composables/useNotifications.ts: detecta soporte, pide permiso (flujo progresivo: explicación primero, luego solicitud), expone grantNotifications(), isGranted.
- Notificaciones LOCALES (sin backend): al abrir la app con datos cacheados, programa notificaciones de cuotas que vencen en 3 y 1 días (con fecha actual). Uso de setInterval + comprobación de permisos; se muestra como notificación del sistema.
- Push (REQUIERE_BACKEND B10): prepara el servicio de suscripción (NotificationManager) para suscribir a un endpoint push cuando exista. Si no hay endpoint, no se invoca.
- UI: página/ajustes de notificaciones (dónde activar/desactivar, estado del permiso) accesible desde el menú de usuario o ajustes.
- Recordatorio también in-app: en el header o dashboard, lista de 'Cuotas por vencer próximamente'.

DEFINITION OF DONE:
- El flujo de permiso funciona sin fricción (explicación → solicitud → estado persistido).
- Con permiso, se disparan notificaciones locales para vencimientos próximos (verificable en el navegador).
- Sin backend de push, la app funciona completa sin error.
- pnpm typecheck, lint OK.
```

---

### FASE 8 — Productividad y diferenciadores

**Objetivo:** paleta de comandos, atajos, cobranza y auditoría local.
**Dependencias:** Fase 6 (no requiere Fase 7 para funcionar, pero los datos offline ayudan).
**Criterios de fase terminada:** mejoras de productividad operativas.

#### T8.1 — Command Palette (Ctrl+K)

```
TASK: Paleta de comandos global.
- components/ui/CommandPalette.vue (o reutiliza UCommandPalette si existe en Nuxt UI v4; revisa la API): invocable con Ctrl+K (o Cmd+K en Mac), buscable, lista de:
  - Navegación: todas las rutas del sidebar con iconos.
  - Acciones: 'Crear préstamo', 'Registrar pago', 'Nuevo cliente', 'Procesar moras', 'Cambiar tema', 'Cerrar sesión'.
  - Búsqueda de clientes/préstamos por nombre/cédula (con datos cacheados o fetch).
- Atajos: registra el listener global en useShortcuts (T8.2). No interfiera con inputs.
- Accesible y cerrable con Escape; foco inicial en input.

DEFINITION OF DONE:
- Ctrl+K abre la paleta desde cualquier página; navegación y acciones funcionan.
- pnpm typecheck, lint OK.
```

#### T8.2 — Atajos de teclado

```
TASK: Atajos de teclado.
- composables/useShortcuts.ts: registro centralizado de combinaciones. Atajos definidos:
  - g + d → dashboard · g + p → préstamos · g + c → clientes · g + r → reportes
  - ctrl+k → paleta · ctrl+n → nuevo préstamo (desde préstamos) · ctrl+s → guardar (en formularios, opcional)
  - Filtros de estado: t→todos, a→activo (en listado de préstamos)
- Respeta prefers-reduced-motion; ignora atajos cuando el foco está en un input (salvo ctrl+k).

DEFINITION OF DONE:
- Atajos documentados en una sección 'Atajos' (menu de usuario o ayuda) y funcionales.
- No hay conflictos con entradas de texto.
```

#### T8.3 — Módulo de cobranza

```
TASK: Módulo de cobranza (agenda y clientes morosos).
- pages/cobranza/index.vue:
  - Carga: GET /prestamos?estado=activo (dataset pequeño) + cuotas de cada detalle (GET /prestamos/{id} por préstamo activo; si son muchos, marca REQUIERE_BACKEND para endpoint agregado). Alternativa eficiente: GET /moras para vencidos.
  - Vistas:
    - 'Por vencer': cuotas pendientes con vencimiento en 7/15/30 días (filtros por rango), con cliente, valor, vencimiento. Resaltado amarillo para <=7 días.
    - 'Morosos': clientes con cuotas vencidas (mora generada), con días de atraso, valor cuota + mora. Enlace directo a 'Registrar pago' del préstamo.
  - Gestión/notas: nota local por préstamo/cliente (persistir en IndexedDB store 'cobranza'): historial de contactos/llamadas (fecha, tipo, resultado). NO es backend: es una herramienta local de seguimiento (documentar).
  - Estados loading/error/vacío.

DEFINITION OF DONE:
- La agenda por vencer y morosos se llenan con datos reales (cuotas/moras).
- Las notas de gestión persisten localmente y sobreviven recarga.
- pnpm typecheck, lint OK.
```

#### T8.4 — Auditoría local y perfil

```
TASK: Auditoría local + perfil de usuario.
- services/db/audit.ts: registra eventos (crear/editar/eliminar cliente, crear préstamo, renovar, marcar perdido, registrar pago, mover capital, login/logout) con { timestamp, accion, entidad, id, detalle, usuario }. Se escribe DESPUÉS de confirmar éxito en la API (o al encolar en outbox).
- components/app/ActivityLog.vue o sección en Configuración: lista de auditoría local con filtros por entidad y export JSON.
- Perfil (menú de usuario): muestra nombre, email, rol; edición de datos de perfil NO está soportada por el backend → marcar 'REQUIERE_BACKEND B5 (cambio de contraseña)' y mostrar solo datos de solo lectura + opción 'Cambiar contraseña (próximamente)' deshabilitada si el backend no existe.
- Si existe POST /auth/password (cuando se implemente), habilita el formulario.

DEFINITION OF DONE:
- Las acciones relevantes quedan registradas en auditoría local y son exportables.
- El perfil muestra datos reales sin inventar endpoints.
- pnpm typecheck, lint OK.
```

#### T8.5 — Usuarios (solo si backend B6 existe)

```
TASK: Gestión de usuarios (admin) — REQUIERE_BACKEND B6.
- Solo implementar si el backend expone CRUD /usuarios. Si no existe, crea pages/usuarios/index.vue con EmptyState 'La gestión de usuarios estará disponible próximamente' + nota de requisito backend. NO inventes el CRUD.
- Si existe: tabla de usuarios (nombre, email, rol, estado), crear/editar/desactivar con validación, gate admin.

DEFINITION OF DONE:
- Sin backend: página informativa sin datos falsos. Con backend: CRUD funcional.
```

---

### FASE 9 — Optimización, testing y producción

**Objetivo:** calidad, pruebas, accesibilidad y despliegue.
**Dependencias:** Fase 8.
**Criterios de fase terminada:** pipeline verde, Lighthouse ≥90, build reproducible.

#### T9.1 — Testing automatizado

```
TASK: Suite de pruebas.
- Configura Vitest + @vue/test-utils + happy-dom/jsdom. Scripts: "test": "vitest run", "test:watch".
- Unit:
  - calculadoraPrestamo (ya creada en T0.3) — amplía casos límite (centavos, cuotas altas).
  - useFormatters (COP, fechas).
  - outbox/merge y reconciliación (mock de fetch): encolar, despachar orden, 400 'ya pagada' → reconciliar, backoff.
  - stores/auth (login/refresh/logout con mocks de services).
  - calculadora de desglose de pago (T5.1): sugerencia y validación de cuadre.
- Componentes: DataTable (orden/filtros/paginación), ClienteForm (validación Zod, error cédula duplicada), PrestamoForm (calculadora en vivo), PagoForm (cuadre). Prioridad: los 4 más críticos.
- E2E con Playwright (agrega @playwright/test): flujos:
  1. Login (admin) → dashboard.
  2. Crear cliente → aparece en listado.
  3. Crear préstamo (calculadora) → detalle con cuotas.
  4. Registrar pago → cuota pagada.
  5. Reportes → exportar PDF (descarga).
  - Configura baseURL, proyecto webServer (npm run dev), auth storageState para tests autenticados.

DEFINITION OF DONE:
- pnpm test en verde (unit + component).
- Playwright con los 5 flujos pasando contra la API real (o con mock de API para CI).
- Cobertura mínima: calculadora y outbox ≥ 90% líneas.
```

#### T9.2 — Accesibilidad y rendimiento

```
TASK: A11y y performance.
- Audita con Lighthouse (desktop + mobile): objetivo ≥90 en performance/accessibility/best-practices/SEO.
- Accesibilidad: verifica contraste de badges y estados, focus-visible, aria en DataTable/menús/modales, navegación por teclado completa, prefers-reduced-motion, lang="es" y titles descriptivos en cada página (useHead/useSeoMeta).
- Rendimiento: lazy-load de ApexCharts (client-only), import de componentes pesados con defineAsyncComponent, chunk splitting, imágenes sin CDN innecesarias, fonts preload, skeleton en vez de spinner pesado.
- Optimiza la carga inicial: evita fetching en paralelo excesivo en dashboard (combina y paraleliza con Promise.all).

DEFINITION OF DONE:
- Lighthouse desktop ≥90 en las 4 categorías (documentar capturas/valores).
- No hay dependencias pesadas en el bundle principal (charts lazy).
- pnpm typecheck, lint OK.
```

#### T9.3 — Build y despliegue

```
TASK: Build reproducible y despliegue.
- Define el target de despliegue (Node server para SSR; alternativas: static no recomendado por PWA/SSR). Documenta en README.
- .env.example documentado con todas las variables (NUXT_PUBLIC_API_BASE, y cualquier de despliegue).
- Scripts de package.json: build, preview, start (si aplica), lint, typecheck, test.
- CI: crea un workflow (GitHub Actions) que corra lint + typecheck + test + build en cada PR.
- Verifica pnpm build y pnpm preview contra la API en producción (CORS del backend debe incluir el dominio — flag al backend).

DEFINITION OF DONE:
- pnpm build + pnpm preview funcionan en un entorno limpio (instalación desde 0 con package-lock/pnpm-lock).
- CI verde en PR.
- README documenta instalación, variables, y despliegue.
```

#### T9.4 — Hardening de seguridad y documentación

```
TASK: Seguridad de producción y documentación.
- nuxt.config security: define Content-Security-Policy (evita eval, restringe fuentes a self + apiBase + fonts locales + conexiones a apiBase), X-Content-Type-Options, Referrer-Policy, Permissions-Policy. Revisa que PWA/workbox no rompan la CSP (worker-src).
- Revisa secretos: grep en el repo por SECRET_KEY/tokens en código cliente. Asegura que runtimeConfig.public solo contiene NUXT_PUBLIC_*.
- Manejo seguro de tokens: documenta la decisión (localStorage hoy; mover refresh a cookie httpOnly cuando B6 exista). Añade validación de que no se logueen tokens.
- Documentación final:
  - README: stack, setup, scripts, variables, estructura, cómo añadir un módulo (guía para IAs), decisión offline-first, listado de REQUIERE_BACKEND.
  - Documenta en código los invariantes financieros (dónde se replican las reglas del backend).

DEFINITION OF DONE:
- Headers de seguridad presentes en la respuesta del servidor de preview.
- No hay secretos en el cliente; la CSP no bloquea el funcionamiento (prueba manual completa).
- README completo con guía de contribución para IAs.
```

---

## 10. Roadmap y prioridades

| Etapa | Contenido | Prioridad |
|---|---|---|
| **Base técnica** | Fase 0–2 | Imprescindible |
| **MVP funcional** | Fase 3 (clientes) + 4 (préstamos) + 5 (pagos/moras) | Imprescindible |
| **App profesional** | Fase 6 (dashboard/reportes) + T8.1–T8.2 (palette/atajos) | Importante |
| **Offline/PWA/Sync** | Fase 7 | Importante |
| **Funcionalidades avanzadas** | T8.3 cobranza · T8.4 auditoría · T8.5 usuarios | Mejora |
| **Optimización/Testing/Producción** | Fase 9 | Imprescindible (go-live) |
| **Diferenciadores** | Cola de pagos offline robusta · command palette · cobranza predictiva | Diferenciador |

**Orden sugerido de implementación por módulo (para ir "de a poco sin errores"):**

1. Fase 0 completa (higiene) → `pnpm build` verde.
2. Fase 1 completa (sesión) → login funcional contra la API real.
3. Fase 2 completa (shell + kit) → app navegable con el esqueleto.
4. Fase 3 (admin) → cliente real.
5. Fase 4 (préstamos) → núcleo financiero.
6. Fase 5 (pagos/moras) → flujo de cobro.
7. Fase 6 (dashboard/reportes) → visibilidad del negocio.
8. Fase 7 (offline/PWA) → valor diferencial.
9. Fase 8 (productividad) → mejoras UX.
10. Fase 9 (calidad/producción) → go-live.

---

## 11. Checklist global de verificación

Antes de marcar el proyecto como "producción":

- [ ] `pnpm typecheck` OK (strict, sin any).
- [ ] `pnpm lint` OK.
- [ ] `pnpm test` OK (unit + component).
- [ ] `pnpm build` OK + `pnpm preview` funciona contra la API real.
- [ ] Login/refresh/logout con sesión persistente (seed `admin@test.com` / `123456`).
- [ ] CRUDs (clientes, tipos, capital) con gate de roles (admin/usuario).
- [ ] Préstamo: crear (calculadora cuadra con backend), detalle, renovar, marcar perdido.
- [ ] Pago: desglose validado; cuota `pendiente→pagado/parcial`; saldo reduce por capital.
- [ ] Moras: procesar y listar.
- [ ] Dashboard KPIs con datos reales (sin inventar).
- [ ] Reportes: filtros mes/año + exportación Excel/PDF válida.
- [ ] PWA instalable; offline lee cache; cola de pagos sincroniza sin duplicados.
- [ ] Lighthouse ≥90 desktop.
- [ ] Sin secretos en cliente; CSP activa.
- [ ] Backend requerimientos B1–B11 documentados y solicitados (no bloqueantes).
- [ ] README con guía de contribución para IAs.

---

*Documento mantenible: cada Fase/Task es independiente para ser entregada a una IA. El PROMPT BASE (§8) debe anteponerse siempre. Si una task requiere algo que el backend no expone, se marca `REQUIERE_BACKEND` en lugar de inventarlo.*
