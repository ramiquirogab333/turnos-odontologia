# Spec Delta: integraciones/google-calendar

## Purpose

Sincroniza la agenda de cada profesional con su Google Calendar en ambos sentidos (US-006, RN-GC-01): los turnos que bloquean agenda aparecen como eventos en Google, los eventos ocupados de Google se conocen como franjas ocupadas, y todo conflicto entre ambos se resuelve a mano con un criterio visible, nunca sobrescribiendo solo (RN-GC-02).

Las referencias `(Ox)` remiten a las decisiones de `design.md`. Todos los ejemplos usan datos sintéticos (R19).

## ADDED Requirements

### Requirement: La profesional conecta su propio Google Calendar
`POST /api/panel/google-calendar/conexion/iniciar` SHALL devolver la URL de autorización de Google solo a un usuario con rol `odontologo` vinculado a una profesional, para el calendario principal de esa profesional (O2, O3). La URL SHALL llevar un `state` de un solo uso que vence a los 10 minutos y un desafío PKCE.

#### Scenario: Iniciar la conexión (Happy Path)
- **GIVEN** la usuaria `ana.prueba@example.com` con rol `odontologo` vinculada a la profesional 7, sin conexión activa
- **WHEN** pide `POST /api/panel/google-calendar/conexion/iniciar`
- **THEN** recibe 200 con `url_autorizacion` hacia Google con el permiso de eventos de calendario, `state` y `code_challenge`, y la conexión de la profesional 7 queda `pendiente`

#### Scenario: Recepción intenta conectar en nombre de otra (Error de Negocio)
- **GIVEN** un usuario con rol `recepcion` o `admin` sin profesional vinculada
- **WHEN** pide `POST /api/panel/google-calendar/conexion/iniciar`
- **THEN** recibe 403 y no se crea ni cambia ninguna conexión; sin sesión recibe 401

#### Scenario: Volver a iniciar con una conexión activa (Caso de Borde)
- **GIVEN** la profesional 7 con conexión `activa`
- **WHEN** su usuaria pide iniciar otra vez
- **THEN** recibe 409 `conexion_activa` y la conexión existente no cambia

### Requirement: El regreso de Google guarda la conexión con los tokens cifrados
`GET /api/panel/google-calendar/oauth/callback` SHALL aceptar solo un `state` vigente y no usado, canjear el código y dejar la conexión `activa` con los tokens cifrados en reposo (O1), y SHALL redirigir al panel con el resultado. Ninguna respuesta, log ni auditoría SHALL contener un token.

#### Scenario: Autorización concedida (Happy Path)
- **GIVEN** una conexión `pendiente` de la profesional 7 con `state` vigente
- **WHEN** Google redirige al callback con un código válido y ese `state`
- **THEN** la conexión queda `activa` con la cuenta `ana.prueba@example.com`, los tokens se guardan cifrados, se audita la conexión y el navegador vuelve a `#/google-calendar` con resultado `conectado`

#### Scenario: State vencido, usado o adulterado (Error de Negocio)
- **GIVEN** un `state` de hace 11 minutos, ya usado o con la firma alterada
- **WHEN** llega al callback
- **THEN** no se canjea el código, la conexión no queda `activa` y el navegador vuelve al panel con resultado `error_autorizacion`

#### Scenario: La profesional rechaza el permiso en Google (Caso de Borde)
- **WHEN** Google redirige al callback con `error=access_denied`
- **THEN** la conexión vuelve a `desconectada`, no se guarda ningún token y el panel muestra "No se conectó Google Calendar: no se dio el permiso"

### Requirement: Desconectar Google Calendar
`DELETE /api/panel/google-calendar/conexiones/{profesional_id}` SHALL permitirlo a la propia profesional y a `admin`. SHALL revocar el token en Google si se puede, borrar los tokens guardados, dejar la conexión `desconectada` y los eventos del sistema desvinculados sin borrarlos de Google (O14). Ningún turno cambia.

