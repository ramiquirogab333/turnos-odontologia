# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **turnos-odontología**.
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

> **Stack congelado (2026-09-30, ver `knowledge-base/10_preguntas_abiertas.md` §Resoluciones y `AGENTS.md`)**: Backend Python + FastAPI + SQLAlchemy (+ Alembic) + PostgreSQL + Redis + JWT (expiración corta + refresh) + Docker Compose; Frontend React + TypeScript + Vite; E2E Playwright. Toda mención previa a "stack a elegir / sin definir" queda reemplazada por este stack en todos los changes.

> **GAP vs KB (restricción de usuario, fase roadmap)**: la KB modela `Turno.estado ∈ {reservado, confirmado, cancelado, ausente, atendido}` y `Pago` atado a `Presupuesto` (ver `04_modelo_de_datos.md` §Turno/§Pago, `05_reglas_de_negocio.md` §RN-PG). La restricción del usuario exige un flujo **reserva → seña pendiente (estado `en_espera`, SIN bloquear agenda) → pago acreditado (bloquea agenda) → ausente (seña no reembolsada)**, con seña fija configurable (ej. 30% del valor de la consulta). Ningún canónico lo contempla con ese detalle. El change **`C-06`** lo implementa como change propio (fuente: restricción de usuario en fase roadmap) e introduce los estados/transiciones faltantes y el porcentaje configurable. Los changes que lo consumen (C-07, C-08, C-10, C-12) lo citan como dependencia.

> **RE-SCOPE 2026-09-30 (post-fundación, sin ciclo OPSX — solo reescritura de roadmap)**: `C-01` deja de ser `foundation-setup` genérico y pasa a ser un **vertical slice**: `crear-turno-sin-solape` (una sola funcionalidad verificable: `POST /api/turnos` con anti-solape por profesional Y por sillón/box). El scaffolding sobrante se movió a los changes que lo consumen: frontend público + CI → **C-05**; frontend panel → **C-08**; base de jobs/scheduler (Redis workers) → **C-09**. `C-01` NO contiene frontends, CI ni jobs. IDs `C-01…C-13` estables (ninguna referencia se rompe); migraciones renumeradas 001–006. Las 4 decisiones HIGH del 2026-09-30 están sincronizadas en los changes afectados (ver bullets `Resoluciones 2026-09-30` en C-02, C-04, C-08, C-09).

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
C-01 crear-turno-sin-solape
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
  1  │ C-01 crear-turno-sin-solape          │         —                              │         —
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

## FASE 0 — Cimientos (vertical slice + modelos core)

> C-01 es un vertical slice de una sola funcionalidad (restricción de usuario 2026-09-30), no un foundation genérico. C-02 extiende sus 4 tablas con el resto del dominio.

### [C-01] `crear-turno-sin-solape`
- **Estado**: `[x]` archivado 2026-10-01 (`openspec/changes/archive/2026-10-01-crear-turno-sin-solapamientos/`, spec en `openspec/specs/turnos/creacion-sin-solape/spec.md`; E2E 4.1 diferido, ver `## Acta de desvío` en `tasks.md` del change archivado)
- **Scope**: Vertical slice mínimo y completo: crear un turno evitando solapamientos por profesional Y por sillón/box (stack congelado: Python + FastAPI + SQLAlchemy + Alembic + PostgreSQL + Docker Compose; E2E Playwright)
  - `backend/` mínimo estrictamente necesario: app FastAPI con `GET /api/health`, `shared/` con settings (Pydantic), logger, db, exceptions; todo el backend con type hints (R13), sin SQL crudo fuera de migraciones (R14), Pydantic in/out en el borde (R15), I/O async sin bloquear el loop (R16), secretos solo por env vars (R17), servicios solo vía Docker Compose con healthchecks de Postgres (R18)
  - `docker-compose.yml`: `backend` + `postgres` con healthcheck; `.env.example` con `DATABASE_URL` (sin secrets hardcodeados)
  - Modelos SQLAlchemy tipados: `Profesional`, `Sillon`, `Tratamiento` (`duracion_minutos`, precio base), `Turno` (`inicio`/`fin` `DateTime(timezone=True)`, `profesional_id`, `sillon_id`, `tratamiento_id`); dinero con `Numeric`, strings con límite + `CHECK` (R4); índice sobre cada FK (R6)
  - Migración Alembic 001 (reversible): 4 tablas + `EXCLUDE USING gist` anti-solape por (profesional + rango) Y por (sillón/box + rango) como garantía en DB (R5)
  - `POST /api/turnos` — crea un turno (profesional + sillón + tratamiento + inicio; `fin = inicio + duración del tratamiento`); solape por profesional o por sillón → `409` con motivo; validación en backend, nunca solo en cliente
  - Reglas verificables: RN-TU-03 (sin superposición por profesional, extendida a sillón/box día 1 por Resolución 2026-09-30 nº1 — cierra SU-03), RN-TU-04 (`fin` derivado de duración), R5 (`EXCLUDE USING gist`), R8 (sin `en_espera` en este change: el turno creado bloquea el slot; `en_espera` no bloqueante llega en C-06)
  - Done-criteria (test): UN E2E Playwright — dos reservas concurrentes sobre el mismo slot → exactamente un `201` y un `409` (R7); más tests de constraint a nivel DB (doble `INSERT` solapado rechazado por el `EXCLUDE`)
  - EXPLÍCITAMENTE FUERA (movido): scaffolding `frontend-paciente/` → C-05; scaffolding `frontend-panel/` → C-08; CI con jobs paralelos → C-05; base de jobs/scheduler (Redis workers) → C-09
