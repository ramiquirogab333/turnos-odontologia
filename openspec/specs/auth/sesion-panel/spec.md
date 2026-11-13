# auth/sesion-panel Specification

## Purpose
Define el ciclo de vida de la sesión del panel en el servidor: cómo nace con el login, cómo se verifica en cada pedido autenticado, cuándo se revoca o vence, y cómo se purga sin volver ineficaz un cierre de sesión (C-15, decisiones O1–O3, O11–O13, PENDIENTES de aprobación).

## Requirements

### Requirement: Cada login crea una sesión identificable en el servidor
Un login exitoso SHALL crear una sesión del panel con un identificador opaco e impredecible, asociada al usuario, con su instante de creación, su vencimiento absoluto y la IP real de origen. El access y el refresh emitidos SHALL llevar ese identificador. Dos logins del mismo usuario SHALL crear dos sesiones independientes.

#### Scenario: Login crea la sesión (Happy Path)
- **GIVEN** la usuaria `recepcion@turnos.test` activa con rol `recepcion`
- **WHEN** ingresa con credenciales válidas desde la IP `203.0.113.10` a las 08:00 (hora de la clínica)
- **THEN** existe una sesión nueva de esa usuaria, creada a las 08:00, con vencimiento absoluto a las 20:00 (`SESION_MAXIMA_HORAS=12`) e IP `203.0.113.10`, y los dos tokens llevan su identificador

#### Scenario: Login fallido no crea sesión (Error de Negocio)
- **GIVEN** la misma usuaria
- **WHEN** ingresa con una contraseña incorrecta
- **THEN** responde 401 y no se crea ninguna sesión

#### Scenario: Dos dispositivos (Caso de Borde)
- **GIVEN** la misma usuaria con una sesión abierta en un equipo
- **WHEN** ingresa desde un segundo equipo
- **THEN** hay dos sesiones vigentes con identificadores distintos, y cerrar una no afecta a la otra

### Requirement: Cada pedido autenticado verifica la sesión, el usuario y sus roles en la base
Todo endpoint que exige token de acceso SHALL rechazar con 401 un token cuya sesión esté revocada o vencida, o cuyo usuario esté inactivo, aunque el JWT siga vigente. Los permisos SHALL evaluarse con los roles que el usuario tiene en la base en ese momento, no con los del token.

#### Scenario: Pedido con sesión vigente (Happy Path)
- **GIVEN** una sesión vigente de `recepcion@turnos.test` con rol `recepcion`
- **WHEN** pide `GET /api/panel/agenda` con su access
- **THEN** responde 200

#### Scenario: Access de una sesión cerrada (Error de Negocio)
- **GIVEN** que la usuaria cerró la sesión hace 1 minuto y su access vence dentro de 14 minutos
- **WHEN** se usa ese access en `GET /api/panel/agenda`
- **THEN** responde 401 y no devuelve ningún dato

#### Scenario: Rol quitado con la sesión abierta (Caso de Borde)
- **GIVEN** la usuaria `rita.ficticia@turnos.test` con roles `recepcion` y `odontologo`, una sesión vigente y un access emitido con ambos roles
- **WHEN** se le quita el rol `recepcion` en la base y, con el mismo access, pide la caja del día
- **THEN** responde 403, porque los permisos se evalúan con el rol `odontologo` que tiene ahora

### Requirement: La sesión tiene una duración máxima absoluta
Ninguna sesión SHALL durar más de `SESION_MAXIMA_HORAS` desde su login, sin importar cuántas veces se renueve. Ni el access ni el refresh emitidos SHALL vencer después del vencimiento absoluto de su sesión. Pasado ese instante, el refresh SHALL responder 401 y borrar la cookie.

#### Scenario: Renovación dentro del máximo (Happy Path)
- **GIVEN** una sesión iniciada a las 08:00 con máximo de 12 h
- **WHEN** se renueva a las 19:50
- **THEN** responde 200, y el access y el refresh nuevos vencen a más tardar a las 20:00

