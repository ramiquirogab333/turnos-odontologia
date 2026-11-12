# Spec Delta: notificaciones/recordatorios-whatsapp

## Purpose

Recordar cada turno que bloquea agenda por WhatsApp en modo manual v1 (links `wa.me/` armados por el sistema y abiertos por recepción, sin API paga), registrar el ciclo de cada recordatorio y mantenerlo coherente cuando el turno se cancela, se reprograma o se confirma (US-004, Flujo 3, RN-WA-01..03).

## ADDED Requirements

### Requirement: Solo los turnos reservados reciben recordatorio
Un trabajo periódico SHALL generar un recordatorio `pendiente`, canal `whatsapp`, para cada turno `reservado` cuyo inicio caiga dentro de la anticipación configurada (`REMINDER_LEAD_TIME`, 48 h por defecto). Un turno `en_espera` no SHALL recibir recordatorio (R8, RN-WA-03), tampoco uno `confirmado`, `cancelado`, `ausente` o `atendido`. El alta manual `reservado` sin seña SHALL recibirlo (RN-WA-01).

#### Scenario: Turno reservado dentro de la anticipación (Happy Path)
- **GIVEN** que el turno 101 de "Carlos Sintético" está `reservado`, empieza en 30 horas y la anticipación es 48 horas
- **WHEN** corre el trabajo de recordatorios
- **THEN** existe exactamente un recordatorio del turno 101 en estado `pendiente`, canal `whatsapp`, con el horario del turno registrado

#### Scenario: Pre-reserva en espera (Error de Negocio)
- **GIVEN** que el turno 102 está `en_espera` con la seña pendiente y empieza en 30 horas
- **WHEN** corre el trabajo de recordatorios
- **THEN** el turno 102 no tiene ningún recordatorio, y si después su seña se acredita y queda `reservado`, el siguiente ciclo le genera uno

#### Scenario: Turno justo en el límite de la anticipación (Caso de Borde)
- **GIVEN** que el turno 103 está `reservado` y empieza exactamente 48 horas después del ciclo, y el turno 104 empieza 48 horas y 1 minuto después
- **WHEN** corre el trabajo de recordatorios
- **THEN** el turno 103 tiene un recordatorio `pendiente` y el turno 104 todavía no tiene ninguno

### Requirement: Un solo recordatorio vigente por horario del turno
El sistema SHALL mantener como máximo un recordatorio no anulado por turno y horario de inicio, aunque el trabajo corra varias veces o en más de un worker a la vez. Volver a correr el trabajo no SHALL duplicar recordatorios ni cambiar los existentes.

#### Scenario: Ciclos repetidos (Happy Path)
- **GIVEN** que el turno 105 ya tiene un recordatorio `enviado` para su horario
- **WHEN** el trabajo corre otras tres veces
- **THEN** el turno 105 sigue con un solo recordatorio, que sigue `enviado`

#### Scenario: Inserción duplicada rechazada por la base (Error de Negocio)
- **GIVEN** que existe un recordatorio `pendiente` del turno 106 para las 10:00
- **WHEN** se intenta guardar otro recordatorio no anulado del turno 106 para las 10:00
- **THEN** la base lo rechaza y queda un solo recordatorio

#### Scenario: Dos workers en el mismo instante (Caso de Borde)
- **GIVEN** que dos workers ejecutan el trabajo de recordatorios en el mismo segundo sobre el turno 107 `reservado` sin recordatorio
- **WHEN** ambos terminan
- **THEN** el turno 107 tiene exactamente un recordatorio y ningún worker termina con error no controlado

### Requirement: Turnos reservados tarde también reciben recordatorio
Un turno `reservado` cuyo inicio ya está dentro de la anticipación al reservarse SHALL recibir su recordatorio en el siguiente ciclo, siempre que no haya empezado (RN-WA-01). Cuando el turno empieza, todo recordatorio `pendiente` o `fallido` suyo SHALL pasar a `anulado` con motivo `turno_iniciado`.