- **Dependencias**: ninguna
- **Governance**: MEDIO — checkpoint: el propose debe mostrar el DDL del `EXCLUDE USING gist` + el test de carrera concurrente antes del apply, porque toca reglas de agenda (RN-TU-03) y constraints DB que todos los changes posteriores heredan
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Profesional / §Sillón / §Tratamiento / §Turno
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Turnos (RN-TU-03, RN-TU-04)
  - `knowledge-base/10_preguntas_abiertas.md` §Resoluciones (multi-odontólogo/multi-sillón día 1, stack congelado)
  - `knowledge-base/08_arquitectura_propuesta.md` §Seguridad (secrets por env vars)

---

### [C-02] `core-models`
- **Estado**: `[ ]` pendiente
- **Scope**: Resto de modelos base + migraciones + seed mínimo, sobre las 4 tablas de C-01 (stack congelado: SQLAlchemy + Alembic + PostgreSQL)
  - Resoluciones 2026-09-30: multi-odontólogo/multi-sillón desde el día 1 — `Turno` siempre asigna `profesional_id` + `sillon_id`; seed con VARIOS profesionales y sillones (no uno solo); Tratamientos como entidad con `duracion_minutos` (seed inicial de tabla tratamiento→duración aportada por la clínica; si falta, seed mínimo documentado como placeholder explícito)
  - Modelos nuevos: `Paciente` (nombre + teléfono requerido, unicidad operativa por teléfono a confirmar), `Disponibilidad` (franjas por día_semana + excepciones/feriados), `Usuario`, `Rol`, `RegistroAuditoria`, `ObraSocial`, `Nomenclador`
  - Estado inicial de `Turno`: el enum vive aquí pero `en_espera` y transiciones de seña se introducen en C-06 (ver GAP en header)
  - Mixins base (`is_active`, `created_at`, `updated_at`, `deleted_at`), `BaseRepository[T]`, `UnitOfWork`; R4/R6/R13/R14 en todo el modelo
  - Migración Alembic 002 (reversible): tablas core restantes + índices `(profesional_id, inicio)`, `(sillon_id, inicio)`, `(paciente_id, inicio)`, `estado`
  - Seed mínimo idempotente: roles (odontólogo, recepción/admin), 1 usuario admin, nomenclador OS AR precargado, varios profesionales/sillones, tabla tratamiento→duración inicial
  - Reglas verificables: RN-TU-05 (tabla tratamiento→duración existe como datos, no código), RN-GL-01 (tabla `RegistroAuditoria` creada), R4, R6
  - Done-criteria (test): constraints de unicidad, defaults de timestamps, seed idempotente (doble corrida sin duplicados)
- **Dependencias**: C-01
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Entidades
  - `knowledge-base/04_modelo_de_datos.md` §Seed data inicial
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados
  - `knowledge-base/09_decisiones_y_supuestos.md` §SU-02
  - `knowledge-base/10_preguntas_abiertas.md` §Resoluciones (multi-odontólogo/sillón, Tratamientos, stack)

---

## FASE 1 — Acceso y catálogo

