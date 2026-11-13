# Spec Delta: auth/panel-login

## MODIFIED Requirements

### Requirement: Autenticación JWT del panel interno
El sistema SHALL autenticar usuarios del panel mediante `POST /api/auth/login`, devolviendo el token de acceso en el JSON y el token de refresh solo en una cookie `HttpOnly`, `Secure`, `SameSite=Strict` y `Path=/api/auth`. El refresh no SHALL aparecer en ningún cuerpo de respuesta. Cada petición de panel SHALL validarse contra los claims `sub`, `roles`, `email`, `jti`, `sid`, `type`, `iat`, `exp` y contra la sesión del servidor identificada por `sid` (capacidad `auth/sesion-panel`); los permisos SHALL evaluarse con los roles vigentes en la base.

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

## ADDED Requirements

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
