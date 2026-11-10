# auth/panel-acceso-web Specification

## Purpose
Define cómo ingresa, se mantiene y sale de la sesión el personal de la clínica desde el navegador, sobre la API de C-03 con el refresh en cookie HttpOnly (decisiones O1 y O2 de C-08, aprobadas por el usuario el 2026-11-09), y cómo se dan de alta los usuarios del panel (O4).

## Requirements

### Requirement: Ingreso al panel
El panel SHALL pedir email y contraseña antes de mostrar cualquier dato, salvo que exista una sesión restaurable. Con credenciales válidas SHALL entrar a la agenda; con credenciales inválidas SHALL mostrar un mensaje que no revele si el email existe. Un usuario sin rol `admin`, `recepcion` ni `odontologo` no SHALL entrar.

#### Scenario: Ingreso correcto (Happy Path)
- **GIVEN** el usuario `recepcion.e2e@turnos.test` con rol `recepcion`
- **WHEN** ingresa su email y contraseña
- **THEN** ve la agenda del día

#### Scenario: Credenciales inválidas (Error de Negocio)
- **WHEN** ingresa una contraseña incorrecta o un email que no existe
- **THEN** ve el mismo mensaje "El email o la contraseña no son correctos", sin distinguir el caso, y sigue en la pantalla de ingreso

#### Scenario: Usuario sin rol de panel (Caso de Borde)
- **GIVEN** un usuario autenticable sin ningún rol asignado
- **WHEN** ingresa con sus credenciales correctas
- **THEN** ve "Tu usuario no tiene acceso al panel" y no se muestra ningún dato de la agenda

### Requirement: La sesión se restaura sola y el access vive solo en memoria
El token de acceso SHALL guardarse solo en memoria y ningún token SHALL escribirse en `localStorage`, `sessionStorage` ni en la URL. Al abrir o recargar el panel, SHALL intentar restaurar la sesión con la cookie de refresh; si no puede, SHALL mostrar la pantalla de ingreso.

#### Scenario: Recarga con sesión vigente (Happy Path)
- **GIVEN** una sesión iniciada con su cookie de refresh vigente
- **WHEN** se recarga la página, se cierra y se vuelve a abrir la pestaña, o se abre otra pestaña
- **THEN** se ve la agenda sin pedir ingreso, y ningún token quedó en el almacenamiento del navegador

#### Scenario: Sin cookie válida (Error de Negocio)
- **GIVEN** que la cookie de refresh no existe, venció o fue revocada
- **WHEN** se abre el panel
- **THEN** se muestra la pantalla de ingreso, sin mostrar un error

#### Scenario: Dos pestañas que se abren a la vez (Caso de Borde)
- **GIVEN** una cookie de refresh vigente
- **WHEN** dos pestañas abren el panel al mismo tiempo
- **THEN** las renovaciones se hacen de a una y las dos pestañas muestran la agenda

### Requirement: La sesión se renueva sin interrumpir
Ante un 401, el panel SHALL renovar el token de acceso una sola vez por pestaña, aunque haya varios pedidos en curso, y SHALL repetir esos pedidos. Si la renovación falla, SHALL volver a la pantalla de ingreso.

#### Scenario: Token de acceso vencido (Happy Path)
- **GIVEN** una sesión con el token de acceso vencido y la cookie de refresh válida
- **WHEN** el panel pide la agenda y sus opciones al mismo tiempo y las dos responden 401
- **THEN** se hace un único pedido de renovación, los dos pedidos se repiten y la agenda se muestra

#### Scenario: Renovación rechazada (Error de Negocio)
- **GIVEN** un refresh vencido o revocado
- **WHEN** el panel intenta renovar la sesión
- **THEN** descarta el token de acceso y muestra la pantalla de ingreso con "Tu sesión venció, ingresá de nuevo"

#### Scenario: Reintento después de renovar (Caso de Borde)
- **GIVEN** un pedido que responde 401 aun después de renovar con éxito
- **WHEN** el panel recibe ese segundo 401
- **THEN** no vuelve a renovar en bucle y muestra la pantalla de ingreso

### Requirement: Salida del panel
"Salir" SHALL llamar a `POST /api/auth/logout`, descartar el token de acceso, avisar a las demás pestañas y volver a la pantalla de ingreso. Si el servidor no pudo cerrar la sesión, SHALL decirlo claramente, porque la cookie HttpOnly no se puede borrar desde el navegador.

#### Scenario: Salir (Happy Path)
- **GIVEN** una sesión iniciada y otra pestaña abierta
- **WHEN** se toca "Salir"
- **THEN** se llama al logout, las dos pestañas muestran la pantalla de ingreso y al recargar se sigue pidiendo ingreso

#### Scenario: Volver atrás después de salir (Error de Negocio)
- **GIVEN** que se cerró la sesión
- **WHEN** se usa el botón "atrás" del navegador
- **THEN** no se muestra la agenda y sigue la pantalla de ingreso

#### Scenario: Logout sin conexión (Caso de Borde)
- **GIVEN** que la API no responde al logout
- **WHEN** se toca "Salir"
- **THEN** se muestra la pantalla de ingreso con el aviso "No pudimos cerrar la sesión en el servidor. Volvé a salir cuando tengas conexión" y la opción de reintentar

### Requirement: Alta de usuarios del panel
El sistema SHALL ofrecer un comando idempotente que crea o actualiza un usuario del panel con email, rol y profesional asociado, tomando la contraseña de una variable de entorno (R17). La contraseña no SHALL aparecer en logs ni en argumentos de la línea de comandos.

#### Scenario: Alta de una odontóloga (Happy Path)
- **WHEN** se corre el comando para `dra.ficticia@turnos.test`, rol `odontologo` y la "Dra. Ana Ficticia", con la contraseña en el entorno
- **THEN** el usuario puede ingresar y ve la agenda de esa profesional

#### Scenario: Sin contraseña o rol inválido (Error de Negocio)
- **WHEN** se corre sin la variable de entorno, con un rol inexistente o con un `odontologo` sin profesional
- **THEN** el comando termina con error, explica la causa y no crea nada

#### Scenario: Doble corrida (Caso de Borde)
- **WHEN** se corre dos veces con los mismos datos
- **THEN** queda un solo usuario con un solo rol asignado