### [C-03] `auth-panel-rbac`
- **Estado**: `[ ]` pendiente
- **Scope**: Autenticación del panel interno + RBAC + gestión pública sin login (stack congelado: JWT expiración corta + refresh, backend FastAPI)
  - `POST /api/auth/login` — JWT access + refresh, rate limiting por IP+email
  - `POST /api/auth/refresh` — rotación con blacklist del anterior; `POST /api/auth/logout` — blacklist; `GET /api/auth/me`
  - Refresh en cookie HttpOnly (secure, samesite=lax); claims JWT: `sub`, `roles`, `email`, `jti`, `type`, `iat`, `exp`
  - `PermissionContext`: `require_role()` según matriz RBAC (odontólogo: lectura su agenda/sus pacientes; recepción/admin: CRUD total)
  - Reserva pública SIN login (RN-TU-06, DD-01): código/enlace de gestión por turno para cancelar/reprogramar (el paciente no tiene Usuario)
  - Migración Alembic 003 (reversible): tablas auth (credenciales solo panel; paciente sin credenciales)
  - Reglas verificables: RN-TU-06 (reserva pública sin login), RN-GL-01 (login/logout auditables), R17 (JWT corta expiración + refresh, secretos por env)
  - Done-criteria (test): login correcto, token expirado rechazado, refresh rotation con blacklist, matriz RBAC por rol, acceso público a reserva sin token
- **Dependencias**: C-02
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §RBAC — Matriz de permisos
  - `knowledge-base/03_actores_y_roles.md` §Rutas públicas
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Turnos (RN-TU-06)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01
  - `knowledge-base/10_preguntas_abiertas.md` §Resoluciones (stack congelado: JWT)

---