#### Scenario: Reserva para mañana (Happy Path)
- **GIVEN** que hoy a las 09:00 se acredita la seña del turno 108, que empieza mañana a las 11:00
- **WHEN** corre el siguiente ciclo
- **THEN** el turno 108 tiene un recordatorio `pendiente`

#### Scenario: Turno que ya empezó sin recordar (Error de Negocio)
- **GIVEN** que el turno 109 `reservado` empezó hace 5 minutos y nunca tuvo recordatorio
- **WHEN** corre el trabajo
- **THEN** no se genera ningún recordatorio para el turno 109

#### Scenario: Recordatorio pendiente al empezar el turno (Caso de Borde)
- **GIVEN** que el turno 110 tiene un recordatorio `pendiente` y su inicio fue hace 1 segundo
- **WHEN** corre el trabajo
- **THEN** el recordatorio queda `anulado` con motivo `turno_iniciado` y deja de aparecer como pendiente en el panel

### Requirement: Turno sin teléfono válido queda fallido
Si al generar el recordatorio el turno no tiene un teléfono de contacto en formato E.164 (ni en el turno ni en la o el paciente vinculado), el recordatorio SHALL quedar `fallido` con motivo `sin_telefono`, sin reintentos, y SHALL verse en el panel.

#### Scenario: Teléfono del turno (Happy Path)
- **GIVEN** que el turno 111 tiene teléfono de contacto "+5491100000001"
- **WHEN** corre el trabajo
- **THEN** su recordatorio queda `pendiente`

#### Scenario: Sin teléfono (Error de Negocio)
- **GIVEN** que el turno 112 no tiene teléfono de contacto ni paciente vinculado con teléfono
- **WHEN** corre el trabajo
- **THEN** su recordatorio queda `fallido` con motivo `sin_telefono` y con 0 reintentos programados

#### Scenario: Teléfono solo en la ficha del paciente (Caso de Borde)
- **GIVEN** que el turno 113 no tiene teléfono de contacto pero está vinculado a "Lucía Ficticia", cuya ficha tiene "+5491100000002"
- **WHEN** corre el trabajo
- **THEN** el recordatorio queda `pendiente` y su link usa "5491100000002"

### Requirement: Link de WhatsApp con el mensaje preformateado
Para un recordatorio vigente el sistema SHALL armar `https://wa.me/<teléfono sin "+">?text=<mensaje codificado>`. El mensaje SHALL incluir nombre de contacto, día y hora en la zona de la clínica, profesional, tratamiento y, si el turno tiene código de gestión, los enlaces `<PUBLIC_BASE_URL>/confirmar#<código>` y `<PUBLIC_BASE_URL>/gestionar#<código>` (código solo en el fragmento). Sin código, SHALL pedir que responda el mensaje.

#### Scenario: Link armado (Happy Path)
- **GIVEN** el turno 114 de "Carlos Sintético", teléfono "+5491100000001", el martes 17/11/2026 a las 10:30 (hora de la clínica) con "Dra. Ficticia" para "Limpieza", con código "CODIGO-SINTETICO-114"
- **WHEN** recepción pide el listado de recordatorios
- **THEN** el link empieza con "https://wa.me/5491100000001?text=" y el mensaje decodificado contiene "Carlos Sintético", "martes 17/11", "10:30", "Dra. Ficticia", "Limpieza", "/confirmar#CODIGO-SINTETICO-114" y "/gestionar#CODIGO-SINTETICO-114"

#### Scenario: Recordatorio que ya no corresponde (Error de Negocio)
- **GIVEN** que el recordatorio del turno 115 está `anulado` o `confirmado`
- **WHEN** recepción pide el listado de recordatorios por enviar
- **THEN** ese recordatorio no aparece con link para abrir WhatsApp

#### Scenario: Horario cerca del cambio de día en UTC (Caso de Borde)
- **GIVEN** un turno que empieza el 18/11/2026 a las 00:30 UTC (17/11 a las 21:30 en la clínica, UTC−3)
- **WHEN** se arma el mensaje
- **THEN** el mensaje dice "17/11" y "21:30", y los caracteres especiales del texto ("¿", "á", "#", "&") quedan codificados en la URL

