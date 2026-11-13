# plataforma/limite-de-solicitudes Specification

## Purpose
Limita la cantidad de solicitudes que un cliente puede hacer al login, a la renovación de sesión y a los endpoints públicos, para frenar la adivinación de contraseñas y el abuso de la reserva pública, e identifica al cliente por su IP real detrás de un proxy de confianza (C-15, decisiones O4–O10 y O17, PENDIENTES de aprobación).

## Requirements

### Requirement: El login se limita por IP y email, por IP y por email
`POST /api/auth/login` SHALL rechazar con 429 un intento cuando se supera cualquiera de estos límites dentro de su ventana: fallos para el mismo par IP + email, intentos desde la misma IP, o fallos para el mismo email desde cualquier IP. Un login exitoso SHALL reiniciar el contador del par IP + email. Ningún límite SHALL bloquear la cuenta de forma permanente.

#### Scenario: Fallos por debajo del límite (Happy Path)
- **GIVEN** el límite de 5 fallos cada 15 minutos para un par IP + email
- **WHEN** desde `203.0.113.20` se envían 4 contraseñas incorrectas para `recepcion@turnos.test` y luego la correcta
- **THEN** los 4 primeros responden 401, el quinto responde 200, y el contador de ese par vuelve a cero

#### Scenario: Se supera el límite del par IP + email (Error de Negocio)
- **GIVEN** 5 fallos para `recepcion@turnos.test` desde `203.0.113.20` en los últimos 15 minutos
- **WHEN** desde esa IP se envía un sexto intento, aun con la contraseña correcta
- **THEN** responde 429 con `motivo: "demasiados_intentos"` y la cabecera `Retry-After`, no verifica la contraseña y no crea ninguna sesión

#### Scenario: Otra IP no queda bloqueada por el par (Caso de Borde)
- **GIVEN** el par de `203.0.113.20` bloqueado como en el escenario anterior
- **WHEN** la usuaria real ingresa desde `198.51.100.7` con la contraseña correcta
- **THEN** responde 200, porque el límite por email (20 fallos por hora) todavía no se alcanzó

### Requirement: El 429 no revela si un email existe
El límite de login SHALL aplicarse igual a un email registrado y a uno inexistente, y la respuesta 429 SHALL ser idéntica en ambos casos.

#### Scenario: Email registrado (Happy Path)
- **GIVEN** 5 fallos para `recepcion@turnos.test` desde una IP
- **WHEN** se envía otro intento
- **THEN** responde 429 con el cuerpo `{"detail": "Demasiados intentos. Probá de nuevo más tarde.", "motivo": "demasiados_intentos"}`

#### Scenario: Email inexistente (Error de Negocio)
- **GIVEN** 5 fallos para `inexistente@turnos.test` desde una IP
- **WHEN** se envía otro intento
- **THEN** responde 429 con el mismo cuerpo y la misma forma de `Retry-After` que con un email registrado

#### Scenario: Email con mayúsculas y espacios (Caso de Borde)
- **GIVEN** 5 fallos para `recepcion@turnos.test`
- **WHEN** se intenta con ` Recepcion@Turnos.TEST `
- **THEN** cuenta para el mismo contador y responde 429

### Requirement: La renovación de sesión se limita por IP
`POST /api/auth/refresh` SHALL rechazar con 429 los pedidos de una IP que superen su límite dentro de la ventana, sin rotar ni revocar nada.

#### Scenario: Uso normal de varias pestañas (Happy Path)
- **GIVEN** el límite de 60 renovaciones cada 15 minutos por IP
- **WHEN** una recepción con tres pestañas renueva 6 veces en 15 minutos
- **THEN** todas responden según su cookie, sin 429

#### Scenario: Ráfaga de renovaciones (Error de Negocio)
- **GIVEN** 60 renovaciones desde `203.0.113.30` en los últimos 15 minutos
- **WHEN** llega la renovación 61 con una cookie válida
- **THEN** responde 429 con `Retry-After`, la cookie no se borra y la sesión sigue válida

#### Scenario: Falta la cabecera anti-CSRF (Caso de Borde)
- **GIVEN** una IP por debajo del límite
- **WHEN** llega un refresh sin `X-Panel-Csrf`
- **THEN** responde 403 `csrf_requerido` como hasta ahora, y el pedido cuenta para el límite de la IP

### Requirement: Los endpoints públicos se limitan por IP en dos niveles
Los endpoints `/api/public/*` SHALL limitarse por IP con un límite estricto para los de escritura (reserva, inicio de seña, cancelar, reprogramar y confirmar) y uno generoso para los de lectura (catálogo, profesionales, disponibilidad, consulta de gestión y estado de la seña). Los webhooks de pagos no SHALL limitarse por IP.

#### Scenario: Paciente que reserva (Happy Path)
- **GIVEN** los límites por defecto (10 escrituras cada 10 minutos, 120 lecturas por minuto)
- **WHEN** un paciente consulta disponibilidad 15 veces y reserva un turno
- **THEN** todas las respuestas son las de siempre, sin 429

