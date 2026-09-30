# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **turnos-odontología**.
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

> **GAP vs KB (restricción de usuario, fase roadmap)**: la KB modela `Turno.estado ∈ {reservado, confirmado, cancelado, ausente, atendido}` y `Pago` atado a `Presupuesto` (ver `04_modelo_de_datos.md` §Turno/§Pago, `05_reglas_de_negocio.md` §RN-PG). La restricción del usuario exige un flujo **reserva → seña pendiente (estado `en_espera`, SIN bloquear agenda) → pago acreditado (bloquea agenda) → ausente (seña no reembolsada)**, con seña fija configurable (ej. 30% del valor de la consulta). Ningún canónico lo contempla con ese detalle. El change **`C-06`** lo implementa como change propio (fuente: restricción de usuario en fase roadmap) e introduce los estados/transiciones faltantes y el porcentaje configurable. Los changes que lo consumen (C-07, C-08, C-10, C-12) lo citan como dependencia.

---

## Cómo usar este documento

1. Identificar el change a implementar (verificar que sus dependencias están en `openspec/changes/archive/`).
2. Leer los docs de la knowledge-base indicados en "Leer antes".
3. Ejecutar `/opsx:propose <nombre-del-change>`.
4. Al terminar el change, archivarlo con `/opsx:archive <nombre-del-change>`.
5. Marcar el checkbox `[x]` en este archivo.

---

## Árbol de dependencias

```
C-01 foundation-setup
  └── C-02 core-models
        └── C-03 auth-panel-rbac                ← desbloquea TODO lo demás
              │
              ├── C-04 catalogo-tratamientos-disponibilidad
              │     └── C-05 reserva-publica-horarios
              │           ├── C-06 sena-pagos-turno      ← GAP usuario: en_espera sin bloqueo
              │           │     └── C-07 cancelacion-reprogramacion-24h
              │           │           ├── C-08 agenda-profesional-panel
              │           │           │     └── C-12 panel-admin-caja-ausentismo
              │           │           │           └── C-13 auditoria-exportacion
              │           │           ├── C-09 whatsapp-recordatorios-confirmacion
              │           │           └── C-10 google-calendar-sync
              │           └── C-11 ficha-odontograma-presupuestos-os
              │                 └── C-12 panel-admin-caja-ausentismo
```

### Paralelismo por fase

> Cada "gate" es un punto de sincronización. Los changes dentro de un grupo pueden ejecutarse en paralelo.

```
GATE 0: ninguna
  → C-01 (solo)

GATE 1: C-01 ✓
  → C-02 (solo)

GATE 2: C-02 ✓
  → C-03 (solo)

GATE 3: C-03 ✓
  → C-04 catalogo-tratamientos-disponibilidad (solo)

GATE 4: C-04 ✓
  → C-05 reserva-publica-horarios (solo)

GATE 5: C-05 ✓                          ← PRIMER FORK (2 paralelos)
  → C-06 sena-pagos-turno               [Agente A]
  → C-11 ficha-odontograma-presupuestos-os [Agente C]

GATE 6: C-06 ✓                          ← SEGUNDO FORK (3 paralelos)
  → C-07 cancelacion-reprogramacion-24h [Agente A]
  → C-09 whatsapp-recordatorios-confirmacion [Agente B — si C-07 ✓ para regla 24h en botones]
  → C-10 google-calendar-sync           [Agente B — si C-07 ✓]

GATE 7: C-07 ✓
  → C-08 agenda-profesional-panel       [Agente A]

GATE 8: C-08 + C-11 ✓
  → C-12 panel-admin-caja-ausentismo    [Agente A]

GATE 9: C-12 ✓
  → C-13 auditoria-exportacion          [Agente A]
```

### Camino crítico (9 changes — mínimo irreducible)

```
C-01 → C-02 → C-03 → C-04 → C-05 → C-06 → C-07 → C-08 → C-12
```

### Plan óptimo con 3 agentes