#### Scenario: Turno interno sin código de gestión (Caso de Borde)
- **GIVEN** un turno `reservado` creado por el alta interna `POST /api/turnos`, sin código de gestión
- **WHEN** se arma su mensaje
- **THEN** el mensaje no contiene "/confirmar#" ni "/gestionar#" y pide responder el mensaje para confirmar o cancelar

### Requirement: Listado de recordatorios para recepción
`GET /api/panel/recordatorios` SHALL devolver a `recepcion` y `admin` los recordatorios vigentes de los turnos que empiezan dentro de la anticipación (por defecto los `pendiente` y `fallido`, filtrables por estado), ordenados por inicio del turno, con el link de WhatsApp cuando corresponde. El rol `odontologo` SHALL recibir 403 y una solicitud sin sesión, 401.

#### Scenario: Recepción ve los pendientes (Happy Path)
- **GIVEN** que hay recordatorios `pendiente` de los turnos 116 (mañana 09:00) y 117 (mañana 08:00)
- **WHEN** recepción pide el listado
- **THEN** recibe 200 con el turno 117 primero y el 116 después, cada uno con estado, horario, profesional, nombre de contacto y link

#### Scenario: Odontóloga intenta listar (Error de Negocio)
- **GIVEN** que el usuario autenticado tiene solo el rol `odontologo`
- **WHEN** pide `GET /api/panel/recordatorios`
- **THEN** recibe 403 y ningún teléfono ni link

#### Scenario: Recordatorio desactualizado por un cambio reciente (Caso de Borde)
- **GIVEN** que el turno 118 se reprogramó y el trabajo todavía no corrió, de modo que su recordatorio viejo apunta al horario anterior
- **WHEN** recepción pide el listado
- **THEN** el recordatorio del horario anterior no aparece

### Requirement: Abrir WhatsApp registra el envío
`POST /api/panel/recordatorios/{id}/enviado` SHALL pasar un recordatorio `pendiente` o `fallido` a `enviado`, guardando quién y cuándo. Volver a marcar un `enviado` SHALL responder 200 y actualizar la fecha (reenvío). Un recordatorio `confirmado` o `anulado` SHALL responder 409 sin cambios; uno inexistente, 404.

#### Scenario: Recepción abre WhatsApp (Happy Path)
- **GIVEN** que el recordatorio del turno 119 está `pendiente`
- **WHEN** recepción toca "Abrir WhatsApp" y el panel envía `POST /api/panel/recordatorios/{id}/enviado`
- **THEN** responde 200, el recordatorio queda `enviado` con el usuario de recepción y la fecha de envío

#### Scenario: Recordatorio anulado (Error de Negocio)
- **GIVEN** que el turno 120 se canceló y su recordatorio quedó `anulado`
- **WHEN** recepción intenta marcarlo enviado
- **THEN** responde 409 con motivo `recordatorio_no_vigente` y el recordatorio sigue `anulado`

#### Scenario: Reenvío de un recordatorio ya enviado (Caso de Borde)
- **GIVEN** que el recordatorio del turno 121 está `enviado` desde ayer
- **WHEN** recepción vuelve a marcarlo enviado
- **THEN** responde 200, sigue `enviado` y la fecha de envío es la de hoy

### Requirement: Marcar un recordatorio que no se pudo enviar
`POST /api/panel/recordatorios/{id}/fallido` SHALL pasar un recordatorio `pendiente` o `enviado` a `fallido` con un motivo de la lista `numero_invalido`, `sin_whatsapp` u `otro`, y SHALL rechazar con 422 cualquier otro motivo. Un recordatorio `confirmado` o `anulado` SHALL responder 409.

#### Scenario: El número no tiene WhatsApp (Happy Path)
- **GIVEN** que el recordatorio del turno 122 está `pendiente`
- **WHEN** recepción lo marca con motivo `sin_whatsapp`
- **THEN** responde 200 y el recordatorio queda `fallido` con ese motivo, visible en el panel