#### Scenario: La profesional se desconecta (Happy Path)
- **GIVEN** la profesional 7 conectada con 3 eventos de turnos futuros sincronizados
- **WHEN** su usuaria pide `DELETE /api/panel/google-calendar/conexiones/7`
- **THEN** recibe 204, la conexión queda `desconectada` sin tokens, los 3 eventos quedan desvinculados en el sistema y siguen en Google, y se audita la desconexión

#### Scenario: Otra odontóloga intenta desconectarla (Error de Negocio)
- **GIVEN** un usuario `odontologo` vinculado a la profesional 8
- **WHEN** pide `DELETE /api/panel/google-calendar/conexiones/7`
- **THEN** recibe 403 y la conexión de la profesional 7 no cambia

#### Scenario: Google no responde al revocar (Caso de Borde)
- **GIVEN** que la revocación en Google falla por red
- **WHEN** se desconecta
- **THEN** igual se borran los tokens locales y la conexión queda `desconectada`; el fallo queda en el log sin el token

### Requirement: Estado de las conexiones según el rol
`GET /api/panel/google-calendar/conexiones` SHALL devolver, por profesional, el estado (`sin_conectar`, `pendiente`, `activa`, `revocada`, `desconectada`), la cuenta conectada, la última sincronización correcta y la cantidad de conflictos abiertos. Recepción y admin SHALL ver todas; una odontóloga SHALL ver solo la suya.

#### Scenario: Recepción ve todas (Happy Path)
- **GIVEN** la profesional 7 `activa` con 1 conflicto abierto y la profesional 8 sin conectar
- **WHEN** recepción pide el listado
- **THEN** recibe ambas filas con su estado, la cuenta de la 7 y `conflictos_abiertos = 1`

#### Scenario: La odontóloga ve solo la suya (Error de Negocio)
- **WHEN** la usuaria de la profesional 7 pide el listado
- **THEN** recibe solo la fila de la profesional 7; sin sesión recibe 401

#### Scenario: Conexión revocada (Caso de Borde)
- **GIVEN** que Google respondió `invalid_grant` al renovar el token de la profesional 7
- **WHEN** se pide el listado
- **THEN** la fila figura `revocada` con la indicación "Volvé a conectar Google Calendar"

### Requirement: Solo los turnos que bloquean agenda tienen evento en Google
Para una profesional con conexión `activa`, cada turno `reservado` o `confirmado` cuyo horario cae en el horizonte de sincronización (desde hoy hasta `GCAL_HORIZONTE_DIAS`, 60 por defecto, O6) SHALL tener un evento en su calendario. Un turno `en_espera` SHALL no tener evento nunca (R8, RN-SN-01).

#### Scenario: La seña se acredita y aparece el evento (Happy Path)
- **GIVEN** la profesional 7 conectada y el turno 501 `en_espera` para mañana a las 10:00
- **WHEN** se acredita la seña (pasa a `reservado`) y corre la sincronización
- **THEN** su Google Calendar tiene un evento de 10:00 a 10:30 (hora de la clínica) vinculado al turno 501

#### Scenario: Pre-reserva sin evento (Error de Negocio)
- **GIVEN** el turno 502 `en_espera` de la profesional 7
- **WHEN** corre la sincronización cualquier cantidad de veces
- **THEN** no existe evento para el turno 502; si vence y queda `cancelado`, tampoco

#### Scenario: Borde del horizonte y alta manual sin seña (Caso de Borde)
- **GIVEN** con horizonte de 60 días, un turno `reservado` del alta manual (sin seña, C-08 O7) a 59 días y otro a 61 días
- **WHEN** corre la sincronización
- **THEN** solo el de 59 días tiene evento; el de 61 días lo recibe cuando entra en el horizonte

### Requirement: Cancelar borra el evento y reprogramar lo mueve
Cuando un turno con evento pasa a `cancelado`, el evento SHALL borrarse de Google; cuando se reprograma, el mismo evento SHALL moverse al horario nuevo. Esto SHALL ocurrir aunque el aviso de la cancelación o reprogramación se pierda (el estado del turno manda).

