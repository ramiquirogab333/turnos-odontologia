# turnos/agenda-panel Specification

## Purpose
Permite que el personal de la clínica vea la agenda por día o por semana (US-005, Flujo 4): la odontóloga u odontólogo la suya, recepción y admin todas. Distingue las pre-reservas que todavía no ocupan el horario (R8) y no muestra turnos superpuestos (RN-TU-03).

Las referencias `(Ox)` remiten a las decisiones resueltas en `design.md`.

## Requirements

### Requirement: Consulta de la agenda por día o por semana
`GET /api/panel/agenda` SHALL recibir `vista` (`dia` o `semana`) y `fecha` (`YYYY-MM-DD`) y SHALL devolver los turnos cuyo inicio cae en ese período, medido en la hora de la clínica (America/Argentina/Buenos_Aires), ordenados por inicio. La semana SHALL ir de lunes a domingo. Los turnos `cancelado` no SHALL devolverse (O16).

#### Scenario: Agenda del día (Happy Path)
- **GIVEN** que la "Dra. Ana Ficticia" tiene el 2026-11-17 un turno `reservado` de "Carlos Sintético" a las 09:00 y uno `confirmado` de "Lucía Ejemplo" a las 09:30 (-03:00)
- **WHEN** recepción consulta `GET /api/panel/agenda?vista=dia&fecha=2026-11-17`
- **THEN** recibe 200 con los dos turnos en ese orden

#### Scenario: Parámetros inválidos (Error de Negocio)
- **WHEN** se consulta con `vista=mes` o con `fecha=17-11-2026`
- **THEN** el sistema responde 422 y no devuelve turnos

#### Scenario: Límite de la semana en hora de la clínica (Caso de Borde)
- **GIVEN** un turno que empieza el domingo 2026-11-22 a las 23:30 (-03:00), que en UTC ya es lunes, y otro que empieza el lunes 2026-11-23 a las 00:00 (-03:00)
- **WHEN** se consulta `vista=semana&fecha=2026-11-18`
- **THEN** el primero está en la respuesta y el segundo no

### Requirement: Contenido de cada turno de la agenda
Cada turno SHALL traer inicio y fin con el offset de la clínica, estado, bloqueo, origen, profesional, sillón, tratamiento, nombre del paciente, estado de la seña y sus acciones posibles para quien consulta, calculadas por el servidor (RN-TU-12, O15). Para `odontologo` la única acción SHALL ser `atendido`. Para recepción y admin, un turno `atendido` dentro del plazo de corrección SHALL traer `deshacer_atendido` (C-12 O7, O8).

#### Scenario: Turno con seña acreditada (Happy Path)
- **GIVEN** un turno `reservado` de "Carlos Sintético" con seña acreditada de "3000.00" que empieza el 2026-11-17 a las 09:00 (-03:00)
- **WHEN** recepción consulta el 2026-11-16 a las 20:00, con menos de 24 horas de anticipación
- **THEN** el turno trae inicio "2026-11-17T09:00:00-03:00", seña `acreditado` por "3000.00" y ninguna acción disponible

#### Scenario: Un rol sin permisos de escritura (Error de Negocio)
- **GIVEN** un turno `reservado` de la odontóloga que consulta, que empezó hace 20 minutos, y otro suyo `reservado` que empieza en 48 horas
- **WHEN** consulta la agenda
- **THEN** el primero trae solo la acción `atendido` (recepción vería `atendido` y `ausente`) y el segundo la lista vacía (recepción vería `cancelar`); las opciones del panel traen `puede_escribir` en `false`

#### Scenario: Acciones según el momento en un turno manual sin seña (Caso de Borde)
- **GIVEN** un turno manual `reservado`, sin seña, que empieza a las 09:00 con tolerancia de ausente de 10 minutos
- **WHEN** recepción consulta a las 08:00, a las 09:09:59 y a las 09:10:00 del mismo día
- **THEN** el turno trae `sena: null` y origen `manual`; las acciones son `atendido` en las dos primeras consultas, y `atendido` y `ausente` en la tercera

#### Scenario: Acciones del rol odontologo y opciones del panel (Caso de Borde)
- **GIVEN** un usuario `odontologo` sin otro rol más amplio y un turno suyo `reservado` ya iniciado
- **WHEN** consulta la agenda
- **THEN** la única acción posible es `atendido`, en las mismas condiciones que para recepción, y nunca `ausente` ni `cancelar`
- **AND** el indicador `puede_escribir` de las opciones del panel sigue en `false` (no da altas manuales)