```
Paso │ Agente A (Backend Core)              │ Agente B (Backend Aux)                 │ Agente C (Frontend)
─────┼──────────────────────────────────────┼────────────────────────────────────────┼─────────────────────────
  1  │ C-01 foundation-setup                │         —                              │         —
  2  │ C-02 core-models                     │         —                              │         —
  3  │ C-03 auth-panel-rbac                 │         —                              │         —
  4  │ C-04 catalogo-tratamientos-disponib. │         —                              │         —
  5  │ C-05 reserva-publica-horarios        │         —                              │         —
  6  │ C-06 sena-pagos-turno                │         —                              │ C-11 ficha-odontograma-presupuestos-os
  7  │ C-07 cancelacion-reprogramacion-24h  │ C-10 google-calendar-sync              │         —
  8  │ C-08 agenda-profesional-panel        │ C-09 whatsapp-recordatorios-confirm.   │         —
  9  │ C-12 panel-admin-caja-ausentismo     │         —                              │         —
 10  │ C-13 auditoria-exportacion           │         —                              │         —
```

---

## FASE 0 — Cimientos

### [C-01] `foundation-setup`
- **Estado**: `[ ]` pendiente
- **Scope**: Scaffolding completo + infraestructura base (stack a elegir; nada de la KB fija tecnología)
  - Estructura de directorios según `08_arquitectura_propuesta.md` §Estructura: `frontend-paciente/`, `frontend-panel/`, `backend/{agenda,pacientes,clinica,pagos,notificaciones,integraciones,plataforma}/`, `jobs/`
  - `backend/`: app mínima con health check (`GET /api/health`), runner de migraciones inicializado, `shared/` con settings, logger, db, exceptions
  - `frontend-paciente/` y `frontend-panel/`: scaffolding mobile-first (la reserva pública es mobile-first, RN-GL-03)
  - `.env.example` con `DATABASE_URL`, `WHATSAPP_API_TOKEN`, `WHATSAPP_SENDER`, `GCAL_CLIENT_ID/SECRET`, `MP_ACCESS_TOKEN`, `REMINDER_LEAD_TIME`, `CANCEL_WINDOW_HOURS=24` (sin secrets hardcodeados)
  - Scheduler/jobs base (para recordatorios C-09 y sync C-10) + CI con jobs paralelos backend/frontend
  - Tests: health check, carga de settings, smoke de migraciones
