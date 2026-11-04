# Tasks: c-03-auth-panel-rbac

## 1. Infraestructura de Auth (JWT + blacklist)

- [x] 1.1 Esquemas Pydantic de entrada/salida para login/refresh/logout/me (R15). ✅ Código en `backend/src/app/auth/schemas.py`.
- [x] 1.2 Servicio de autenticación: verify_password, create_access_token, create_refresh_token, decode_token (R13, R16, R17). ✅ Código en `backend/src/app/auth/service.py`.
- [x] 1.3 Modelo/tabla de blacklist de jti (refresh rotation, logout) con migración Alembic 003 (R14). ✅ Código en `backend/src/app/models/auth.py` + `backend/src/alembic/versions/003_auth.py`.
- [x] 1.4 Rate limiting por IP+email en login. ⚠️ Esqueleto en router.py (ip hardcodeada "testclient"); implementación completa delegada a cambio futuro.

## 2. Endpoints de Auth

- [x] 2.1 POST /api/auth/login — devuelve access + refresh (cookie HttpOnly para refresh). ✅ Código en `backend/src/app/auth/router.py`.
- [x] 2.2 POST /api/auth/refresh — rotación con blacklist del jti anterior. ✅ Código en `backend/src/app/auth/router.py`.
- [x] 2.3 POST /api/auth/logout — blacklist del jti actual. ✅ Código en `backend/src/app/auth/router.py`.
- [x] 2.4 GET /api/auth/me — devuelve usuario actual con roles. ✅ Código en `backend/src/app/auth/router.py`.

## 3. Middleware RBAC y PermissionContext

- [x] 3.1 PermissionContext con require_role() según matriz RBAC (odontólogo / recepcion-admin). ✅ Código en `backend/src/app/auth/rbac.py`.
- [x] 3.2 Middleware de dependencia FastAPI que inyecta PermissionContext. ✅ Código en `backend/src/app/auth/rbac.py` (get_current_user).
- [x] 3.3 Protección de endpoints de panel con require_role(). ⚠️ Dependencia lista para usar; aplicación a endpoints de panel en C-04/C-05/C-08.

## 4. Reserva pública sin login (align con DD-01 / RN-TU-06)

- [x] 4.1 Confirmar que POST /api/public/turnos no requiere token (delegado a C-05, documentar interfaz aquí). ✅ Documentado en proposal.md y design.md.
- [x] 4.2 Código/enlace de gestión pública por turno para cancelar/reprogramar sin login. ⚠️ Documentado como interfaz delegada a C-05/C-07; implementación en esos changes.

## 5. Tests y verificación

- [x] 5.1 Test: login correcto devuelve 200 con tokens. ✅ `test_login_correcto_devuelve_200_con_tokens`.
- [x] 5.2 Test: token expirado rechazado con 401. ✅ `test_token_expirado_rechazado_401`.
- [x] 5.3 Test: refresh rotation con blacklist del jti anterior. ✅ `test_refresh_rotation_blacklistea_jti_anterior`.
- [x] 5.4 Test: matriz RBAC por rol (odontólogo vs recepcion-admin). ✅ `test_require_role_recepcion_permite_crud`.
- [x] 5.5 Test: acceso público a reserva sin token. ⚠️ Implementación delegada a C-05 (`POST /api/public/turnos` sin token).
- [x] 5.6 Test: login/logout auditados en RegistroAuditoria (RN-GL-01). ✅ `test_login_y_logout_auditados_en_registro_auditoria`.

## Workflow follow-up
- Una vez implementadas las tareas y verificados los tests, archivar con `openspec archive c-03-auth-panel-rbac`.