#### Scenario: Renovación pasado el máximo (Error de Negocio)
- **GIVEN** la misma sesión
- **WHEN** se intenta renovar a las 20:01
- **THEN** responde 401, borra la cookie de refresh y no emite ningún token

#### Scenario: Instante exacto del vencimiento (Caso de Borde)
- **GIVEN** la misma sesión
- **WHEN** se intenta renovar exactamente a las 20:00:00
- **THEN** responde 401: el vencimiento es exclusivo

### Requirement: Un token sin sesión del servidor no se acepta
Un access o refresh con firma válida pero sin identificador de sesión, o con un identificador que no existe en la base, SHALL rechazarse con 401. Esto incluye los tokens emitidos antes de este cambio.

#### Scenario: Token emitido antes del despliegue (Happy Path de la migración)
- **GIVEN** un refresh válido emitido antes de desplegar C-15, sin identificador de sesión
- **WHEN** se intenta renovar
- **THEN** responde 401 y borra la cookie, y el panel muestra la pantalla de ingreso

#### Scenario: Sesión inexistente (Error de Negocio)
- **GIVEN** un access firmado con la clave vigente y un identificador de sesión que no existe en la base
- **WHEN** se usa en cualquier endpoint del panel
- **THEN** responde 401

#### Scenario: Sesión purgada (Caso de Borde)
- **GIVEN** una sesión vencida que ya fue purgada
- **WHEN** alguien presenta un token de esa sesión con el reloj de la máquina adelantado
- **THEN** responde 401, nunca 200 ni 500

### Requirement: Desactivar un usuario revoca todas sus sesiones
El comando de alta de usuarios SHALL permitir desactivar y reactivar un usuario. Desactivarlo SHALL marcarlo inactivo y revocar todas sus sesiones vigentes en la misma transacción, y SHALL auditarse. Reactivarlo no SHALL revivir sesiones revocadas.

#### Scenario: Desactivar a una odontóloga (Happy Path)
- **GIVEN** `dra.ficticia@turnos.test` con dos sesiones vigentes
- **WHEN** se corre el comando con `--desactivar` para ese email
- **THEN** el usuario queda inactivo, sus dos sesiones quedan revocadas, sus access y refresh responden 401, y la auditoría registra la desactivación con la cantidad de sesiones revocadas

#### Scenario: Usuario inexistente (Error de Negocio)
- **WHEN** se corre `--desactivar` con `nadie@turnos.test`, que no existe
- **THEN** el comando termina con error, explica la causa y no cambia nada

#### Scenario: Reactivar (Caso de Borde)
- **GIVEN** la odontóloga desactivada del primer escenario
- **WHEN** se corre `--reactivar` y ella usa su refresh viejo
- **THEN** el refresh viejo sigue respondiendo 401 y ella puede ingresar de nuevo con su contraseña

### Requirement: La purga de sesiones vencidas no vuelve ineficaz un cierre de sesión
Las sesiones SHALL purgarse solo cuando todos sus tokens ya vencieron: su vencimiento absoluto pasó hace más que el margen configurado. Una sesión revocada y todavía no vencida SHALL conservarse, de modo que sus tokens sigan rechazándose.

#### Scenario: Purga de una sesión vieja (Happy Path)
- **GIVEN** una sesión cuyo vencimiento absoluto fue hace 2 horas, con margen de 1 hora
- **WHEN** corre la purga
- **THEN** la sesión se borra

#### Scenario: Sesión revocada y no vencida (Error de Negocio)
- **GIVEN** una sesión cerrada por logout hace 10 minutos y con vencimiento absoluto dentro de 5 horas
- **WHEN** corre la purga y después se presenta su refresh
- **THEN** la sesión sigue en la base y el refresh responde 401

#### Scenario: Dentro del margen (Caso de Borde)
- **GIVEN** una sesión cuyo vencimiento absoluto fue hace 30 minutos, con margen de 1 hora
- **WHEN** corre la purga
- **THEN** la sesión se conserva hasta un ciclo posterior