#### Scenario: Acción de corrección en un turno atendido (Caso de Borde)
- **GIVEN** un turno `atendido` que empezó hace 2 días, otro `atendido` que empezó hace 8 días y un turno `ausente` de ayer
- **WHEN** recepción consulta la agenda de cada día, y la odontóloga dueña de esos turnos también
- **THEN** recepción recibe `deshacer_atendido` solo en el primero y ninguna acción en los otros dos; la odontóloga no recibe ninguna acción en ninguno

### Requirement: Aislamiento de la agenda por rol
La agenda SHALL requerir un token de acceso válido. Un usuario con rol `odontologo` SHALL ver solamente los turnos de la profesional asociada a su usuario. Un usuario con rol `recepcion` o `admin` SHALL ver todas las agendas. Si una persona tiene más de un rol, SHALL aplicar el permiso más amplio.

#### Scenario: La odontóloga ve solo su agenda (Happy Path)
- **GIVEN** que `dra.ficticia@turnos.test` tiene rol `odontologo` y está asociada a la "Dra. Ana Ficticia", y que el "Dr. Bruno Ejemplo" también tiene turnos ese día
- **WHEN** consulta la agenda sin indicar profesional
- **THEN** recibe solo los turnos de la "Dra. Ana Ficticia"

#### Scenario: Pedir la agenda de otra profesional o no tener sesión (Error de Negocio)
- **WHEN** esa misma usuaria consulta con `profesional_id` del "Dr. Bruno Ejemplo", o alguien consulta sin token
- **THEN** recibe 403 en el primer caso y 401 en el segundo, y en ninguno se devuelven turnos

#### Scenario: Odontólogo sin profesional asociado (Caso de Borde)
- **GIVEN** un usuario con rol `odontologo` y sin profesional asociado
- **WHEN** consulta la agenda
- **THEN** recibe 403 con motivo `sin_profesional_asociado` y un mensaje que le indica pedir la asociación a la clínica

### Requirement: La agenda distingue las pre-reservas que no ocupan horario
Un turno `en_espera` vigente SHALL devolverse con `bloquea_agenda: false` y no SHALL contarse como ocupación (R8, RN-SN-01). Los turnos `reservado`, `confirmado` y `atendido` SHALL devolverse con `bloquea_agenda: true`, porque `atendido` ocupa el horario hasta su `fin` (O19). Un turno `en_espera` con el vencimiento ya cumplido, que el barrido todavía no canceló, no SHALL devolverse.

#### Scenario: Pre-reserva vigente (Happy Path)
- **GIVEN** que "Sofía Muestra" tiene un turno `en_espera` el 2026-11-17 a las 10:00 con vencimiento futuro
- **WHEN** recepción consulta ese día
- **THEN** el turno aparece con `bloquea_agenda: false` y estado de seña pendiente

#### Scenario: La pre-reserva no impide ocupar el horario (Error de Negocio)
- **GIVEN** ese mismo turno `en_espera` a las 10:00 y ningún otro turno a esa hora
- **WHEN** recepción crea un turno manual a las 10:00 con la misma profesional
- **THEN** el alta se acepta porque la pre-reserva no ocupaba el horario, y la agenda devuelve el turno nuevo con `bloquea_agenda: true` y la pre-reserva con `bloquea_agenda: false`

#### Scenario: Pre-reserva vencida sin barrer (Caso de Borde)
- **GIVEN** un turno `en_espera` cuyo vencimiento fue hace un segundo y que el barrido todavía no canceló
- **WHEN** se consulta la agenda
- **THEN** ese turno no aparece

### Requirement: Sin turnos superpuestos visibles
Entre los turnos con `bloquea_agenda: true` de una misma profesional o de un mismo sillón no SHALL existir dos que se superpongan (RN-TU-03, CA-2 de US-005). La pantalla SHALL mostrar las pre-reservas fuera de la secuencia de turnos que ocupan horario (O16).

#### Scenario: Secuencia sin solapes (Happy Path)
- **GIVEN** una agenda con varios turnos bloqueantes el mismo día
- **WHEN** se la consulta
- **THEN** para cada par de turnos bloqueantes de la misma profesional o del mismo sillón, uno termina antes o justo cuando empieza el otro