#### Scenario: Recordatorio ya confirmado (Error de Negocio)
- **GIVEN** que la paciente del turno 123 ya confirmó
- **WHEN** recepción intenta marcar su recordatorio `fallido`
- **THEN** responde 409 y el recordatorio sigue `confirmado`

#### Scenario: Motivo fuera de la lista (Caso de Borde)
- **WHEN** recepción envía el motivo "no atiende"
- **THEN** responde 422 y el recordatorio no cambia

### Requirement: La confirmación de la o el paciente cierra el recordatorio
Cuando un turno pasa de `reservado` a `confirmado` por la confirmación del paciente, su recordatorio vigente SHALL quedar `confirmado` con la fecha de confirmación (RN-WA-02). Si el turno no tenía recordatorio, la confirmación SHALL aceptarse igual y el trabajo no SHALL generarle uno.

#### Scenario: Confirma desde el link (Happy Path)
- **GIVEN** que el recordatorio del turno 124 está `enviado`
- **WHEN** el paciente confirma su asistencia con el código de gestión
- **THEN** el turno queda `confirmado` y el recordatorio `confirmado` con la fecha de confirmación

#### Scenario: Confirmación rechazada (Error de Negocio)
- **GIVEN** que el turno 125 está `cancelado` y su recordatorio `anulado`
- **WHEN** se intenta confirmar con su código
- **THEN** la confirmación se rechaza con 409 y el recordatorio sigue `anulado`

#### Scenario: Confirmación antes del recordatorio (Caso de Borde)
- **GIVEN** que el turno 126 `reservado` empieza en 5 días y no tiene recordatorio
- **WHEN** el paciente confirma y después el turno entra en la anticipación
- **THEN** el turno sigue `confirmado` y el trabajo no le genera recordatorio

### Requirement: Cancelar o reprogramar anula el recordatorio del horario anterior
Al cancelarse un turno (desde la gestión del paciente o desde el panel) o al reprogramarse, sus recordatorios `pendiente`, `enviado` o `fallido` del horario anterior SHALL pasar a `anulado` con motivo `turno_cancelado` o `turno_reprogramado`. Un turno reprogramado SHALL recibir un recordatorio nuevo para su horario nuevo según la anticipación. Si la anulación inmediata falla, el trabajo SHALL corregirlo en su próximo ciclo.

#### Scenario: Cancelación desde el link del recordatorio (Happy Path)
- **GIVEN** que el turno 127 `reservado` empieza en 40 horas y su recordatorio está `enviado`
- **WHEN** el paciente lo cancela desde `/gestionar#<código>` con la regla de 24 horas de la gestión
- **THEN** el turno queda `cancelado`, la seña `a_reembolsar` y el recordatorio `anulado` con motivo `turno_cancelado`

#### Scenario: Cancelación fuera de plazo desde el recordatorio (Error de Negocio)
- **GIVEN** que el turno 128 `reservado` empieza en 23 horas y 59 minutos y su recordatorio está `enviado`
- **WHEN** el paciente intenta cancelarlo desde `/gestionar#<código>`
- **THEN** recibe 409 `fuera_de_plazo`, el turno sigue `reservado` y el recordatorio sigue `enviado`

#### Scenario: Reprogramación con el publicador caído (Caso de Borde)
- **GIVEN** que el turno 129 `confirmado` con recordatorio `confirmado` se reprograma a otro día y la anulación inmediata falla
- **WHEN** corre el siguiente ciclo del trabajo
- **THEN** el recordatorio del horario anterior queda `anulado` con motivo `turno_reprogramado`, el turno está `reservado` (C-07 O5) y, si el nuevo horario está dentro de la anticipación, tiene un recordatorio `pendiente` nuevo

#### Scenario: Turno atendido o ausente conserva el historial (Caso de Borde)
- **GIVEN** que el turno 133 tenía su recordatorio `enviado` y después recepción lo marcó `ausente` (o `atendido`)
- **WHEN** corre el trabajo
- **THEN** el recordatorio sigue `enviado`: marcar ausente o atendido no anula recordatorios, solo la cancelación y la reprogramación lo hacen