#### Scenario: Cancelación con 24 h o más (Happy Path)
- **GIVEN** el turno 503 `reservado` con evento sincronizado, cancelado por la paciente con 30 h de anticipación
- **WHEN** corre la sincronización
- **THEN** el evento ya no está en Google y el vínculo queda `borrado`

#### Scenario: Reprogramación con el aviso perdido (Error de Negocio)
- **GIVEN** el turno 504 reprogramado de las 10:00 a las 16:00 y que el aviso al calendario falló
- **WHEN** corre la sincronización
- **THEN** el mismo evento de Google pasa a 16:00 sin crear otro

#### Scenario: Cancelar un turno cuyo evento ya no está en Google (Caso de Borde)
- **GIVEN** el turno 505 con evento que la profesional ya borró en Google, y conflicto `borrado_en_google` abierto
- **WHEN** el turno se cancela y corre la sincronización
- **THEN** el conflicto se cierra solo con resolución `turno_cancelado` (sin usuario) y no se intenta recrear ni borrar nada en Google

### Requirement: Ausente y atendido conservan el evento
Un turno que pasa a `ausente` o `atendido` SHALL conservar su evento en Google sin cambios (O7). Deshacer un `atendido` (vuelve a `reservado`) SHALL no crear un evento nuevo.

#### Scenario: Turno atendido (Happy Path)
- **GIVEN** el turno 506 `confirmado` con evento
- **WHEN** recepción lo marca `atendido` y corre la sincronización
- **THEN** el evento sigue igual en Google

#### Scenario: Ausente no libera el evento (Error de Negocio)
- **GIVEN** el turno 507 `reservado` con evento, marcado `ausente`
- **WHEN** corre la sincronización
- **THEN** el evento no se borra ni se modifica

#### Scenario: Deshacer un atendido (Caso de Borde)
- **GIVEN** el turno 506 `atendido` que un admin vuelve a `reservado` dentro del plazo
- **WHEN** corre la sincronización
- **THEN** sigue habiendo un único evento para el turno 506

### Requirement: El evento no identifica al paciente
El evento que el sistema escribe en Google SHALL llevar como título "Turno · <tratamiento>" y en la descripción el sillón y un enlace al panel, y SHALL no llevar nombre, teléfono, DNI, email ni código de gestión del paciente (O8, Ley 25.326, R19). SHALL marcar el evento como del sistema para reconocerlo en el pull.

#### Scenario: Contenido del evento (Happy Path)
- **GIVEN** el turno 508 de "Paciente Ficticio" (+5491100000000) para "Limpieza" en el Sillón 2
- **WHEN** se crea su evento
- **THEN** el título es "Turno · Limpieza", la descripción menciona "Sillón 2" y el enlace al panel, y ni el nombre ni el teléfono aparecen en ningún campo del evento

#### Scenario: Tratamiento renombrado (Error de Negocio)
- **GIVEN** el turno 508 con evento y el tratamiento renombrado a "Limpieza dental"
- **WHEN** corre la sincronización
- **THEN** el título del evento se actualiza; no se agrega ningún dato del paciente

#### Scenario: Turno interno sin paciente vinculado (Caso de Borde)
- **GIVEN** un turno `reservado` del alta manual sin paciente vinculado ni código de gestión
- **WHEN** se crea su evento
- **THEN** el evento se crea con el mismo formato, sin enlaces de gestión

### Requirement: La sincronización no duplica eventos
Cada turno SHALL tener a lo sumo un evento vigente por conexión. Reintentar un ciclo interrumpido, correr dos workers a la vez o recibir de Google un evento ya creado SHALL no crear un segundo evento.

#### Scenario: Ciclo interrumpido después de crear en Google (Happy Path)
- **GIVEN** que el worker creó el evento del turno 509 en Google y se cayó antes de guardar el vínculo
- **WHEN** corre el ciclo siguiente
- **THEN** reconoce el evento existente y guarda el vínculo sin crear otro

#### Scenario: Dos workers en el mismo ciclo (Error de Negocio)
- **GIVEN** dos workers que procesan la misma conexión a la vez
- **WHEN** ambos intentan crear el evento del turno 510
- **THEN** en Google queda un solo evento para el turno 510

