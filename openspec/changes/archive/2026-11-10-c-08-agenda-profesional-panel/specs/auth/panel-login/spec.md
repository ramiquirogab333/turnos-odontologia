# Spec Delta: auth/panel-login

## MODIFIED Requirements

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

## ADDED Requirements

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
