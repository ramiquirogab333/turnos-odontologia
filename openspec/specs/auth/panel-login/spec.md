# auth/panel-login Specification

## Purpose
Añade autenticación JWT del panel interno, rotación de refresh con blacklist de jti, autorización RBAC mediante `PermissionContext.require_role()` y la interfaz de reserva pública sin login, sin modificar las capacidades de C-01/C-02.

## Requirements

### Requirement: Autenticación JWT del panel interno
El sistema SHALL autenticar usuarios del panel mediante `POST /api/auth/login`, devolviendo el access en el JSON y el refresh solo en una cookie `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth`, nunca en un cuerpo de respuesta. Cada petición de panel SHALL validarse contra los claims del JWT y la sesión del servidor de su `sid` (`auth/sesion-panel`), con los roles vigentes en la base.

#### Scenario: Login con credenciales válidas (Happy Path)
- **GIVEN** que existe un usuario activo `recepcion@turnos.test` con rol `recepcion` y contraseña válida (hash almacenado)
- **WHEN** se envía `POST /api/auth/login` con `email` y `password` correctos
- **THEN** el sistema responde 200 con `access_token` (JWT con claims `sub`, `roles`, `email`, `jti`, `sid`, `type=access`, `iat`, `exp`), sin `refresh_token` en el JSON, establece la cookie de refresh con `HttpOnly`, `Secure`, `SameSite=Strict` y `Path=/api/auth`, y crea la sesión identificada por `sid`

#### Scenario: Login con credenciales inválidas (Error de Negocio)
- **GIVEN** que no existe usuario con email `inexistente@turnos.test` o la contraseña no coincide
- **WHEN** se envía `POST /api/auth/login` con credenciales inválidas
- **THEN** el sistema responde 401 sin emitir tokens ni cookie y registra el intento fallido en `RegistroAuditoria` con la IP real del cliente (RN-GL-01)

#### Scenario: Refresh token rotado (Caso de Borde)
- **GIVEN** que existe un refresh token válido con jti `JTI-OLD` en la cookie, de una sesión vigente
- **WHEN** se envía `POST /api/auth/refresh` con la cookie y la cabecera anti-CSRF
- **THEN** el sistema invalida `JTI-OLD`, responde con un `access_token` nuevo de la misma sesión y reemplaza la cookie por un refresh con jti nuevo, y un segundo uso de `JTI-OLD` responde 401

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
`POST /api/auth/logout` SHALL revocar la sesión del servidor del token de acceso y, si es otra, la del refresh de la cookie, de modo que ningún access ni refresh de esas sesiones vuelva a aceptarse, y SHALL borrar la cookie. Repetir el logout no SHALL producir un error interno.

#### Scenario: Logout revoca el refresh (Happy Path)
- **GIVEN** una sesión con su cookie de refresh y un access vigente
- **WHEN** se llama a `POST /api/auth/logout` y después se intenta renovar con ese refresh y pedir la agenda con ese access
- **THEN** el logout responde 200 y borra la cookie, la renovación responde 401 y la agenda responde 401

#### Scenario: El refresh revocado sigue revocado después de 15 minutos (Error de Negocio)
- **GIVEN** un refresh revocado por logout hace 16 minutos, dentro de la duración máxima de su sesión
- **WHEN** se intenta renovar con ese refresh
- **THEN** responde 401, nunca 200 ni 500

#### Scenario: Otra pestaña ya rotó el refresh (Caso de Borde)
- **GIVEN** un token de acceso de la sesión todavía vigente en una pestaña y una cookie con un refresh ya rotado por otra pestaña, de otro `jti` y de la misma sesión
- **WHEN** se llama al logout con ese token de acceso
- **THEN** la sesión queda revocada, el refresh de la cookie ya no se puede usar y el access de la otra pestaña responde 401

### Requirement: El login rechaza usuarios inactivos sin revelarlo
`POST /api/auth/login` SHALL rechazar a un usuario con `is_active = false` con el mismo 401 y el mismo mensaje que una contraseña incorrecta, sin crear sesión, y SHALL auditar el intento con el motivo `usuario_inactivo`. El tiempo de respuesta no SHALL permitir distinguir un email inexistente, un usuario inactivo o una contraseña incorrecta.

#### Scenario: Usuario activo (Happy Path)
- **GIVEN** `dra.ficticia@turnos.test` activa
- **WHEN** ingresa con su contraseña
- **THEN** responde 200

#### Scenario: Usuario inactivo con la contraseña correcta (Error de Negocio)
- **GIVEN** `dra.ficticia@turnos.test` desactivada
- **WHEN** ingresa con su contraseña correcta
- **THEN** responde 401 con "Credenciales inválidas", sin cookie ni sesión, y la auditoría registra `LOGIN_FAILED` con motivo `usuario_inactivo`

#### Scenario: Email inexistente (Caso de Borde)
- **WHEN** se ingresa con `inexistente@turnos.test`
- **THEN** responde el mismo 401 y el servidor igual ejecuta una verificación de contraseña de costo equivalente

### Requirement: La renovación verifica el usuario y emite roles de la base
`POST /api/auth/refresh` SHALL responder 401 y borrar la cookie si el usuario de la sesión está inactivo o la sesión está revocada o vencida. Si renueva, el access nuevo SHALL llevar los roles que el usuario tiene en la base en ese momento.

#### Scenario: Roles actualizados al renovar (Happy Path)
- **GIVEN** una sesión de `rita.ficticia@turnos.test` iniciada con rol `recepcion`, a la que después se le sumó `admin`
- **WHEN** renueva la sesión
- **THEN** responde 200 y el access nuevo lleva los roles `recepcion` y `admin`

#### Scenario: Usuario desactivado con la sesión abierta (Error de Negocio)
- **GIVEN** una sesión vigente de un usuario que fue desactivado directamente en la base, sin revocar sus sesiones
- **WHEN** intenta renovar
- **THEN** responde 401, borra la cookie y no emite tokens

#### Scenario: Dos renovaciones simultáneas de la misma sesión (Caso de Borde)
- **GIVEN** una cookie de refresh válida de una sesión vigente
- **WHEN** llegan a la vez dos renovaciones con ese mismo refresh
- **THEN** exactamente una responde 200 y la otra 401, nunca 500, y la sesión sigue vigente para la ganadora

### Requirement: La auditoría de acceso guarda la IP real del cliente
Los registros de auditoría de login, login fallido, login bloqueado y logout SHALL guardar la IP real del cliente, resuelta según la capacidad `plataforma/limite-de-solicitudes`. Ningún registro SHALL guardar un valor fijo de reemplazo como IP.

#### Scenario: Login auditado (Happy Path)
- **GIVEN** un cliente directo desde `198.51.100.21` y `TRUSTED_PROXIES` vacío
- **WHEN** ingresa con éxito
- **THEN** el registro `LOGIN_OK` guarda la IP `198.51.100.21`

#### Scenario: Bloqueo auditado una sola vez (Error de Negocio)
- **GIVEN** un par IP + email que acaba de superar su límite de login
- **WHEN** llegan 30 intentos más dentro de la misma ventana
- **THEN** hay un solo registro `LOGIN_BLOQUEADO` para ese par y esa ventana, con la IP, y ninguno por cada intento rechazado

#### Scenario: Cliente sin IP conocida (Caso de Borde)
- **GIVEN** un pedido en el que el servidor no conoce la dirección del cliente
- **WHEN** se audita el logout
- **THEN** el campo IP queda vacío (nulo), nunca con un texto inventado