### [C-04] `catalogo-tratamientos-disponibilidad`
- **Estado**: `[ ]` pendiente
- **Scope**: Catálogo administrable que alimenta el cálculo de horarios libres (US-008) — backend admin puro, sin frontend (el panel UI llega en C-08)
  - Resoluciones 2026-09-30: Tratamientos con duración — CRUD admin `Tratamiento` (nombre, `duracion_minutos` > 0 con `CHECK`, precio base `Numeric`); multi-odontólogo/multi-sillón día 1 — CRUD admin `Profesional`, `Sillon`, `Disponibilidad` (franjas + excepciones/feriados)
  - Endpoints admin CRUD: `/api/admin/tratamientos`, `/profesionales`, `/sillones`, `/disponibilidad` (protegidos por C-03, rol recepción/admin; Pydantic in/out, R15)
  - Regla: tabla tratamiento→duración editable sin tocar código (RN-TU-05, DD-03); al cambiar una duración los horarios libres se recalculan (sin migración de datos históricos)
  - Migración Alembic 004 (reversible): constraints de catálogo (`duracion_minutos > 0`)
  - Reglas verificables: RN-TU-04, RN-TU-05 (CA-1 US-008: edición sin tocar código), R4 (`Numeric`/`CHECK`)
  - Done-criteria (test): CRUD denegado por rol sin permiso, duración inválida → 422, recálculo de libres tras cambio de duración
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
- **Scope**: Reserva pública mobile-first + cálculo de horarios libres con anti-solape (US-001), sobre el constraint de C-01 (stack congelado: React + TypeScript + Vite estricto, Playwright)
  - MOVIDO desde el viejo C-01: scaffolding `frontend-paciente/` (Vite + React + TS strict, sin `any`, componentes PascalCase — R1) + CI GitHub Actions con jobs paralelos backend/frontend (primera change con superficie usuario real)
  - `GET /api/public/disponibilidad?profesional_id&tratamiento_id&desde&hasta` — libres = disponibilidad vigente − turnos que BLOQUEAN agenda (nota: `en_espera` NO bloquea desde C-06; hasta entonces bloquean `reservado/confirmado`)
  - `POST /api/public/turnos` — nombre + teléfono (sin cuenta, RN-TU-06/DD-01); `fin = inicio + duración del tratamiento` (RN-TU-04); reutiliza el `EXCLUDE USING gist` de C-01: anti-solape por profesional + sillón (RN-TU-03) y horarios libres vigentes (RN-TU-07); devuelve código/enlace de gestión pública (Flujo 1, pasos 1–4); datos incompletos → 422 sin crear
  - Condición de carrera: dos pacientes sobre el mismo slot → uno gana (`201`), el otro recibe alternativas libres
  - Frontend mobile-first (R3: criterio de aceptación a 360px; R2: `Promise.all` + `Suspense`, sin fetches en cascada): elegir día → horario → profesional → nombre/teléfono
  - Reglas verificables: RN-TU-03, RN-TU-04, RN-TU-06, RN-TU-07, RN-GL-03, R1, R2, R3
  - Done-criteria (test): E2E Playwright del flujo completo a 360px + cálculo de libres + solape profesional/sillón + carrera por el mismo slot con alternativas (R7)
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
  - Máquina de estados del turno: `en_espera` → `reservado` (pago acreditado, BLOQUEA agenda) → `confirmado` / `cancelado` / `ausente` / `atendido`; `en_espera` NO bloquea agenda ni genera evento de calendario; expiración de `en_espera` configurable (job que libera la pre-reserva; la base de jobs/scheduler vive en C-09 — si C-09 no está archivado, el job se define local y C-09 lo consolida)
  - `POST /api/public/turnos/{id}/sena` — crea preferencia/intento Mercado Pago por el % configurado + registra transferencia pendiente con referencia; `GET` estado del intento; webhook `POST /api/webhooks/mercadopago` — verifica firma, idempotencia por `referencia externa`, acredita → `reservado` (bloquea agenda, dispara Flujo 1 paso 5: recordatorio + GCal)
  - Config admin: `SENA_PORCENTAJE` (ej. 30% del valor de la consulta = precio base del tratamiento), medios habilitados (RN-PG-01: MP + transferencia, sin otros en v1), textos de no-reembolso
  - Regla ausente: marcar `ausente` NO reembolsa la seña (queda registrada como no reembolsada en caja, R9); cancelación ≥ 24h: política de la seña definida por admin (default: no reembolsable salvo decisión explícita)
  - Migración Alembic 005 (reversible): `estado en_espera`, tabla `PagoSena` (`turno_id`, medio MP/transferencia, monto `Numeric`, estado pendiente/acreditado/vencido/no_reembolsado, referencia externa única), config `sena_porcentaje`
  - Secrets fuera del código (`MP_ACCESS_TOKEN`); frontend: pantalla "pagá la seña para confirmar" tras elegir día/horario/profesional
  - Reglas verificables: R8 (`en_espera` NO bloquea), R9 (ausente NO reembolsa), RN-PG-01, RN-TU-03 (acreditado vuelve a bloquear con anti-solape)
  - Done-criteria (test): `en_espera` no aparece en libres-bloqueantes; acreditación bloquea; webhook duplicado idempotente; firma inválida rechazada; ausente retiene seña
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
  - Validación backend: anticipación ≥ 24 hs (RN-TU-01, RN-TU-02/DD-02); < 24 hs → rechazo con motivo claro; reprogramación solo a horario libre vigente (RN-TU-07), con anti-solape (hereda `EXCLUDE` de C-01)
  - Si el turno está `en_espera`: cancelar libera la pre-reserva y vence el intento de seña pendiente (sin movimiento de caja); si está `reservado/confirmado`: cancelar libera el slot y la seña queda no reembolsable (regla usuario); reprogramar conserva la seña acreditada sobre el nuevo horario
  - Al cancelar/reprogramar: actualiza Google Calendar y cancela/reprograma recordatorios pendientes (Flujo 2, paso 4)
  - Reglas verificables: RN-TU-01, RN-TU-02, RN-TU-07, R8 (liberación de `en_espera` sin caja), R9 (seña retenida en cancelación de `reservado`)
  - Done-criteria (test): E2E Playwright ventana 24h exacta/borde, reprogramación a slot ocupado → alternativas, seña retenida vs. liberada según estado (R7)
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

> C-09 y C-10 pueden ejecutarse en paralelo entre sí una vez que C-07 está archivado (ambos consumen estados finales + regla 24h). C-09 crea la base de jobs/scheduler (movida del viejo C-01); C-10 la reutiliza.

