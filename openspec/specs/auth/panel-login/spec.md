# auth/panel-login Specification

## Purpose
Añade autenticación JWT del panel interno, rotación de refresh con blacklist de jti, autorización RBAC mediante `PermissionContext.require_role()` y la interfaz de reserva pública sin login, sin modificar las capacidades de C-01/C-02.

## Requirements

### Requirement: Autenticación JWT del panel interno
El sistema SHALL autenticar usuarios del panel mediante `POST /api/auth/login`, devolviendo el token de acceso en el JSON y el token de refresh solo en una cookie `HttpOnly`, `Secure`, `SameSite=Strict` y `Path=/api/auth`. El refresh no SHALL aparecer en ningún cuerpo de respuesta. Cada petición de panel SHALL validarse contra los claims `sub`, `roles`, `email`, `jti`, `type`, `iat`, `exp`.

#### Scenario: Login con credenciales válidas (Happy Path)
- **GIVEN** que existe un usuario `recepcion@turnos.test` con rol `recepcion` y contraseña válida (hash almacenado)
- **WHEN** se envía `POST /api/auth/login` con `email` y `password` correctos
- **THEN** el sistema responde 200 con `access_token` (JWT con claims `sub`, `roles`, `email`, `jti`, `type=access`, `iat`, `exp`), sin `refresh_token` en el JSON, y establece la cookie de refresh con `HttpOnly`, `Secure`, `SameSite=Strict` y `Path=/api/auth`

#### Scenario: Login con credenciales inválidas (Error de Negocio)
- **GIVEN** que no existe usuario con email `inexistente@turnos.test` o la contraseña no coincide
- **WHEN** se envía `POST /api/auth/login` con credenciales inválidas
- **THEN** el sistema responde 401 sin emitir tokens ni cookie y registra el intento fallido en `RegistroAuditoria` (RN-GL-01)

#### Scenario: Refresh token rotado (Caso de Borde)
- **GIVEN** que existe un refresh token válido con jti `JTI-OLD` en la cookie
- **WHEN** se envía `POST /api/auth/refresh` con la cookie y la cabecera anti-CSRF
- **THEN** el sistema añade `JTI-OLD` a la blacklist, responde con un `access_token` nuevo y reemplaza la cookie por un refresh con jti nuevo, y un segundo uso de `JTI-OLD` responde 401

### Requirement: RBAC authorization
El sistema SHALL autorizar operaciones de panel mediante `PermissionContext.require_role()` según la matriz de `03_actores_y_roles.md` (actualizada por C-11). `recepcion` / `admin` = CRUD total. `odontologo` = lectura de su agenda y de sus pacientes, y solo las escrituras del escenario «Alcance del rol odontologo»; nunca escribe datos administrativos, vínculos, presupuestos ni pagos.

#### Scenario: La odontóloga ejerce sus permisos (Happy Path)
- **GIVEN** un usuario `odontologo` asociado a la "Dra. Ana Ficticia", un turno suyo `reservado` de hoy y la paciente "Lucía Ejemplo" atendida por ella hace dos meses
- **WHEN** marca atendido ese turno y edita la ficha de Lucía con la `version` vigente
- **THEN** recibe 200 en ambas operaciones

#### Scenario: require_role('recepcion') permite CRUD; odontólogo denegado en pacientes ajenos (Caso de Borde / Matriz RBAC)
- **GIVEN** que el usuario autenticado tiene rol `recepcion` y otro usuario tiene rol `odontologo`
- **WHEN** `recepcion` ejecuta `POST /api/panel/pacientes` (crear paciente) y `odontologo` ejecuta `PUT /api/panel/pacientes/{id_ajeno}` (editar paciente ajeno)
- **THEN** `recepcion` recibe 201 (CRUD permitido) y `odontologo` recibe 403 (denegado: solo lectura de sus pacientes)

#### Scenario: La odontóloga intenta una escritura administrativa (Error de Negocio)
- **GIVEN** el mismo usuario `odontologo` y su paciente "Lucía Ejemplo"
- **WHEN** intenta cancelar un turno propio, crear un presupuesto para Lucía o registrarle un pago
- **THEN** recibe 403 en los tres casos y no cambia nada

