# Spec Delta: turnos/gestion-panel

## Purpose
Permite que recepción y admin operen la agenda desde el panel: cargar turnos manuales con la misma garantía anti-solape que la reserva pública (R5, RN-TU-03) y registrar qué pasó con cada turno, respetando las reglas de la seña (R9, RN-SN-02, RN-SN-04).

Las referencias `(Ox)` remiten a las decisiones resueltas en `design.md`.

## ADDED Requirements

### Requirement: Alta manual de un turno sin solapes
`POST /api/panel/turnos` SHALL crear un turno con profesional, tratamiento, inicio, nombre y teléfono, y sillón opcional. El turno SHALL guardar `fin = inicio + duración vigente del tratamiento` y origen `manual` (O10). Un solape por profesional o por sillón SHALL responder 409 con el motivo y horarios alternativos, sin crear nada; la base de datos SHALL ser la garantía final (R5). Si no se indica sillón, el sistema SHALL asignar uno libre.

#### Scenario: Alta en un horario libre (Happy Path)
- **GIVEN** que la "Dra. Ana Ficticia" tiene libre el 2026-11-17 a las 11:00 y "Limpieza dental" dura 45 minutos
- **WHEN** recepción crea el turno para "Carlos Sintético" (+5491144445555) a las 11:00 sin indicar sillón
- **THEN** recibe 201 con el turno de 11:00 a 11:45, estado `reservado`, origen `manual` y un sillón asignado, y el turno aparece en la agenda

#### Scenario: Horario ocupado (Error de Negocio)
- **GIVEN** un turno `reservado` de esa profesional de 11:00 a 11:45
- **WHEN** recepción intenta crear otro a las 11:15
- **THEN** recibe 409 con `motivo: "profesional"` y alternativas libres, y no se crea ningún turno

#### Scenario: Dos altas simultáneas sobre el mismo horario (Caso de Borde)
- **GIVEN** un horario libre
- **WHEN** llegan a la vez dos altas manuales para esa profesional y ese horario
- **THEN** exactamente una responde 201 y la otra 409, nunca 500

### Requirement: El alta manual respeta la disponibilidad vigente
El turno manual SHALL entrar completo en una franja vigente de la profesional (RN-TU-07) y su inicio SHALL ser futuro (O9). Si no, SHALL responder 422 con el motivo.

#### Scenario: Dentro de la franja (Happy Path)
- **GIVEN** una franja de 09:00 a 13:00 y un tratamiento de 30 minutos
- **WHEN** se crea un turno a las 12:00
- **THEN** responde 201

#### Scenario: Fuera de la franja o en el pasado (Error de Negocio)
- **WHEN** se crea un turno a las 20:00 o con un inicio ya pasado
- **THEN** responde 422 con `fuera_de_disponibilidad` o error de validación, y no se crea nada

#### Scenario: Termina justo al cierre de la franja (Caso de Borde)
- **GIVEN** una franja que cierra a las 13:00 y un tratamiento de 30 minutos
- **WHEN** se crea un turno a las 12:30 y otro a las 12:45
- **THEN** el primero responde 201 y el segundo 422

### Requirement: Datos de la o el paciente en el alta manual
El alta manual SHALL exigir nombre y teléfono en formato E.164 y SHALL guardarlos como contacto del turno, sin crear un registro de `Paciente` (O8). Un campo `fin` enviado por el cliente SHALL rechazarse (RN-TU-04). El alta SHALL generar un código de gestión y devolverlo solo en la respuesta de creación (O11).

#### Scenario: Datos completos (Happy Path)
- **WHEN** recepción envía nombre "Lucía Ejemplo" y teléfono +5491155556666
- **THEN** el turno se crea con esos datos y la respuesta incluye el código de gestión

#### Scenario: Teléfono inválido o fin enviado (Error de Negocio)
- **WHEN** se envía el teléfono "11 5555 6666" o un campo `fin`
- **THEN** responde 422 y no se crea nada

#### Scenario: Gestión por la o el paciente de un turno manual (Caso de Borde)
- **GIVEN** un turno manual con código de gestión, sin seña, a 48 horas
- **WHEN** se cancela con ese código por `POST /api/public/gestion/cancelar`
- **THEN** el turno queda `cancelado`, sin ningún pago

### Requirement: El turno manual nace sin seña
El turno manual SHALL nacer `reservado`, bloqueando la agenda, y sin ningún `PagoSena` (O7). La agenda SHALL indicar que no tiene seña.

#### Scenario: Sin movimiento de pago (Happy Path)
- **WHEN** recepción crea un turno manual de un tratamiento con precio "15000.00"
- **THEN** el turno queda `reservado` y no existe ningún pago para ese turno

#### Scenario: El alta manual no crea una pre-reserva (Error de Negocio)
- **WHEN** se envía un campo `estado: "en_espera"` en el alta manual
- **THEN** responde 422 y no se crea nada