### [C-08] `agenda-profesional-panel`
- **Estado**: `[ ]` pendiente
- **Scope**: Agenda por profesional día/semana para odontólogo y gestión total para recepción (US-005) — primera superficie de panel (stack congelado: React + TypeScript + Vite)
  - MOVIDO desde el viejo C-01: scaffolding `frontend-panel/` (TS strict R1, mobile-first donde aplique)
  - Resoluciones 2026-09-30: multi-odontólogo/multi-sillón día 1 — `GET /api/panel/agenda?profesional_id&dia|semana` con filtro por profesional/sillón; odontólogo ve solo su agenda, recepción/admin todo (RBAC C-03)
  - La vista distingue `en_espera` (no bloqueante, visual atenuada) de `reservado/confirmado`; sin turnos superpuestos visibles (RN-TU-03)
  - Acciones de recepción: crear turno manual (origen manual, con el mismo anti-solape de C-01), marcar `ausente` (retiene seña, C-06, R9) / `atendido`
  - Frontend panel: vista día y semana, filtro por profesional/sillón
  - Reglas verificables: RN-TU-03 (sin solapes visibles), R8 (`en_espera` atenuada, no cuenta como ocupación), R9 (ausente retiene seña), R1
  - Done-criteria (test): aislamiento por rol, `en_espera` no cuenta como ocupación, marcado de ausente/atendido con seña retenida
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
- **Scope**: Recordatorios y confirmación por WhatsApp MANUAL v1 con scheduler (US-004) (stack congelado: Redis workers vía Docker Compose)
  - MOVIDO desde el viejo C-01: base de jobs/scheduler — Redis vía Docker Compose con healthcheck + workers para jobs pesados (R16, R18); el job de expiración de `en_espera` de C-06 se consolida aquí si se definió local allí
  - Resoluciones 2026-09-30 nº2 — WhatsApp MANUAL en v1: SIN API paga de envío automático; la v1 genera links `wa.me/` con mensajes preformateados (recordatorio con botones confirmar/cancelar como links con código de gestión); se mantiene la abstracción de proveedor (interfaz) para migrar a API después sin reescribir el dominio (cierra RN-WA-03 como manual)
  - Job `jobs/recordatorios`: detecta turnos próximos (`REMINDER_LEAD_TIME`, default 24h) **que bloquean agenda** (`reservado`; `en_espera` NO recibe recordatorio) sin recordar; genera/sirve el link `wa.me` preformateado
  - `POST /api/webhooks/whatsapp` — confirmar → `confirmado`; cancelar → aplica Flujo 2/ventana 24h (C-07); reintentos con backoff, estado `fallido` registrado (Flujo 3)
  - Modelo `Recordatorio` (`turno_id`, canal WhatsApp, estado pendiente/enviado/confirmado/fallido, fecha_envío)
  - Reglas verificables: RN-WA-01 (todo turno bloqueante genera recordatorio), RN-WA-02 (confirmación por botón actualiza estado), RN-WA-03 = manual v1 (links `wa.me`, sin costo por mensaje), R8 (`en_espera` sin recordatorio), R16 (envío pesado en workers Redis)
  - Done-criteria (test): solo turnos bloqueantes reciben recordatorio, link `wa.me` con mensaje preformateado correcto, confirmación cambia estado, fallo → reintento + registro
- **Dependencias**: C-07
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: WhatsApp (RN-WA-01, RN-WA-02, RN-WA-03)
  - `knowledge-base/06_funcionalidades.md` §US-004
  - `knowledge-base/07_flujos_principales.md` §Flujo 3: Recordatorio y confirmación por WhatsApp
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados
  - `knowledge-base/10_preguntas_abiertas.md` §Resoluciones (WhatsApp MANUAL v1)

---