#### Scenario: Ráfaga de reservas (Error de Negocio)
- **GIVEN** 10 escrituras públicas desde `203.0.113.40` en los últimos 10 minutos
- **WHEN** esa IP envía otra reserva
- **THEN** responde 429 con `motivo: "demasiados_intentos"` y `Retry-After`, y no crea ningún turno

#### Scenario: Webhook de Mercado Pago (Caso de Borde)
- **GIVEN** 200 notificaciones firmadas de Mercado Pago desde la misma IP en un minuto
- **WHEN** llega la siguiente
- **THEN** se procesa según su firma, sin 429

### Requirement: Contrato de la respuesta 429
Toda respuesta por límite superado SHALL tener estado 429, el cuerpo `{"detail": <mensaje en castellano>, "motivo": "demasiados_intentos"}` y la cabecera `Retry-After` con los segundos enteros hasta que se libere la ventana (mínimo 1). No SHALL incluir datos del usuario ni el valor de los contadores.

#### Scenario: Retry-After al comienzo de la ventana (Happy Path)
- **GIVEN** una ventana de 15 minutos que se llenó hace 1 minuto
- **WHEN** se rechaza un pedido
- **THEN** `Retry-After` vale entre 1 y 840

#### Scenario: Pedido después de la ventana (Error de Negocio evitado)
- **GIVEN** una ventana vencida
- **WHEN** llega un pedido nuevo
- **THEN** no responde 429 por esa ventana

#### Scenario: Último segundo de la ventana (Caso de Borde)
- **GIVEN** una ventana a la que le quedan 300 milisegundos
- **WHEN** se rechaza un pedido
- **THEN** `Retry-After` vale 1, nunca 0

### Requirement: Sin el almacén de contadores la API sigue atendiendo
Si el almacén de contadores no responde, la API SHALL atender el pedido sin aplicar el límite y SHALL registrar un aviso sin datos personales (ni email ni IP completa). Nunca SHALL responder 500 por esa causa.

#### Scenario: Almacén disponible (Happy Path)
- **WHEN** el almacén responde
- **THEN** los límites se aplican como en los requisitos anteriores

#### Scenario: Almacén caído durante un login (Error de Negocio)
- **GIVEN** que el almacén de contadores no responde
- **WHEN** la recepción ingresa con credenciales válidas
- **THEN** responde 200 y el log registra un aviso de límite no aplicado sin el email ni la IP

#### Scenario: Almacén lento (Caso de Borde)
- **GIVEN** que el almacén tarda más que el tiempo máximo de espera configurado
- **WHEN** llega un pedido público de lectura
- **THEN** se atiende sin límite dentro de ese tiempo máximo más el tiempo normal de la consulta

### Requirement: Los límites se configuran por entorno
Cada límite y su ventana SHALL configurarse por variable de entorno con un valor por defecto seguro. Un valor no positivo o no numérico SHALL impedir el arranque con un mensaje que nombre la variable.

#### Scenario: Valores por defecto (Happy Path)
- **WHEN** la API arranca sin variables de límite
- **THEN** aplica los valores por defecto documentados en `08_arquitectura_propuesta.md`

#### Scenario: Valor inválido (Error de Negocio)
- **GIVEN** `RATE_LIMIT_LOGIN_IP_MAX=0`
- **WHEN** arranca la API
- **THEN** no arranca e informa la variable inválida

#### Scenario: Límites amplios para E2E (Caso de Borde)
- **GIVEN** `RATE_LIMIT_LOGIN_IP_MAX=1000` en el entorno E2E
- **WHEN** la suite del panel ingresa 40 veces desde la misma IP
- **THEN** ningún ingreso responde 429, y el límite del par IP + email sigue en su valor por defecto

### Requirement: La IP del cliente se toma del proxy solo si es de confianza
La IP usada para los límites y la auditoría SHALL ser la del socket, salvo que el pedido llegue desde un proxy listado en `TRUSTED_PROXIES`; en ese caso SHALL tomarse de `X-Forwarded-For`. Sin proxies de confianza configurados, `X-Forwarded-For` SHALL ignorarse.

#### Scenario: Detrás del proxy de la clínica (Happy Path)
- **GIVEN** `TRUSTED_PROXIES=10.0.0.5`
- **WHEN** llega un login desde `10.0.0.5` con `X-Forwarded-For: 203.0.113.50`
- **THEN** el límite y la auditoría usan `203.0.113.50`

#### Scenario: Cabecera falsificada (Error de Negocio)
- **GIVEN** `TRUSTED_PROXIES` vacío
- **WHEN** un cliente directo `198.51.100.9` envía `X-Forwarded-For: 203.0.113.99`
- **THEN** el límite y la auditoría usan `198.51.100.9`

#### Scenario: Cadena de proxies (Caso de Borde)
- **GIVEN** `TRUSTED_PROXIES=10.0.0.5`
- **WHEN** llega desde `10.0.0.5` con `X-Forwarded-For: 192.0.2.1, 203.0.113.50`
- **THEN** se usa `203.0.113.50`, la última dirección no confiable de la cadena, y no `192.0.2.1`, que el cliente pudo inventar
