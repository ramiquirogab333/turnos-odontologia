# Spec Delta: auth/panel-acceso-web

## MODIFIED Requirements

### Requirement: Alta de usuarios del panel
El sistema SHALL ofrecer un comando idempotente que crea o actualiza un usuario del panel con email, rol y profesional asociado, tomando la contraseña de una variable de entorno (R17). La contraseña no SHALL aparecer en logs ni en argumentos de la línea de comandos. Actualizar un usuario desactivado no SHALL reactivarlo: eso solo lo hace la opción de reactivar (capacidad `auth/sesion-panel`).

#### Scenario: Alta de una odontóloga (Happy Path)
- **WHEN** se corre el comando para `dra.ficticia@turnos.test`, rol `odontologo` y la "Dra. Ana Ficticia", con la contraseña en el entorno
- **THEN** el usuario puede ingresar y ve la agenda de esa profesional

#### Scenario: Sin contraseña o rol inválido (Error de Negocio)
- **WHEN** se corre sin la variable de entorno, con un rol inexistente o con un `odontologo` sin profesional
- **THEN** el comando termina con error, explica la causa y no crea nada

#### Scenario: Doble corrida (Caso de Borde)
- **WHEN** se corre dos veces con los mismos datos
- **THEN** queda un solo usuario con un solo rol asignado

#### Scenario: Actualizar un usuario desactivado (Caso de Borde)
- **GIVEN** `dra.ficticia@turnos.test` desactivada
- **WHEN** se corre el alta con sus mismos datos y una contraseña nueva
- **THEN** la contraseña se actualiza, el usuario sigue inactivo y el comando avisa que para habilitarlo hay que usar la opción de reactivar

## ADDED Requirements

### Requirement: El ingreso informa el bloqueo por demasiados intentos
Si el login responde 429, el panel SHALL mostrar "Demasiados intentos. Probá de nuevo en N minutos", con N calculado desde `Retry-After` y redondeado hacia arriba, SHALL seguir en la pantalla de ingreso y no SHALL revelar si el email existe. El mensaje SHALL leerse completo a 360 px (R3) y anunciarse a lectores de pantalla.

#### Scenario: Bloqueo informado (Happy Path)
- **GIVEN** que el login responde 429 con `Retry-After: 600`
- **WHEN** la recepción toca "Ingresar"
- **THEN** ve "Demasiados intentos. Probá de nuevo en 10 minutos" y sigue en la pantalla de ingreso

#### Scenario: Credenciales inválidas antes del límite (Error de Negocio)
- **GIVEN** que el login responde 401
- **WHEN** la recepción toca "Ingresar"
- **THEN** ve el mensaje de credenciales incorrectas de siempre, no el de bloqueo

#### Scenario: Retry-After ausente o menor a un minuto (Caso de Borde)
- **GIVEN** que el login responde 429 con `Retry-After: 20` o sin esa cabecera
- **WHEN** la recepción toca "Ingresar"
- **THEN** ve "Demasiados intentos. Probá de nuevo en 1 minuto" (singular), sin mostrar "0" ni "NaN"

### Requirement: Una renovación limitada no cierra la sesión
Si la renovación de sesión responde 429, el panel no SHALL descartar la sesión ni mostrar la pantalla de ingreso: SHALL tratarlo como una falla temporal del servidor y permitir reintentar. Solo un 401 de la renovación SHALL cerrar la sesión local.

#### Scenario: Renovación limitada (Happy Path)
- **GIVEN** una sesión en la agenda cuyo access venció
- **WHEN** la renovación responde 429
- **THEN** la agenda muestra el error de carga con "Reintentar" y la sesión sigue abierta

#### Scenario: Renovación rechazada por sesión vencida (Error de Negocio)
- **GIVEN** una sesión que superó su duración máxima
- **WHEN** la renovación responde 401
- **THEN** el panel muestra la pantalla de ingreso con "Tu sesión venció, ingresá de nuevo"

#### Scenario: Access revocado por un logout de otra pestaña (Caso de Borde)
- **GIVEN** dos pestañas abiertas y la segunda sin conexión cuando la primera tocó "Salir"
- **WHEN** la segunda recupera la conexión y su próximo pedido responde 401
- **THEN** intenta renovar una sola vez, recibe 401 y muestra la pantalla de ingreso, sin renovar en bucle