### [C-10] `google-calendar-sync`
- **Estado**: `[ ]` pendiente
- **Scope**: Sincronía bidireccional con Google Calendar (US-006); reutiliza la base Redis/workers de C-09 (si C-09 no está archivado, el job se define local con el mismo patrón y C-09 lo consolida)
  - Solo turnos que BLOQUEAN agenda (`reservado/confirmado`) generan/actualizan `EventoCalendar`; `en_espera` no sincroniza; al cancelar/reprogramar actualiza o borra el evento
  - OAuth por profesional (`GCAL_CLIENT_ID/SECRET`), pull+push con `syncToken`, mapeo `Turno ↔ EventoCalendar`, tabla de eventos (*───* Turno)
  - Conflictos sistema↔GCal: resolución manual con criterio visible (RN-GC-02 pendiente — exponer UI/toast de conflicto, no auto-sobrescribir)
  - Job `jobs/gcal-sync` + secrets fuera del código (R17)
  - Reglas verificables: RN-GC-01 (bidireccional), RN-GC-02 (conflicto → flag manual, nunca auto-sobrescritura), R8 (`en_espera` sin evento)
  - Done-criteria (test): creación/borrado de evento por transición de estado, `en_espera` sin evento, conflicto → flag manual
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
  - Endpoints panel: `/api/panel/pacientes/{id}/ficha`, `/odontograma`, `/presupuestos` (CRUD recepción/admin; lectura odontólogo sus pacientes; Pydantic in/out R15)
  - Presupuesto descuenta cobertura según nomenclador AR precargado (RN-PG-02, seed C-02); sin ARCA nativa en v1 (RN-PG-03)
  - Migración Alembic 006 (reversible): tablas ficha/odontograma/presupuesto
  - Reglas verificables: RN-PG-02 (descuento por cobertura), RN-PG-03 (sin ARCA), R4 (montos `Numeric`)
  - Done-criteria (test): cálculo total con cobertura, permisos por rol, seed nomenclador aplicado
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
  - `GET /api/panel/pacientes` (alta, ficha, historial, ausentes), `GET /api/panel/ocupacion?sillon_id&dia` (solo turnos bloqueantes cuentan; `en_espera` excluida — multi-sillón día 1), `POST /api/panel/turnos/{id}/ausente` (seña no reembolsada — regla usuario, R9)
  - Caja: `GET /api/panel/caja` (señas acreditadas/no reembolsadas + pagos de presupuestos), `POST /api/panel/caja/cierre` (cierres y liquidaciones)
  - Frontend panel recepción/admin (sobre el scaffolding de C-08): dashboard ocupación, ausentismo, recupero, caja
  - Reglas verificables: R8 (ocupación excluye `en_espera`), R9 (ausente retiene seña en caja), RN-GL-01 (cierre auditado)
  - Done-criteria (test): ocupación excluye `en_espera`, ausente retiene seña en caja, cierre cuadra
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
  - Reglas verificables: RN-GL-01 (toda acción de panel deja rastro), RN-GL-02 (exportación masiva tabular)
  - Done-criteria (test): toda acción de panel deja rastro, exportación con datos grandes vía streaming, permisos de lectura
- **Dependencias**: C-12
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Dominio: Excepciones globales (RN-GL-01, RN-GL-02)
  - `knowledge-base/06_funcionalidades.md` §US-011
  - `knowledge-base/06_funcionalidades.md` §US-012
  - `knowledge-base/04_modelo_de_datos.md` §RegistroAuditoria

---

## Riesgos

| Riesgo | Mitigación |
|--------|------------|
| E2E Windows diferido (C-01 4.1: popups `python.exe` cuelgan el host; Playwright prohibido en este entorno) | Cobertura interina verde API+DB (carrera 201+409, SQLSTATE 23P01) en la suite 27 passed; follow-up en C-05/C-08; ver `## Acta de desvío` en `openspec/changes/archive/2026-10-01-crear-turno-sin-solapamientos/tasks.md` |
| Forward-compat `EXCLUDE` → C-06 (`en_espera` no bloqueante) | Resuelta con estrategia A: EXCLUDE parciales `WHERE estado IN ('reservado','confirmado')`; `en_espera` queda fuera del constraint desde el DDL de C-01, sin migración correctiva en C-06 |
| Daemon Docker no disponible en el host | `docker compose config` como verificación sin daemon pesado; Postgres levantado solo con `docker compose up -d postgres` (foreground, un intento); si falla, abortar y reportar en vez de reintentar en background |
| Alertas Snyk: `playwright-cli` / `gws-calendar-agenda` | Skills solo como harness de test/agenda; sin pins productivos afectados; revisar alertas antes de C-05 (Playwright) y C-10 (GCal) |
| Cifras de mercado autodeclaradas (ej. DentalSoft "+300 clínicas / −82% ausencias" sin auditoría) | No usar como criterio de aceptación; métricas de éxito propias en `01_vision_y_objetivos.md`; pendiente de confirmación (pregunta Media en `10_preguntas_abiertas.md`) |
| Reglas que pueden cambiar (ventana 24h idéntica p/ reprogramación, RN-GC-02, unicidad operativa por teléfono) | Trazadas como preguntas abiertas/inconsistencias en `10_preguntas_abiertas.md` (IN-02, RN-GC-02); cambios solo vía OPSX con specs actualizados |
| Disponibilidad desactualizada (franjas/excepciones/feriados) | Horarios libres siempre calculados desde disponibilidad vigente − turnos bloqueantes (RN-TU-07); sin caché de libres del lado cliente |
