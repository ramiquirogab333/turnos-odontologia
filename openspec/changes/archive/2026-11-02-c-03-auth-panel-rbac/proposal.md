# Proposal: c-03-auth-panel-rbac

## Why
C-02 `core-models` estableció los modelos base del dominio (`Usuario`, `Rol`, `UsuarioRol`, `RegistroAuditoria` y demás) pero el panel interno no tiene mecanismo de autenticación ni autorización. Sin login JWT, rotación de refresh tokens, blacklist de jti y middleware RBAC, ningún cambio posterior (agenda por profesional, caja, ausentismo) puede proteger sus endpoints según la matriz de permisos. C-03 cierra esta brecha para que el panel sea operable y trazable.

## What Changes
- **Endpoints de autenticación del panel:**
  - `POST /api/auth/login` — devuelve par de tokens JWT (access + refresh), rate limiting por IP+email.
  - `POST /api/auth/refresh` — rotación con blacklist del jti del refresh token anterior.
  - `POST /api/auth/logout` — blacklist del jti actual (revoca sesión).
  - `GET /api/auth/me` — devuelve el usuario autenticado con sus roles asignados.
- **Tokens y seguridad:**
  - Access token con expiración corta; refresh token en cookie HttpOnly (secure, samesite=lax).
  - Claims JWT: `sub`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.
  - Blacklist de jti para rotación de refresh y logout (tablas auth adicionales).
  - Secrets (JWT secret, expiraciones) solo vía variables de entorno (R17).
- **Autorización RBAC:**
  - `PermissionContext` con `require_role()` según la matriz de `03_actores_y_roles.md`.
  - Odontólogo: lectura de su agenda y sus pacientes.
  - Recepción/admin: CRUD total sobre turnos, pacientes, disponibilidad, caja.
  - Dependencia de FastAPI que inyecta `PermissionContext` en endpoints de panel.
- **Reserva pública sin login:**
  - `POST /api/public/turnos` no requiere token (nombre + teléfono suficiente, RN-TU-06, DD-01).
  - El paciente no tiene `Usuario`; se gestiona por código/enlace de gestión por turno (delegado a C-05, interfaz documentada aquí).
- **Migración Alembic 003 (reversible):** tablas de auth (refresh tokens, blacklist de jti).

## Capabilities
### New Capabilities
- `auth/panel-login`: endpoints login/refresh/logout/me con JWT, refresh en cookie HttpOnly y rate limiting por IP+email.
- `auth/jwt-rotation`: rotación de refresh con blacklist de jti y logout revocable.
- `auth/rbac-middleware`: `PermissionContext.require_role()` y dependencia FastAPI para proteger endpoints de panel.

### Modified Capabilities
- Ninguna.

## Impact
- **Backend:** Nuevos módulos en `backend/src/app/auth/` (esquemas Pydantic, servicio de tokens, dependencia RBAC) y routers de auth.
- **Base de Datos:** Migración `003_auth.py` en `backend/src/alembic/versions/` con tablas de refresh tokens y blacklist de jti.
- **Tests:** suite pytest que verifica login correcto (200 + tokens), token expirado (401), refresh rotation con blacklist, matriz RBAC por rol, acceso público sin token y login/logout auditados en `RegistroAuditoria` (RN-GL-01).