#### Scenario: La base rechaza un solape (Error de Negocio)
- **GIVEN** un turno `reservado` de 10:00 a 10:30 de una profesional
- **WHEN** se intenta guardar directamente en la base otro turno bloqueante de esa profesional de 10:15 a 10:45
- **THEN** PostgreSQL lo rechaza por violación de exclusión (23P01) y el turno no aparece en la agenda

#### Scenario: Turnos contiguos (Caso de Borde)
- **GIVEN** un turno bloqueante de 10:00 a 10:30 y otro de 10:30 a 11:00 de la misma profesional
- **WHEN** se consulta la agenda
- **THEN** aparecen los dos y no se consideran superpuestos

### Requirement: Filtros de la agenda
La agenda SHALL aceptar `profesional_id` y `sillon_id` opcionales, combinables. `GET /api/panel/agenda/opciones` SHALL devolver los profesionales que quien consulta puede ver, los sillones activos y los tratamientos. Un filtro por un id inexistente SHALL responder 422.

#### Scenario: Filtro por sillón (Happy Path)
- **GIVEN** turnos del mismo día en "Sillón 1" y "Sillón 2"
- **WHEN** recepción filtra por "Sillón 2"
- **THEN** recibe solo los turnos de "Sillón 2"

#### Scenario: Sillón inexistente (Error de Negocio)
- **WHEN** se filtra por un `sillon_id` que no existe
- **THEN** el sistema responde 422 sin turnos

#### Scenario: Combinación sin resultados (Caso de Borde)
- **GIVEN** que la "Dra. Ana Ficticia" no tiene turnos en "Sillón 2" ese día
- **WHEN** se combinan los dos filtros
- **THEN** el sistema responde 200 con la lista vacía

### Requirement: Datos de contacto según el rol
El teléfono de la o el paciente SHALL devolverse solo a `recepcion` y `admin`. Para `odontologo` SHALL ser `null` (O6). La respuesta de la agenda no SHALL incluir nunca el código de gestión.

#### Scenario: Recepción ve el teléfono (Happy Path)
- **GIVEN** un turno de "Carlos Sintético" con teléfono +5491144445555
- **WHEN** recepción consulta la agenda
- **THEN** el turno trae el teléfono

#### Scenario: La odontóloga no recibe el teléfono (Error de Negocio)
- **WHEN** la odontóloga asociada a ese turno consulta la agenda
- **THEN** el turno trae el nombre "Carlos Sintético" y el teléfono en `null`

#### Scenario: Turno sin datos de contacto (Caso de Borde)
- **GIVEN** un turno creado antes de este change, sin nombre ni teléfono de contacto
- **WHEN** se consulta la agenda
- **THEN** el turno aparece con el nombre en `null` y la pantalla muestra "Sin datos del paciente"

### Requirement: Pantalla de agenda día y semana
El panel SHALL mostrar la agenda en vista día y semana con navegación de fecha y filtros, sin scroll horizontal de la página a 360 px y con objetivos táctiles de al menos 48 px. El estado de cada turno SHALL leerse como texto, sin depender solo del color. Las horas SHALL mostrarse siempre en la hora de la clínica. La agenda y sus opciones SHALL pedirse en paralelo (R2).

#### Scenario: Vista día a 360 px (Happy Path)
- **GIVEN** recepción con sesión iniciada en un dispositivo de 360 px
- **WHEN** abre el panel
- **THEN** ve la lista del día con hora, paciente, tratamiento, sillón y estado, y las pre-reservas aparte con estilo atenuado y el texto "No ocupan horario"

#### Scenario: Falla al cargar la agenda (Error de Negocio)
- **GIVEN** que la API responde un error al pedir la agenda
- **WHEN** se abre el panel
- **THEN** la pantalla explica que no se pudo cargar la agenda y ofrece reintentar, sin mostrar una agenda vacía como si no hubiera turnos

#### Scenario: Navegador en otra zona horaria (Caso de Borde)
- **GIVEN** un navegador configurado en Asia/Tokyo y un turno a las 09:00 de la clínica
- **WHEN** se abre la agenda de ese día
- **THEN** el turno se muestra a las 09:00 y dentro de ese día