#### Scenario: Ocupa el horario de una pre-reserva que después se paga (Caso de Borde)
- **GIVEN** un turno `en_espera` a las 10:00, y que recepción creó un turno manual a las 10:00 con la misma profesional
- **WHEN** llega la aprobación del pago de la pre-reserva
- **THEN** el pago queda `a_reembolsar`, la pre-reserva no pasa a `reservado` (RN-SN-05) y el turno manual no cambia

### Requirement: Solo recepción y admin operan la agenda
Las operaciones de escritura bajo `/api/panel/turnos` SHALL requerir rol `recepcion` o `admin` (O5). Un usuario con rol `odontologo` SHALL recibir 403 y sin token SHALL recibir 401, sin que cambie ningún dato.

#### Scenario: Recepción opera (Happy Path)
- **WHEN** un usuario con rol `recepcion` marca un turno ya iniciado como `atendido`
- **THEN** responde 200

#### Scenario: La odontóloga intenta operar (Error de Negocio)
- **WHEN** un usuario con rol `odontologo` intenta crear un turno o marcar uno propio como `ausente`
- **THEN** responde 403 y no cambia nada

#### Scenario: Sin sesión o con un token de refresh (Caso de Borde)
- **WHEN** se llama sin token o con un token de tipo refresh
- **THEN** responde 401 y no cambia nada

### Requirement: Marcar ausente retiene la seña
`POST /api/panel/turnos/{id}/ausente` SHALL aceptarse solo para un turno `reservado` o `confirmado` y desde el inicio del turno más la tolerancia configurada, 10 minutos por defecto (RN-TU-12, O14). El turno SHALL pasar a `ausente` y una seña acreditada SHALL quedar `no_reembolsado`, sin ningún reembolso (R9, RN-SN-02).

#### Scenario: Ausente con seña acreditada (Happy Path)
- **GIVEN** un turno `confirmado` que empezó hace 15 minutos, con seña acreditada de "3000.00"
- **WHEN** recepción lo marca ausente
- **THEN** responde 200, el turno queda `ausente` y el pago `no_reembolsado` por "3000.00"

#### Scenario: Antes de la tolerancia o en un estado inválido (Error de Negocio)
- **GIVEN** un turno `reservado` que empezó hace 9 minutos y 59 segundos, y otro `en_espera`
- **WHEN** se marca ausente cada uno
- **THEN** el primero responde 409 `marcado_no_habilitado` con el instante desde el que se puede, el segundo 409 `transicion_invalida`, y ningún turno ni pago cambia

#### Scenario: Exactamente al cumplirse la tolerancia y sin seña (Caso de Borde)
- **GIVEN** un turno manual `reservado`, sin seña, y el servidor procesa el pedido exactamente 10 minutos después del inicio
- **WHEN** se lo marca ausente
- **THEN** se acepta, el turno queda `ausente` y no se crea ningún pago

### Requirement: La tolerancia del ausente es configurable
La tolerancia para marcar ausente SHALL leerse de la configuración `AUSENTE_TOLERANCIA_MINUTOS`, con valor 10 por defecto, y SHALL ser un entero mayor o igual a 0 (RN-TU-12).

#### Scenario: Valor por defecto (Happy Path)
- **GIVEN** que `AUSENTE_TOLERANCIA_MINUTOS` no está definida
- **WHEN** se marca ausente un turno a los 10 minutos de su inicio
- **THEN** se acepta

#### Scenario: Valor inválido (Error de Negocio)
- **GIVEN** que `AUSENTE_TOLERANCIA_MINUTOS` vale -1 o un texto
- **WHEN** arranca el backend
- **THEN** no inicia y el error nombra la variable

#### Scenario: Tolerancia cero (Caso de Borde)
- **GIVEN** que `AUSENTE_TOLERANCIA_MINUTOS` vale 0
- **WHEN** se marca ausente un turno exactamente a la hora de inicio
- **THEN** se acepta

### Requirement: Marcar atendido
`POST /api/panel/turnos/{id}/atendido` SHALL aceptarse solo para un turno `reservado` o `confirmado` y desde las 00:00 del día local de la clínica en que empieza el turno, sin importar la hora (RN-TU-12, O14). El turno SHALL pasar a `atendido`, la seña SHALL quedar sin cambios y el turno SHALL seguir ocupando su horario hasta `fin` (O19).

#### Scenario: Atendido antes de la hora del turno, el mismo día (Happy Path)
- **GIVEN** un turno `reservado` para hoy a las 11:00, con seña acreditada, y son las 09:30 de la clínica
- **WHEN** recepción lo marca atendido
- **THEN** responde 200, el turno queda `atendido`, el pago sigue `acreditado` y el horario de las 11:00 sigue sin figurar como libre

#### Scenario: Día anterior o estado final (Error de Negocio)
- **GIVEN** un turno `reservado` que empieza el 2026-11-17 a las 09:00 (-03:00) y son las 23:59:59 del 2026-11-16, y otro turno `ausente`
- **WHEN** se marca atendido cada uno
- **THEN** el primero responde 409 `marcado_no_habilitado`, el segundo 409 `transicion_invalida`, y ninguno cambia