#### Scenario: Alcance del rol odontologo (Matriz RBAC)
- **GIVEN** un usuario `odontologo` asociado a una profesional y una paciente suya (al menos un turno `atendido` con esa profesional, O2)
- **WHEN** se evalúan sus permisos
- **THEN** puede leer su agenda, marcar `atendido` los turnos de su profesional (O15), leer los datos administrativos de sus pacientes sin teléfono ni email, y leer ficha, odontograma y presupuestos
- **AND** solo puede escribir ficha y odontograma con acceso clínico vigente (O3, O4, O16), y nunca datos administrativos, vínculos, presupuestos ni pagos

### Requirement: Reserva pública sin login
El sistema SHALL permitir crear un turno público sin autenticación: `POST /api/public/turnos` con nombre + teléfono suficiente (RN-TU-06, DD-01). El paciente no tiene `Usuario`; la gestión posterior se hace por código/enlace por turno (interfaz delegada a C-05, documentada aquí).

#### Scenario: POST /api/public/turnos sin token → 201 (Caso de Borde / Sin login)
- **GIVEN** que no existe sesión ni token de autenticación
- **WHEN** se envía `POST /api/public/turnos` con `nombre` y `telefono` válidos sobre un horario libre vigente
- **THEN** el sistema responde 201 y crea el turno sin requerir `Usuario`, devolviendo código/enlace de gestión pública para cancelar/reprogramar

### Requirement: El refresh se acepta solo por cookie y con protección CSRF
`POST /api/auth/refresh` SHALL leer el token únicamente de la cookie y SHALL exigir la cabecera `X-Panel-Csrf`. Un token enviado por body no SHALL aceptarse. Sin cookie válida SHALL responder 401 y borrar la cookie; sin la cabecera SHALL responder 403 sin rotar nada.

#### Scenario: Renovación desde la pantalla (Happy Path)
- **GIVEN** una cookie de refresh válida
- **WHEN** se llama a `POST /api/auth/refresh` con `X-Panel-Csrf: 1`
- **THEN** responde 200 con un `access_token` nuevo, sin `refresh_token` en el JSON

#### Scenario: Pedido sin cabecera anti-CSRF o token por body (Error de Negocio)
- **GIVEN** una cookie de refresh válida
- **WHEN** llega el pedido sin `X-Panel-Csrf`, o con la cabecera, sin cookie y con el refresh en el body
- **THEN** responde 403 `csrf_requerido` en el primer caso y 401 en el segundo, y ningún token se rota

#### Scenario: Dos renovaciones simultáneas con la misma cookie (Caso de Borde)
- **GIVEN** una cookie de refresh válida
- **WHEN** llegan a la vez dos `POST /api/auth/refresh` con ese mismo token
- **THEN** exactamente una responde 200 y la otra 401, nunca 500

### Requirement: El logout revoca la sesión hasta el vencimiento del refresh
`POST /api/auth/logout` SHALL revocar el `jti` del token de acceso y el del refresh de la cookie, cada uno hasta que pueda vencer su refresh, y SHALL borrar la cookie. Repetir el logout no SHALL producir un error interno.

#### Scenario: Logout revoca el refresh (Happy Path)
- **GIVEN** una sesión con su cookie de refresh
- **WHEN** se llama a `POST /api/auth/logout` y después se intenta renovar con ese refresh
- **THEN** el logout responde 200 y borra la cookie, y la renovación responde 401

#### Scenario: El refresh revocado sigue revocado después de 15 minutos (Error de Negocio)
- **GIVEN** un refresh revocado por logout hace 16 minutos, con vencimiento a 7 días
- **WHEN** se intenta renovar con ese refresh
- **THEN** responde 401, nunca 200 ni 500

#### Scenario: Otra pestaña ya rotó el refresh (Caso de Borde)
- **GIVEN** un token de acceso de la sesión anterior todavía vigente y una cookie con un refresh ya rotado, de otro `jti`
- **WHEN** se llama al logout con ese token de acceso
- **THEN** los dos `jti` quedan revocados y el refresh de la cookie ya no se puede usar