- **Dependencias**: ninguna
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/01_vision_y_objetivos.md` §Alcance v1
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios
  - `knowledge-base/10_preguntas_abiertas.md` (stack sin definir — no inventar elección)

---

### [C-02] `core-models`
- **Estado**: `[ ]` pendiente
- **Scope**: Modelos base + migraciones iniciales + seed mínimo
  - Modelos: `Paciente` (nombre + teléfono requerido, unicidad operativa por teléfono a confirmar), `Profesional`, `Sillon`, `Tratamiento` (duración_minutos configurable, precio base), `Disponibilidad` (franjas por día_semana + excepciones/feriados), `Turno` (inicio, fin derivado, estado, origen, código de gestión pública), `Usuario`, `Rol`, `RegistroAuditoria`, `ObraSocial`, `Nomenclador`
  - Estado inicial de `Turno`: el enum vive aquí pero `en_espera` y transiciones de seña se introducen en C-06 (ver GAP en header)
  - Mixins base (`is_active`, `created_at`, `updated_at`, `deleted_at`), `BaseRepository[T]`, `UnitOfWork`
  - Migración 001: tablas core + índices `(profesional_id, inicio)`, `(sillon_id, inicio)`, `(paciente_id, inicio)`, `estado`
  - Seed mínimo: roles (odontólogo, recepción/admin), 1 usuario admin, nomenclador OS AR precargado, tabla tratamiento→duración inicial (pendiente — ver preguntas abiertas)
  - Tests: constraints de unicidad, defaults de timestamps, seed idempotente
- **Dependencias**: C-01
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Entidades
  - `knowledge-base/04_modelo_de_datos.md` §Seed data inicial
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados
  - `knowledge-base/09_decisiones_y_supuestos.md` §SU-02
  - `knowledge-base/10_preguntas_abiertas.md` (uno o varios odontólogos/sillones; tabla tratamiento→duración)

---

## FASE 1 — Acceso y catálogo

### [C-03] `auth-panel-rbac`
- **Estado**: `[ ]` pendiente
- **Scope**: Autenticación del panel interno + RBAC + gestión pública sin login
  - `POST /api/auth/login` — JWT access + refresh, rate limiting por IP+email
  - `POST /api/auth/refresh` — rotación con blacklist del anterior; `POST /api/auth/logout` — blacklist; `GET /api/auth/me`
  - Refresh en cookie HttpOnly (secure, samesite=lax); claims JWT: `sub`, `roles`, `email`, `jti`, `type`, `iat`, `exp`
  - `PermissionContext`: `require_role()` según matriz RBAC (odontólogo: lectura su agenda/sus pacientes; recepción/admin: CRUD total)
  - Reserva pública SIN login (RN-TU-06, DD-01): código/enlace de gestión por turno para cancelar/reprogramar (el paciente no tiene Usuario)
  - Migración 002: tablas auth (credenciales solo panel; paciente sin credenciales)
  - Tests: login, token expirado, refresh rotation, matriz RBAC, acceso público sin token a reserva
- **Dependencias**: C-02
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §RBAC — Matriz de permisos
  - `knowledge-base/03_actores_y_roles.md` §Rutas públicas
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Turnos (RN-TU-06)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01
  - `knowledge-base/10_preguntas_abiertas.md` (login paciente vs. nombre+teléfono)

---

### [C-04] `catalogo-tratamientos-disponibilidad`
- **Estado**: `[ ]` pendiente
- **Scope**: Catálogo administrable que alimenta el cálculo de horarios libres (US-008)
  - Modelos ya creados en C-02; aquí: CRUD admin `Tratamiento` (nombre, duración_minutos > 0, precio base), `Profesional`, `Sillon`, `Disponibilidad` (franjas + excepciones/feriados)
  - Endpoints admin CRUD: `/api/admin/tratamientos`, `/profesionales`, `/sillones`, `/disponibilidad` (protegidos por C-03, rol recepción/admin)
  - Regla: tabla tratamiento→duración editable sin tocar código (RN-TU-05, DD-03); al cambiar una duración los horarios libres se recalculan (sin migración de datos históricos)
  - Migración 003: ajustes de catálogo si los hubiera (constraints duración > 0)
  - Tests: CRUD por rol, duración inválida rechazada, recálculo de libres tras cambio
- **Dependencias**: C-03
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Tratamiento
  - `knowledge-base/04_modelo_de_datos.md` §Disponibilidad
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Turnos (RN-TU-04, RN-TU-05)
  - `knowledge-base/06_funcionalidades.md` §US-008
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-03

---

## FASE 2 — Reserva y seña (núcleo MVP)

> C-06 es el change de la restricción de usuario (GAP contra la KB). C-07 depende de C-06 porque cancelar/reprogramar debe contemplar `en_espera` y la seña no reembolsable.

### [C-05] `reserva-publica-horarios`
- **Estado**: `[ ]` pendiente
- **Scope**: Reserva pública mobile-first + cálculo de horarios libres con anti-solape (US-001)
  - `GET /api/public/disponibilidad?profesional_id&tratamiento_id&desde&hasta` — libres = disponibilidad vigente − turnos que BLOQUEAN agenda (nota: `en_espera` NO bloquea desde C-06; hasta entonces bloquean `reservado/confirmado`)
  - `POST /api/public/turnos` — nombre + teléfono (sin cuenta, RN-TU-06/DD-01); `fin = inicio + duración del tratamiento` (RN-TU-04); validación backend de anti-solape por profesional (+ sillón si aplica, SU-03) y de horarios libres vigentes (RN-TU-03, RN-TU-07)
  - Crea el turno y devuelve código/enlace de gestión pública (Flujo 1, pasos 1–4); datos incompletos → 422 sin crear
  - Condición de carrera: dos pacientes sobre el mismo slot → uno gana, el otro recibe alternativas libres
  - Frontend mobile-first: elegir día → horario → profesional (si hay varios) → nombre/teléfono
  - Tests: cálculo de libres, solape profesional/sillón, carrera por el mismo slot, validación de input solo-backend
- **Dependencias**: C-04
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Turnos (RN-TU-03, RN-TU-04, RN-TU-06, RN-TU-07)
  - `knowledge-base/06_funcionalidades.md` §US-001
  - `knowledge-base/07_flujos_principales.md` §Flujo 1: Reserva online de turno
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados
  - `knowledge-base/09_decisiones_y_supuestos.md` §SU-03

---

### [C-06] `sena-pagos-turno`
- **Estado**: `[ ]` pendiente
- **Scope**: Flujo de seña fija configurable — GAP contra la KB, fuente: restricción de usuario en fase roadmap (US-010 extendida al turno)
  - Máquina de estados del turno: `en_espera` → `reservado` (pago acreditado, BLOQUEA agenda) → `confirmado` / `cancelado` / `ausente` / `atendido`; `en_espera` NO bloquea agenda ni genera evento de calendario; expiración de `en_espera` configurable (job que libera la pre-reserva)
  - `POST /api/public/turnos/{id}/sena` — crea preferencia/intento Mercado Pago por el % configurado + registra transferencia pendiente con referencia; `GET` estado del intento; webhook `POST /api/webhooks/mercadopago` — verifica firma, idempotencia por `referencia externa`, acredita → `reservado` (bloquea agenda, dispara Flujo 1 paso 5: recordatorio + GCal)
  - Config admin: `SENA_PORCENTAJE` (ej. 30% del valor de la consulta = precio base del tratamiento), medios habilitados (RN-PG-01: MP + transferencia, sin otros en v1), textos de no-reembolso
  - Regla ausente: marcar `ausente` NO reembolsa la seña (queda registrada como no reembolsada en caja); cancelación ≥ 24h: política de la seña definida por admin (default: no reembolsable salvo decisión explícita)
  - Migración 004: `estado en_espera`, tabla `PagoSena` (`turno_id`, medio MP/transferencia, monto, estado pendiente/acreditado/vencido/no_reembolsado, referencia externa única), config `sena_porcentaje`
  - Secrets fuera del código (`MP_ACCESS_TOKEN`); frontend: pantalla "pagá la seña para confirmar" tras elegir día/horario/profesional
  - Tests: `en_espera` no aparece en libres-bloqueantes; acreditación bloquea; webhook duplicado idempotente; firma inválida rechazada; ausente retiene seña
- **Dependencias**: C-04, C-05
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Turno
  - `knowledge-base/04_modelo_de_datos.md` §Pago
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Pagos y cobertura (RN-PG-01)
  - `knowledge-base/06_funcionalidades.md` §US-010
  - `knowledge-base/07_flujos_principales.md` §Flujo 1: Reserva online de turno

---

### [C-07] `cancelacion-reprogramacion-24h`
- **Estado**: `[ ]` pendiente
- **Scope**: Cancelación y reprogramación por el paciente con ventana de 24 hs + interacción con seña (US-002, US-003)
  - `POST /api/public/turnos/{codigo}/cancelar` y `POST /api/public/turnos/{codigo}/reprogramar` (código de gestión pública, sin login)
  - Validación backend: anticipación ≥ 24 hs (RN-TU-01, RN-TU-02/DD-02); < 24 hs → rechazo con motivo claro; reprogramación solo a horario libre vigente (RN-TU-07), con anti-solape
  - Si el turno está `en_espera`: cancelar libera la pre-reserva y vence el intento de seña pendiente (sin movimiento de caja); si está `reservado/confirmado`: cancelar libera el slot y la seña queda no reembolsable (regla usuario); reprogramar conserva la seña acreditada sobre el nuevo horario
  - Al cancelar/reprogramar: actualiza Google Calendar y cancela/reprograma recordatorios pendientes (Flujo 2, paso 4)
  - Tests: ventana 24h exacta/borde, reprogramación a slot ocupado → alternativas, seña retenida vs. liberada según estado
- **Dependencias**: C-05, C-06
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Turnos (RN-TU-01, RN-TU-02, RN-TU-07)
  - `knowledge-base/06_funcionalidades.md` §US-002
  - `knowledge-base/06_funcionalidades.md` §US-003
  - `knowledge-base/07_flujos_principales.md` §Flujo 2: Cancelación / reprogramación por el paciente
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-02

---

## FASE 3 — Agenda y notificaciones

> C-09 y C-10 pueden ejecutarse en paralelo entre sí una vez que C-07 está archivado (ambos consumen estados finales + regla 24h).

### [C-08] `agenda-profesional-panel`
- **Estado**: `[ ]` pendiente
- **Scope**: Agenda por profesional día/semana para odontólogo y gestión total para recepción (US-005)
  - `GET /api/panel/agenda?profesional_id&dia|semana` — turnos con paciente, tratamiento, estado; odontólogo ve solo su agenda, recepción/admin todo (RBAC C-03)
  - La vista distingue `en_espera` (no bloqueante, visual atenuada) de `reservado/confirmado`; sin turnos superpuestos visibles (RN-TU-03)
  - Acciones de recepción: crear turno manual (origen manual), marcar `ausente` (retiene seña, C-06) / `atendido`
  - Frontend panel: vista día y semana, filtro por profesional/sillón
  - Tests: aislamiento por rol, `en_espera` no cuenta como ocupación, marcado de ausente/atendido
- **Dependencias**: C-07
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §RBAC — Matriz de permisos
  - `knowledge-base/06_funcionalidades.md` §US-005
  - `knowledge-base/07_flujos_principales.md` §Flujo 4: Consulta de agenda por el profesional
  - `knowledge-base/04_modelo_de_datos.md` §Turno

---

### [C-09] `whatsapp-recordatorios-confirmacion`
- **Estado**: `[ ]` pendiente
- **Scope**: Recordatorios y confirmación por WhatsApp con scheduler (US-004)
  - Job `jobs/recordatorios`: detecta turnos próximos (`REMINDER_LEAD_TIME`, default 24h) **que bloquean agenda** (`reservado`; `en_espera` NO recibe recordatorio) sin recordar; envía con botones confirmar/cancelar
  - `POST /api/webhooks/whatsapp` — confirmar → `confirmado`; cancelar → aplica Flujo 2/ventana 24h (C-07); reintentos con backoff, estado `fallido` registrado (Flujo 3)
  - Modelo `Recordatorio` (`turno_id`, canal WhatsApp, estado pendiente/enviado/confirmado/fallido, fecha_envío)
  - Abstracción de proveedor (manual vs. API con costo por mensaje — RN-WA-03 pendiente; diseñar interfaz para no atarse a Twilio/Meta)
  - Tests: solo turnos bloqueantes reciben recordatorio, confirmación cambia estado, fallo → reintento + registro
- **Dependencias**: C-07
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: WhatsApp (RN-WA-01, RN-WA-02, RN-WA-03)
  - `knowledge-base/06_funcionalidades.md` §US-004
  - `knowledge-base/07_flujos_principales.md` §Flujo 3: Recordatorio y confirmación por WhatsApp
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados
  - `knowledge-base/10_preguntas_abiertas.md` (WhatsApp manual vs. API)

---

### [C-10] `google-calendar-sync`
- **Estado**: `[ ]` pendiente
- **Scope**: Sincronía bidireccional con Google Calendar (US-006)
  - Solo turnos que BLOQUEAN agenda (`reservado/confirmado`) generan/actualizan `EventoCalendar`; `en_espera` no sincroniza; al cancelar/reprogramar actualiza o borra el evento
  - OAuth por profesional (`GCAL_CLIENT_ID/SECRET`), pull+push con `syncToken`, mapeo `Turno ↔ EventoCalendar`, tabla de eventos (*───* Turno)
  - Conflictos sistema↔GCal: resolución manual con criterio visible (RN-GC-02 pendiente — exponer UI/toast de conflicto, no auto-sobrescribir)
  - Job `jobs/gcal-sync` + secrets fuera del código
  - Tests: creación/borrado de evento por transición de estado, `en_espera` sin evento, conflicto → flag manual
- **Dependencias**: C-07
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Calendario (RN-GC-01, RN-GC-02)
  - `knowledge-base/06_funcionalidades.md` §US-006
  - `knowledge-base/04_modelo_de_datos.md` §ERD (textual)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-05
  - `knowledge-base/10_preguntas_abiertas.md` (resolución de conflictos GCal)

---

## FASE 4 — Clínica y administración

### [C-11] `ficha-odontograma-presupuestos-os`
- **Estado**: `[ ]` pendiente
- **Scope**: Ficha clínica mínima + odontograma FDI básico + presupuestos con cobertura OS (US-009)
  - Modelos: `Ficha` (antecedentes, historia de turnos), `Odontograma` FDI básico por paciente, `Presupuesto` (líneas tratamiento + cobertura OS, total, estado) — `Pago` de presupuestos aquí o reutilizando medio MP/transferencia de C-06 (RN-PG-01)
  - Endpoints panel: `/api/panel/pacientes/{id}/ficha`, `/odontograma`, `/presupuestos` (CRUD recepción/admin; lectura odontólogo sus pacientes)
  - Presupuesto descuenta cobertura según nomenclador AR precargado (RN-PG-02, seed C-02); sin ARCA nativa en v1 (RN-PG-03)
  - Migración 005: tablas ficha/odontograma/presupuesto
  - Tests: cálculo total con cobertura, permisos por rol, seed nomenclador aplicado
- **Dependencias**: C-04
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Ficha
  - `knowledge-base/04_modelo_de_datos.md` §Presupuesto
  - `knowledge-base/04_modelo_de_datos.md` §ObraSocial / Nomenclador
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Pagos y cobertura (RN-PG-02, RN-PG-03)
  - `knowledge-base/06_funcionalidades.md` §US-009

---

### [C-12] `panel-admin-caja-ausentismo`
- **Estado**: `[ ]` pendiente
- **Scope**: Panel de operación diaria: pacientes, ausentismo, ocupación por sillón, caja y liquidaciones (US-007)
  - `GET /api/panel/pacientes` (alta, ficha, historial, ausentes), `GET /api/panel/ocupacion?sillon_id&dia` (solo turnos bloqueantes cuentan; `en_espera` excluida), `POST /api/panel/turnos/{id}/ausente` (seña no reembolsada — regla usuario)
  - Caja: `GET /api/panel/caja` (señas acreditadas/no reembolsadas + pagos de presupuestos), `POST /api/panel/caja/cierre` (cierres y liquidaciones)
  - Frontend panel recepción/admin: dashboard ocupación, ausentismo, recupero, caja
  - Tests: ocupación excluye `en_espera`, ausente retiene seña en caja, cierre cuadra
- **Dependencias**: C-08, C-11
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-007
  - `knowledge-base/07_flujos_principales.md` §Flujo 5: Gestión admin
  - `knowledge-base/04_modelo_de_datos.md` §Sillón
  - `knowledge-base/01_vision_y_objetivos.md` §Métricas de éxito

---

### [C-13] `auditoria-exportacion`
- **Estado**: `[ ]` pendiente
- **Scope**: Auditoría básica transversal + exportación masiva (US-011, US-012)
  - `RegistroAuditoria` (usuario, acción, entidad_afectada, fecha_hora) vía middleware/interceptor en todos los endpoints de panel (RN-GL-01) — incluye transiciones de seña y marcado de ausente
  - `GET /api/panel/auditoria` (lectura/generación recepción/admin) con filtros por entidad/usuario/fecha
  - `GET /api/panel/export?entidad=turnos|pacientes&formato=csv` — exportación tabular descargable (RN-GL-02), streaming para datasets grandes
  - Tests: toda acción de panel deja rastro, exportación con datos grandes, permisos de lectura
- **Dependencias**: C-12
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Excepciones globales (RN-GL-01, RN-GL-02)
  - `knowledge-base/06_funcionalidades.md` §US-011
  - `knowledge-base/06_funcionalidades.md` §US-012
  - `knowledge-base/04_modelo_de_datos.md` §RegistroAuditoria