#### Scenario: Recrear después de restaurar (Caso de Borde)
- **GIVEN** el evento del turno 511 borrado en Google y el conflicto resuelto con "Restaurar en Google"
- **WHEN** corre la sincronización
- **THEN** se crea un evento nuevo para el turno 511 y el vínculo anterior queda `borrado` como historial

### Requirement: Los eventos ocupados de Google se traen como franjas ocupadas
Cada ciclo SHALL traer los cambios del calendario conectado de forma incremental. De cada evento ajeno al sistema SHALL guardarse solo inicio, fin, si ocupa (`opaque`) y su estado; nunca título, descripción, lugar ni invitados (O19). Un evento libre (`transparent`), cancelado o rechazado SHALL no ocupar.

#### Scenario: Evento personal ocupado (Happy Path)
- **GIVEN** que la profesional 7 carga en Google "Evento sintético" ocupado mañana de 15:00 a 16:00
- **WHEN** corre la sincronización
- **THEN** el sistema tiene una franja ocupada de 15:00 a 16:00 de la profesional 7, sin el título

#### Scenario: Evento marcado como disponible (Error de Negocio)
- **GIVEN** un evento de Google `transparent` de 11:00 a 12:00 o un evento que la profesional rechazó
- **WHEN** corre la sincronización
- **THEN** no genera franja ocupada

#### Scenario: Evento borrado o movido en Google (Caso de Borde)
- **GIVEN** la franja de 15:00 a 16:00 ya guardada
- **WHEN** la profesional la mueve a 17:00 o la borra en Google y corre la sincronización
- **THEN** la franja pasa a 17:00 o deja de ocupar

### Requirement: Un cambio en Google nunca modifica un turno
Si un evento del sistema se mueve o se borra en Google, el turno SHALL quedar igual y SHALL registrarse un conflicto abierto (`movido_en_google` o `borrado_en_google`) con el horario del sistema y el de Google. Mientras esté abierto, el sistema SHALL no volver a escribir ese evento (RN-GC-02, O9).

#### Scenario: La profesional mueve el evento en Google (Happy Path)
- **GIVEN** el turno 512 `reservado` mañana a las 10:00 con evento sincronizado
- **WHEN** la profesional lo mueve a las 12:00 en Google y corre la sincronización
- **THEN** el turno 512 sigue a las 10:00, hay un conflicto `movido_en_google` que muestra "Sistema: 10:00–10:30 / Google: 12:00–12:30" y el evento de Google sigue a las 12:00

#### Scenario: La profesional borra el evento en Google (Error de Negocio)
- **GIVEN** el turno 513 `confirmado` con evento sincronizado
- **WHEN** lo borra en Google y corre la sincronización
- **THEN** el turno 513 sigue `confirmado` y hay un conflicto `borrado_en_google`; el sistema no recrea el evento solo

#### Scenario: Solo cambia el título en Google (Caso de Borde)
- **GIVEN** el evento del turno 514 con el título editado en Google y el mismo horario
- **WHEN** corre la sincronización
- **THEN** no se registra conflicto ni se reescribe el título hasta que el turno cambie (O9)

### Requirement: Conflicto por superposición con un evento ocupado de Google
Un turno `reservado` o `confirmado` que se superpone con una franja ocupada de Google de la misma profesional SHALL registrar un conflicto abierto `solapa_evento_externo`. Ni el turno ni el evento de Google SHALL cambiar solos.

#### Scenario: Seña acreditada sobre una franja ocupada (Happy Path)
- **GIVEN** el turno 515 `en_espera` a las 15:00 y luego una franja ocupada en Google de 15:00 a 16:00
- **WHEN** se acredita la seña y corre la sincronización
- **THEN** el turno queda `reservado`, se crea su evento y se registra un conflicto `solapa_evento_externo` que muestra ambos horarios

#### Scenario: Pre-reserva superpuesta (Error de Negocio)
- **GIVEN** el turno 516 `en_espera` superpuesto con una franja ocupada
- **WHEN** corre la sincronización
- **THEN** no se registra conflicto (la pre-reserva no bloquea agenda, R8)