#### Scenario: Primer instante del día local e inexistente (Caso de Borde)
- **GIVEN** un turno `reservado` del 2026-11-17 a las 09:00 (-03:00) y el pedido llega a las 00:00:00 del 2026-11-17 (-03:00), que en UTC es 03:00; y un id de turno que no existe
- **WHEN** se marca atendido cada uno
- **THEN** el primero se acepta, y el segundo responde 404

### Requirement: Cancelar desde el panel respeta la ventana de 24 horas
`POST /api/panel/turnos/{id}/cancelar` SHALL aplicar las mismas reglas que la cancelación de la o el paciente: `reservado` o `confirmado` solo con 24 horas o más (RN-TU-01), con la seña acreditada pasando a `a_reembolsar` (RN-SN-04); `en_espera` en cualquier momento, sin cobro (O12).

#### Scenario: Cancelación con 48 horas (Happy Path)
- **GIVEN** un turno `reservado` a 48 horas con seña acreditada
- **WHEN** recepción lo cancela
- **THEN** responde 200, el turno queda `cancelado`, el pago `a_reembolsar` y el horario queda libre

#### Scenario: Con menos de 24 horas (Error de Negocio)
- **GIVEN** un turno `confirmado` a 23 horas y 59 minutos
- **WHEN** recepción intenta cancelarlo
- **THEN** responde 409 `fuera_de_plazo` con el límite en hora de la clínica, y nada cambia

#### Scenario: Exactamente 24 horas antes (Caso de Borde)
- **GIVEN** un turno `reservado` que empieza exactamente en 24 horas
- **WHEN** recepción lo cancela
- **THEN** se acepta y la seña acreditada queda `a_reembolsar`

### Requirement: Auditoría de las acciones del panel
Cada alta, marcado o cancelación aceptada SHALL dejar, en la misma transacción, un registro con el usuario, la acción, el turno, el estado anterior y nuevo, y un origen propio: `alta_manual_panel`, `marcado_ausente_panel`, `marcado_atendido_panel` o `cancelacion_panel` (RN-GL-01). El registro no SHALL contener nombre ni teléfono (R19).

#### Scenario: Alta auditada (Happy Path)
- **WHEN** recepción crea un turno manual
- **THEN** existe un registro con su `usuario_id` y origen `alta_manual_panel`

#### Scenario: Acción rechazada (Error de Negocio)
- **WHEN** una acción se rechaza por solape, plazo o transición inválida
- **THEN** no queda ningún registro nuevo de esa acción

#### Scenario: Sin datos personales (Caso de Borde)
- **GIVEN** un alta manual para "Carlos Sintético" (+5491144445555)
- **WHEN** se inspecciona el registro de auditoría
- **THEN** no contiene ni el nombre ni el teléfono

### Requirement: Eventos de las acciones del panel
Una cancelación desde el panel de un turno `reservado` o `confirmado` SHALL publicar `turno_cancelado` por el puerto de notificaciones después del commit, sin datos personales. Marcar ausente o atendido no SHALL publicar eventos (O15). Una falla de publicación no SHALL revertir la operación.

#### Scenario: Cancelación con evento (Happy Path)
- **WHEN** recepción cancela un turno `reservado` a 48 horas
- **THEN** se publica un `turno_cancelado` con el id del turno, la profesional y el horario anterior

#### Scenario: Cancelación rechazada o pre-reserva (Error de Negocio)
- **WHEN** una cancelación se rechaza, o se cancela un turno `en_espera`
- **THEN** no se publica ningún evento

#### Scenario: Publicador caído (Caso de Borde)
- **GIVEN** un publicador que lanza un error
- **WHEN** recepción cancela un turno `reservado` a 48 horas
- **THEN** responde 200 y el turno queda `cancelado`

### Requirement: Pantallas de alta manual y acciones sobre el turno
El panel SHALL ofrecer a recepción y admin el formulario de alta manual y las acciones que el servidor informa para cada turno. Marcar ausente y cancelar SHALL pedir confirmación indicando qué pasa con la seña. A un usuario `odontologo` no SHALL mostrarle acciones de escritura.

#### Scenario: Alta desde la pantalla (Happy Path)
- **GIVEN** recepción con sesión iniciada
- **WHEN** toca "Nuevo turno", completa los datos, elige un horario libre y confirma
- **THEN** ve el turno en la agenda y el código de gestión una única vez, para compartirlo

#### Scenario: Horario tomado mientras se completa (Error de Negocio)
- **GIVEN** que otro turno ocupó el horario elegido
- **WHEN** recepción confirma el alta
- **THEN** ve "Ese horario ya no está disponible" con alternativas, y puede elegir una sin volver a cargar los datos

#### Scenario: Confirmación del ausente (Caso de Borde)
- **GIVEN** un turno iniciado con seña acreditada de "3000.00"
- **WHEN** recepción toca "Marcar ausente"
- **THEN** el diálogo avisa que la seña de $ 3.000,00 no se devuelve y que el cambio no se puede deshacer, y nada cambia hasta confirmar
