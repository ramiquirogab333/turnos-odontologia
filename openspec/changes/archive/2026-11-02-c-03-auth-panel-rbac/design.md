# Design: c-03-auth-panel-rbac

## Context
C-02 creó los modelos base `Usuario`, `Rol`, `UsuarioRol` y `RegistroAuditoria`, pero no hay autenticación ni autorización para el panel interno. C-03 añade login JWT con rotación de refresh, blacklist de jti, `PermissionContext` con `require_role()` y el middleware de protección de endpoints, respetando las reglas duras **R13** (type hints 100%), **R14** (SQLAlchemy ORM + Alembic reversible, sin SQL crudo fuera de migraciones), **R15** (Pydantic in/out en el borde), **R16** (I/O async, no bloquear el loop) y **R17** (secretos por env vars, JWT corta expiración + refresh).

---

## Goals / Non-Goals

**Goals:**
- Autenticación JWT del panel interno: `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`, `GET /api/auth/me`.
- Access token con expiración corta; refresh token en cookie HttpOnly (secure, samesite=lax).
- Claims JWT: `sub`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.
- Blacklist de jti para rotación de refresh y logout.
- `PermissionContext.require_role()` según matriz RBAC de `03_actores_y_roles.md` (odontólogo: lectura su agenda/sus pacientes; recepción/admin: CRUD total).
- Migración Alembic 003 reversible con tablas auth (refresh tokens, blacklist de jti).
- Reserva pública sin login (`POST /api/public/turnos` sin token, nombre + teléfono suficiente — RN-TU-06, DD-01).

**Non-Goals:**
- Endpoints de reserva pública (`POST /api/public/turnos`, cálculo de horarios libres) — pertenecen a **C-05**.
- WhatsApp (recordatorios, confirmación) — pertenecen a **C-09**.
- Google Calendar sync — pertenecen a **C-10**.

---

## Decisions

### Decision 1: JWT con expiración corta + refresh en cookie HttpOnly
* **Decisión:** Access token JWT de vida corta (configurable por env var) para autenticar cada petición de panel; refresh token de mayor vida almacenado únicamente en cookie HttpOnly (secure, samesite=lax), nunca expuesto al JS del cliente.
* **Claims JWT:** `sub` (id de usuario), `roles` (lista de roles del usuario), `email`, `jti` (identificador único del token), `type` (`access` / `refresh`), `iat`, `exp`.
* **Alternativas descartadas:** JWT sin expiración (violaría R17), refresh token en body/localStorage (menos seguro contra XSS), sesión server-side (incompatibiliza con escalado y stateless API).

### Decision 2: Blacklist de jti para rotación de refresh y logout
* **Decisión:** Tabla de blacklist de jti (identificadores de token revocados). En refresh rotation, el jti del refresh token usado se añade a la blacklist antes de emitir el nuevo par. En logout, el jti del access token actual se blacklistea. Cada validación de token comprueba que su jti no esté en la blacklist.
* **Alternativas descartadas:** No revocar tokens (único remedio es esperar expiración, inaceptable ante robo), blacklist en Redis sin persistencia (perdería revocaciones al reiniciar; se elige tabla DB para simplicidad y trazabilidad con R14).

### Decision 3: PermissionContext con require_role() según matriz RBAC
* **Decisión:** Clase `PermissionContext` que expone `require_role(rol_requerido)` y `tiene_rol(rol)`. La matriz RBAC de `03_actores_y_roles.md` define: `odontólogo` = lectura de su agenda y sus pacientes; `recepcion` / `admin` = CRUD total. Un odontólogo que intente escribir en pacientes ajenos recibe denegación.
* **Alternativas descartadas:** RBAC basado en scopes de endpoint hardcodeados (menos flexible que `require_role` dinámico), ACL por usuario individual (sobreingeniería para v1).

### Decision 4: Reserva pública sin login (DD-01, RN-TU-06)
* **Decisión:** `POST /api/public/turnos` no requiere autenticación ni token. El paciente no tiene `Usuario`; la reserva se identifica por nombre + teléfono y se gestiona posteriormente mediante código/enlace de gestión por turno para cancelar/reprogramar. La interfaz pública se documenta aquí pero su implementación pertenece a C-05.
* **Alternativas descartadas:** Login obligatorio de paciente (violaría DD-01 y RN-TU-06), cuenta de paciente previa a la reserva (fricción de conversión, descartada por el PO).

### Decision 5: Migración Alembic 003 reversible con tablas auth
* **Decisión:** Migración `003_auth.py` que crea las tablas de auth (refresh tokens, blacklist de jti) de forma reversible (`upgrade` crea, `downgrade` elimina). Credenciales solo para el panel; el paciente no tiene credenciales. Índices manuales en cada FK (R6), tipos tz-aware (R4).
* **Alternativas descartadas:** SQL crudo fuera de migraciones (violaría R14), no versionar las tablas auth (imposible reproducir entornos).

**Decisiones alineadas con:** R13 (firmas tipadas), R14 (ORM + Alembic reversible), R15 (Pydantic esquemas de entrada/salida), R16 (I/O async), R17 (secretos por env vars, JWT corta expiración + refresh).

---

## Risks / Trade-offs

- **[Riesgo: Rotación de refresh bajo concurrencia]** → *Mitigación:* validación atómica de jti en blacklist dentro de transacción; dos refresh concurrentes con el mismo token viejo → uno rotado, el otro rechazado (su jti ya blacklisteado).
- **[Riesgo: Blacklist crece sin límite]** → *Mitigación:* limpieza periódica de jti expirados (job futuro, no en C-03); entradas con `exp` pasado son ignoradas en validación.
- **[Riesgo: Odontólogo accede a pacientes ajenos]** → *Mitigación:* `require_role('odontologo')` se combina en endpoints de pacientes con filtro por `profesional_id` vinculado al usuario; el middleware solo valida el rol, el dominio valida la pertenencia.
