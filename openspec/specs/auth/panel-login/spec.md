# auth/panel-login Specification

## Purpose
Añade autenticación JWT del panel interno, rotación de refresh con blacklist de jti, autorización RBAC mediante `PermissionContext.require_role()` y la interfaz de reserva pública sin login, sin modificar las capacidades de C-01/C-02.

## Requirements

### Requirement: Autenticación JWT del panel interno
El sistema SHALL autenticar usuarios del panel mediante `POST /api/auth/login` emitiendo un par de tokens JWT (access de expiración corta + refresh en cookie HttpOnly), y validar cada petición de panel contra claims `sub`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.

#### Scenario: Login con credenciales válidas (Happy Path)
- **GIVEN** que existe un usuario `recepcion@turnos.test` con rol `recepcion` y contraseña válida (hash almacenado)
- **WHEN** se envía `POST /api/auth/login` con `email` y `password` correctos
- **THEN** el sistema responde 200 con `access_token` (JWT con claims `sub`, `roles`, `email`, `jti`, `type=access`, `iat`, `exp`) y establece `refresh_token` en cookie HttpOnly (secure, samesite=lax)

#### Scenario: Login con credenciales inválidas (Error de Negocio)
- **GIVEN** que no existe usuario con email `inexistente@turnos.test` o la contraseña no coincide
- **WHEN** se envía `POST /api/auth/login` con credenciales inválidas
- **THEN** el sistema responde 401 sin emitir tokens y registra el intento fallido en `RegistroAuditoria` (RN-GL-01)

#### Scenario: Refresh token rotado (Caso de Borde)
- **GIVEN** que existe un refresh token válido con jti `JTI-OLD` en cookie HttpOnly
- **WHEN** se envía `POST /api/auth/refresh` con ese token
- **THEN** el sistema añade `JTI-OLD` a la blacklist de jti, emite un nuevo par de tokens (access con jti nuevo, refresh con jti nuevo en cookie), y `JTI-OLD` queda revocada para futuros usos

### Requirement: RBAC authorization
El sistema SHALL autorizar operaciones de panel mediante `PermissionContext.require_role()` según la matriz de `03_actores_y_roles.md`: `odontologo` = lectura de su agenda y sus pacientes; `recepcion` / `admin` = CRUD total.

#### Scenario: require_role('recepcion') permite CRUD; odontólogo denegado en pacientes ajenos (Caso de Borde / Matriz RBAC)
- **GIVEN** que el usuario autenticado tiene rol `recepcion` y otro usuario tiene rol `odontologo`
- **WHEN** `recepcion` ejecuta `POST /api/panel/pacientes` (crear paciente) y `odontologo` ejecuta `PUT /api/panel/pacientes/{id_ajeno}` (editar paciente ajeno)
- **THEN** `recepcion` recibe 201 (CRUD permitido) y `odontologo` recibe 403 (denegado: solo lectura de sus pacientes)

### Requirement: Reserva pública sin login
El sistema SHALL permitir crear un turno público sin autenticación: `POST /api/public/turnos` con nombre + teléfono suficiente (RN-TU-06, DD-01). El paciente no tiene `Usuario`; la gestión posterior se hace por código/enlace por turno (interfaz delegada a C-05, documentada aquí).

#### Scenario: POST /api/public/turnos sin token → 201 (Caso de Borde / Sin login)
- **GIVEN** que no existe sesión ni token de autenticación
- **WHEN** se envía `POST /api/public/turnos` con `nombre` y `telefono` válidos sobre un horario libre vigente
- **THEN** el sistema responde 201 y crea el turno sin requerir `Usuario`, devolviendo código/enlace de gestión pública para cancelar/reprogramar