#### Scenario: Turnos que solo se tocan en el borde (Caso de Borde)
- **GIVEN** un turno de 14:30 a 15:00 y una franja ocupada de 15:00 a 16:00
- **WHEN** corre la sincronización
- **THEN** no hay conflicto: los intervalos son semiabiertos `[inicio, fin)`

### Requirement: Resolución manual de conflictos con criterio visible
`GET /api/panel/google-calendar/conflictos` SHALL listar los conflictos con tipo, turno, horario del sistema, horario de Google y acciones posibles. `POST .../conflictos/{id}/resolver` SHALL aceptarlo solo de recepción o admin, con una acción válida para el tipo (O11, O12, O18), y SHALL auditarse.

#### Scenario: Restaurar el evento en Google (Happy Path)
- **GIVEN** el conflicto `movido_en_google` del turno 512 abierto
- **WHEN** recepción lo resuelve con `restaurar_en_google`
- **THEN** recibe 200, el conflicto queda resuelto con quién y cuándo, y en el ciclo siguiente el evento vuelve a las 10:00

#### Scenario: Acción inválida o rol sin permiso (Error de Negocio)
- **GIVEN** el conflicto `solapa_evento_externo` del turno 515
- **WHEN** recepción pide `restaurar_en_google`, o la odontóloga pide cualquier acción
- **THEN** recibe 422 `accion_no_valida` o 403, y el conflicto sigue abierto

#### Scenario: Conflicto ya resuelto o desaparecido (Caso de Borde)
- **GIVEN** un conflicto ya resuelto, o uno cuyo turno se canceló entre medio
- **WHEN** se pide resolverlo
- **THEN** recibe 409 `conflicto_cerrado` sin cambios

### Requirement: Desvincular un turno del calendario
La acción `desvincular` SHALL dejar el turno sin evento sincronizado: el sistema no vuelve a crear, mover ni borrar su evento en Google y el turno no cambia. SHALL ser válida para `movido_en_google` y `borrado_en_google`; `revisado` SHALL ser la única acción de `solapa_evento_externo`.

#### Scenario: Desvincular un evento movido (Happy Path)
- **GIVEN** el conflicto `movido_en_google` del turno 512
- **WHEN** recepción lo resuelve con `desvincular`
- **THEN** el evento sigue a las 12:00 en Google, el turno a las 10:00 en el sistema, y ningún ciclo posterior lo toca

#### Scenario: Marcar revisada una superposición (Error de Negocio)
- **GIVEN** el conflicto `solapa_evento_externo` del turno 515
- **WHEN** recepción lo resuelve con `revisado`
- **THEN** el conflicto se cierra; el turno y la franja de Google siguen iguales

#### Scenario: La superposición vuelve a ocurrir (Caso de Borde)
- **GIVEN** la superposición del turno 515 marcada `revisado`
- **WHEN** la franja de Google se mueve a otro horario que también se superpone con el turno 515
- **THEN** se registra un conflicto nuevo

### Requirement: Errores de Google sin perder cambios
Un error transitorio de Google (red, 429, 5xx) SHALL dejar pendientes los cambios de esa conexión y reintentarlos con espera creciente (1, 5, 15 y 60 minutos como máximo). Un `syncToken` vencido (410) SHALL provocar una lectura completa del horizonte sin duplicar franjas ni eventos (O13).

#### Scenario: Google vuelve después de un corte (Happy Path)
- **GIVEN** que Google responde 503 durante dos ciclos mientras se acredita el turno 517
- **WHEN** Google vuelve
- **THEN** el evento del turno 517 se crea en el ciclo siguiente a la espera, sin intervención

#### Scenario: Cuota excedida (Error de Negocio)
- **GIVEN** que Google responde 429 para la profesional 7
- **WHEN** corre la sincronización
- **THEN** la conexión de la profesional 7 espera antes de reintentar, las demás conexiones se sincronizan normalmente y el log registra el error sin datos personales ni tokens