### Requirement: Reintentos con espera creciente ante fallas del proveedor
Si el proveedor de WhatsApp informa un error transitorio al procesar un recordatorio, el sistema SHALL reintentar a los 1, 5 y 15 minutos y, agotado el tercer reintento, dejarlo `fallido` con el error registrado. El proveedor manual de v1 no SHALL fallar: deja el recordatorio `pendiente` para recepción.

#### Scenario: Proveedor manual (Happy Path)
- **GIVEN** que el proveedor configurado es `manual`
- **WHEN** el trabajo procesa el recordatorio del turno 130
- **THEN** el recordatorio queda `pendiente`, con 0 intentos fallidos

#### Scenario: Proveedor que falla siempre (Error de Negocio)
- **GIVEN** un proveedor que responde error transitorio en cada intento
- **WHEN** el trabajo procesa el recordatorio del turno 131 y los tres reintentos programados
- **THEN** el recordatorio queda `fallido` con 3 reintentos registrados y el último error, sin teléfono ni nombre en el error guardado

#### Scenario: Falla y luego éxito (Caso de Borde)
- **GIVEN** un proveedor que falla una vez y responde bien en el segundo intento
- **WHEN** pasa 1 minuto y el trabajo reintenta
- **THEN** el recordatorio queda en el estado que devolvió el proveedor y conserva 1 intento fallido registrado

### Requirement: Recordatorios sin datos personales en logs ni auditoría
El sistema no SHALL guardar el texto del mensaje en la base ni escribir teléfono, nombre, link ni código de gestión en logs o en la auditoría (R19, Ley 25.326). Marcar un recordatorio enviado o fallido SHALL quedar en la auditoría con el usuario, el id del recordatorio y los estados anterior y nuevo.

#### Scenario: Auditoría del envío (Happy Path)
- **WHEN** recepción marca enviado el recordatorio del turno 132
- **THEN** existe un registro de auditoría con su usuario, la entidad `recordatorio`, el id y los estados `pendiente` → `enviado`, sin teléfono ni link

#### Scenario: Error del proveedor con datos personales (Error de Negocio)
- **GIVEN** un proveedor que devuelve un error cuyo texto contiene "+5491100000003"
- **WHEN** se registra el fallo
- **THEN** el error guardado y el log no contienen "+5491100000003"

#### Scenario: Ciclo del trabajo con muchos turnos (Caso de Borde)
- **WHEN** el trabajo genera 50 recordatorios en un ciclo
- **THEN** el log del ciclo informa solo cantidades e ids, sin nombres, teléfonos ni códigos

### Requirement: Pantalla de recordatorios del panel a 360px
`frontend-panel/` SHALL ofrecer a recepción y admin la sección "Recordatorios" usable a 360 px de ancho sin scroll horizontal (R3), con los turnos por avisar, su estado, "Abrir WhatsApp" (abre el link en otra pestaña y registra el envío) y "No se pudo enviar". La odontóloga no SHALL ver la sección.

#### Scenario: Recepción avisa desde el celular (Happy Path)
- **GIVEN** que recepción entra al panel en un celular de 360 px y hay un recordatorio `pendiente` de "Carlos Sintético"
- **WHEN** abre "Recordatorios" y toca "Abrir WhatsApp"
- **THEN** se abre una pestaña con el link `https://wa.me/…`, la fila pasa a "Enviado" y la pantalla no tiene scroll horizontal

#### Scenario: Odontóloga en el panel (Error de Negocio)
- **GIVEN** que la usuaria autenticada tiene solo el rol `odontologo`
- **WHEN** navega a `#recordatorios`
- **THEN** no ve la sección en la navegación y queda en la agenda

#### Scenario: Sin recordatorios por enviar (Caso de Borde)
- **WHEN** recepción abre "Recordatorios" y no hay ninguno `pendiente` ni `fallido`
- **THEN** ve "No hay recordatorios por enviar" en lugar de una lista vacía