#### Scenario: syncToken vencido (Caso de Borde)
- **GIVEN** que Google responde 410 al pull incremental de la profesional 7
- **WHEN** corre la sincronización
- **THEN** se relee el horizonte completo, se obtiene un `syncToken` nuevo y las franjas quedan iguales a Google, sin duplicados

### Requirement: Token revocado deja de sincronizar sin tocar turnos
Si Google rechaza la renovación del token (`invalid_grant`), la conexión SHALL pasar a `revocada`, el sistema SHALL dejar de sincronizarla y SHALL avisarlo en el panel. Ningún turno SHALL cambiar y la reserva pública SHALL seguir funcionando con las franjas ya conocidas.

#### Scenario: La profesional quitó el acceso en su cuenta de Google (Happy Path)
- **GIVEN** la conexión `activa` de la profesional 7 cuyo acceso se quitó desde la cuenta de Google
- **WHEN** corre la sincronización
- **THEN** la conexión queda `revocada`, se audita el cambio y el panel muestra "Volvé a conectar Google Calendar"

#### Scenario: Turnos nuevos con la conexión revocada (Error de Negocio)
- **GIVEN** la conexión `revocada` y un turno nuevo `reservado`
- **WHEN** corren varios ciclos
- **THEN** no se llama a Google para esa conexión y el turno queda pendiente de evento

#### Scenario: Reconectar (Caso de Borde)
- **GIVEN** la conexión `revocada` con turnos pendientes de evento
- **WHEN** la profesional vuelve a conectar la misma cuenta
- **THEN** el ciclo siguiente crea los eventos pendientes sin duplicar los que ya existían en Google

### Requirement: La API nunca llama a Google
Cancelar, reprogramar, acreditar, dar de alta o marcar un turno SHALL responder sin esperar a Google ni depender de que esté disponible. El aviso de cancelación o reprogramación SHALL solo marcar el evento como pendiente; el trabajo periódico SHALL hacer las llamadas (R16).

#### Scenario: Cancelar con Google caído (Happy Path)
- **GIVEN** Google sin respuesta
- **WHEN** la paciente cancela su turno con 30 h de anticipación
- **THEN** la cancelación responde 200 en el tiempo habitual y el evento se borra cuando Google vuelve

#### Scenario: Falla el aviso al calendario (Error de Negocio)
- **GIVEN** que marcar el evento como pendiente falla después del commit
- **WHEN** se reprograma un turno
- **THEN** la reprogramación igual responde 200 y la reconciliación del ciclo siguiente mueve el evento

#### Scenario: Profesional sin conexión (Caso de Borde)
- **GIVEN** la profesional 8 sin Google Calendar conectado
- **WHEN** se cancelan o reservan sus turnos
- **THEN** nada se encola ni se intenta para ella

### Requirement: Sección "Google Calendar" del panel a 360 px
El panel SHALL tener una sección "Google Calendar" que funcione a 360 px (R3): estado de conexión, botón "Conectar Google Calendar" o "Desconectar" para la odontóloga, y la lista de conflictos con el horario del sistema, el de Google y las acciones para recepción y admin. La odontóloga SHALL ver sus conflictos sin acciones.

#### Scenario: Recepción resuelve un conflicto desde el celular (Happy Path)
- **GIVEN** recepción en un viewport de 360 px con un conflicto `movido_en_google` abierto
- **WHEN** abre la sección y toca "Restaurar en Google"
- **THEN** ve el conflicto con "Sistema: 10:00–10:30 / Google: 12:00–12:30", sin desplazamiento horizontal, y tras confirmar desaparece de la lista de abiertos

#### Scenario: La conexión falla al volver de Google (Error de Negocio)
- **GIVEN** que el callback volvió con `error_autorizacion`
- **WHEN** la odontóloga ve la sección
- **THEN** lee "No se pudo conectar Google Calendar. Volvé a intentarlo" y el botón "Conectar Google Calendar" sigue disponible

#### Scenario: Sin conflictos (Caso de Borde)
- **GIVEN** la profesional 7 conectada sin conflictos abiertos
- **WHEN** se abre la sección
- **THEN** se lee "No hay conflictos con Google Calendar" y la última sincronización correcta
