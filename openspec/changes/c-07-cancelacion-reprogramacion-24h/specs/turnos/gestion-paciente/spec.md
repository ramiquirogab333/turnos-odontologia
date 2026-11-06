# Spec Delta: turnos/gestion-paciente

## Purpose
Permite que la o el paciente gestione su propio turno sin cuenta, solo con el código de gestión que recibió al reservar: consultarlo, cancelarlo y reprogramarlo respetando la ventana de 24 horas (RN-TU-01, RN-TU-02, DD-02), con alternativas ante un horario ocupado y avisando a calendario y recordatorios (Flujo 2, US-002, US-003).

## ADDED Requirements

### Requirement: Acceso a la gestión solo con el código de gestión
El sistema SHALL identificar el turno a gestionar únicamente por su código de gestión, enviado en la cabecera `X-Codigo-Gestion` y nunca en la ruta ni en la query. Un código ausente, desconocido o de un turno sin código (alta interna) SHALL responder 404 con el mismo mensaje genérico, sin revelar si el turno existe ni datos de contacto.

#### Scenario: Código de gestión correcto (Happy Path)
- **GIVEN** que "Carlos Sintético" (+5491144445555) tiene un turno `reservado` con código de gestión C1
- **WHEN** consulta `GET /api/public/gestion` con la cabecera `X-Codigo-Gestion: C1`
- **THEN** recibe 200 con los datos de su turno

#### Scenario: Código desconocido o ausente (Error de Negocio)
- **WHEN** se consulta, cancela o reprograma con un código que no existe, con la cabecera vacía o sin ella
- **THEN** el sistema responde 404 "No encontramos un turno con ese código", con el mismo cuerpo en los tres casos, y no modifica ningún turno

#### Scenario: Turno interno sin código de gestión (Caso de Borde)
- **GIVEN** un turno creado por `POST /api/turnos` (alta interna) que no tiene código de gestión
- **WHEN** alguien intenta gestionarlo por la API pública con cualquier código
- **THEN** el sistema responde 404 y el turno no cambia

### Requirement: Consulta del turno para gestionarlo
`GET /api/public/gestion` SHALL devolver inicio, fin, tratamiento, profesional, estado del turno, monto y estado de la seña, el límite para cancelar o reprogramar (inicio − 24 h) y si cada acción está permitida en este momento, con su motivo si no lo está. No SHALL devolver el teléfono de contacto. Las horas SHALL tener el offset de la clínica (America/Argentina/Buenos_Aires).

#### Scenario: Turno reservado con más de 24 horas por delante (Happy Path)
- **GIVEN** que el turno de "Carlos Sintético" está `reservado` el 2026-11-16 de 10:00 a 10:30 (-03:00), con seña acreditada de "3000.00", y ahora son las 09:00 del 2026-11-14
- **WHEN** consulta la gestión con su código
- **THEN** recibe `puede_cancelar: true`, `puede_reprogramar: true`, `limite_cambios` "2026-11-15T10:00:00-03:00", la seña "3000.00" `acreditado` y ningún teléfono

#### Scenario: Turno ya cancelado (Error de Negocio)
- **GIVEN** que el turno está `cancelado`
- **WHEN** se consulta la gestión
- **THEN** recibe 200 con `estado: "cancelado"`, `puede_cancelar: false` y `puede_reprogramar: false` con motivo `turno_no_modificable`

#### Scenario: Dentro de las últimas 24 horas (Caso de Borde)
- **GIVEN** que el turno `reservado` empieza el 2026-11-16 a las 10:00 (-03:00) y ahora son las 10:01 del 2026-11-15
- **WHEN** se consulta la gestión
- **THEN** recibe `puede_cancelar: false` y `puede_reprogramar: false` con motivo `fuera_de_plazo` y el mismo `limite_cambios`

### Requirement: Cancelación de un turno con seña acreditada respetando 24 horas
`POST /api/public/gestion/cancelar` sobre un turno `reservado` o `confirmado` SHALL aceptarse solo si faltan 24 horas o más para el inicio, comparando instantes absolutos (exactamente 24 h se acepta). Al aceptarse, el turno SHALL pasar a `cancelado` y liberar el horario, y la seña acreditada SHALL quedar `a_reembolsar` (RN-TU-01, RN-SN-04). Si no, 409 `fuera_de_plazo` sin cambios.

#### Scenario: Cancelación con 48 horas de anticipación (Happy Path)
- **GIVEN** que el turno de "Carlos Sintético" está `reservado` con seña acreditada de "3000.00" y faltan 48 horas para el inicio
- **WHEN** envía `POST /api/public/gestion/cancelar` con su código
- **THEN** recibe 200 con `estado: "cancelado"` y `estado_sena: "a_reembolsar"`, el horario vuelve a figurar libre en la disponibilidad y queda una auditoría con origen `cancelacion_paciente`

#### Scenario: Cancelación con 23 horas y 59 minutos (Error de Negocio)
- **GIVEN** que el turno está `confirmado` con seña acreditada y faltan 23 horas y 59 minutos para el inicio
- **WHEN** se envía la cancelación
- **THEN** el sistema responde 409 con `motivo: "fuera_de_plazo"`, el límite en hora de la clínica y un mensaje que dice que ya no se puede cancelar online y que se comunique con la clínica; el turno sigue `confirmado`, la seña sigue `acreditado` y el horario sigue ocupado

#### Scenario: Cancelación exactamente 24 horas antes (Caso de Borde)
- **GIVEN** que el turno `reservado` empieza el 2026-11-16 a las 10:00:00 (-03:00) y el servidor recibe la cancelación a las 10:00:00 del 2026-11-15 (-03:00)
- **WHEN** se procesa la cancelación
- **THEN** se acepta, el turno queda `cancelado` y la seña `a_reembolsar`; recibida a las 10:00:01 se rechaza con 409 `fuera_de_plazo`

### Requirement: Cancelación de una pre-reserva en espera
Cancelar un turno `en_espera` SHALL aceptarse en cualquier momento mientras siga en espera, porque no bloquea agenda ni se cobró nada (R8). El turno SHALL pasar a `cancelado`, el pago pendiente a `vencido` sin movimiento de caja y un pago `en_revision` a `a_reembolsar` (RN-SN-10). Un turno en estado final SHALL rechazarse con 409 `turno_no_modificable`.

#### Scenario: Cancelación de una pre-reserva con pago pendiente (Happy Path)
- **GIVEN** que "Carlos Sintético" tiene un turno `en_espera` con un pago de Mercado Pago `pendiente`
- **WHEN** lo cancela con su código
- **THEN** recibe 200, el turno queda `cancelado`, el pago `vencido`, no se registra ningún reembolso ni cobro y la disponibilidad no cambia porque el horario nunca estuvo ocupado

#### Scenario: Turno en estado final (Error de Negocio)
- **GIVEN** que el turno ya está `cancelado`, `ausente` o `atendido`
- **WHEN** se intenta cancelarlo
- **THEN** el sistema responde 409 `turno_no_modificable` y nada cambia; en particular, un `ausente` conserva su seña `no_reembolsado` (R9)

#### Scenario: Pre-reserva a menos de 24 horas o con pago en revisión (Caso de Borde)
- **GIVEN** que el turno está `en_espera`, faltan 3 horas para el inicio y tiene un pago `en_revision`
- **WHEN** se lo cancela
- **THEN** se acepta sin aplicar la ventana de 24 horas, el turno queda `cancelado` y el pago `a_reembolsar`; si después llega la aprobación de un pago pendiente de ese turno, queda `a_reembolsar` y el turno no revive (RN-SN-05)

### Requirement: Reprogramación a un horario libre respetando 24 horas
`POST /api/public/gestion/reprogramar` con un nuevo inicio SHALL mover un turno `reservado` o `confirmado` solo si faltan 24 horas o más para su inicio actual (RN-TU-02), con el mismo tratamiento y profesional y `fin = nuevo inicio + duración vigente del tratamiento` (RN-TU-04). El turno SHALL conservar su identificador, su código de gestión y su seña acreditada. Si no, 409 `fuera_de_plazo` sin cambios.

#### Scenario: Reprogramación con 72 horas de anticipación (Happy Path)
- **GIVEN** que el turno de "Carlos Sintético" (Limpieza, 30 min) está `reservado` el 2026-11-16 a las 10:00, con seña acreditada de "3000.00", y faltan 72 horas
- **WHEN** reprograma al 2026-11-18 a las 11:00 (-03:00), un horario libre de la misma profesional
- **THEN** recibe 200, el turno queda `reservado` de 11:00 a 11:30 del 2026-11-18 con el mismo id y código, la seña sigue `acreditado` por "3000.00", las 10:00 del 2026-11-16 vuelven a figurar libres y queda una auditoría con el inicio anterior y el nuevo

#### Scenario: Reprogramación con menos de 24 horas (Error de Negocio)
- **GIVEN** que faltan 23 horas y 59 minutos para el inicio actual del turno `reservado`
- **WHEN** se intenta reprogramarlo a cualquier horario libre
- **THEN** el sistema responde 409 `fuera_de_plazo` con el límite, y el turno, su horario y su seña no cambian

#### Scenario: Reprogramación exactamente 24 horas antes o hacia un horario que se superpone con el propio (Caso de Borde)
- **GIVEN** que faltan exactamente 24 horas para el inicio del turno `reservado` de 10:00 a 10:30
- **WHEN** se lo reprograma a las 10:15 del mismo día, que solo se superpone con el propio turno
- **THEN** se acepta: la ventana se cumple y el propio turno no cuenta como ocupación del nuevo horario

### Requirement: Reprogramación a un horario ocupado ofrece alternativas
Si el nuevo horario está ocupado por un turno bloqueante de la misma profesional o no queda ningún sillón libre (RN-TU-03), el sistema SHALL responder 409 con el motivo y una lista de horarios libres alternativos, sin modificar el turno. La base de datos SHALL seguir siendo la garantía final contra el solape (R5): una violación del EXCLUDE nunca SHALL producir un 500.

#### Scenario: Nuevo horario libre (Happy Path)
- **GIVEN** que el 2026-11-18 a las 11:00 la profesional y al menos un sillón están libres
- **WHEN** se reprograma a ese horario
- **THEN** se acepta y el turno queda con un sillón libre asignado

#### Scenario: Nuevo horario ocupado (Error de Negocio)
- **GIVEN** que el 2026-11-18 a las 11:00 la profesional ya tiene un turno `reservado`
- **WHEN** "Carlos Sintético" intenta reprogramar a ese horario
- **THEN** el sistema responde 409 con el motivo `profesional` y alternativas libres próximas, y su turno sigue en el horario original con su seña `acreditado`

#### Scenario: Dos pacientes reprograman al mismo horario a la vez (Caso de Borde)
- **GIVEN** que dos turnos `reservado` de la misma profesional, con más de 24 horas por delante, piden en simultáneo reprogramar al mismo horario libre
- **WHEN** se procesan las dos solicitudes
- **THEN** exactamente una recibe 200; la otra recibe 409 con alternativas, su turno queda en su horario original y nunca se responde 500

### Requirement: Reprogramación solo dentro de la disponibilidad vigente
El nuevo inicio SHALL ser un instante futuro con zona horaria, distinto del inicio actual, y el turno resultante SHALL caber completo en una franja de disponibilidad vigente de la profesional (RN-TU-07). Si no, el sistema SHALL responder 422 con el motivo y no modificar el turno.

#### Scenario: Horario dentro de la franja (Happy Path)
- **GIVEN** que la profesional atiende de 09:00 a 13:00 los miércoles
- **WHEN** se reprograma un turno de 30 minutos al miércoles 2026-11-18 a las 12:30
- **THEN** se acepta y el turno queda de 12:30 a 13:00

#### Scenario: Horario fuera de la franja (Error de Negocio)
- **GIVEN** que la profesional atiende de 09:00 a 13:00 los miércoles
- **WHEN** se reprograma un turno de 30 minutos al miércoles 2026-11-18 a las 12:45 o a las 20:00
- **THEN** el sistema responde 422 `fuera_de_disponibilidad` y el turno no cambia

#### Scenario: Mismo horario, horario pasado o sin zona horaria (Caso de Borde)
- **WHEN** el nuevo inicio es igual al actual, ya pasó o llega sin offset ("2026-11-18T11:00:00")
- **THEN** el sistema responde 422 (`mismo_horario` o error de validación) y el turno no cambia

### Requirement: Solo se reprograman turnos con seña acreditada y vigentes
Reprogramar SHALL rechazarse con 409 `sena_pendiente` si el turno está `en_espera` (la o el paciente puede cancelarlo y reservar otro horario) y con 409 `turno_no_modificable` si está en un estado final. Un turno `confirmado` que se reprograma SHALL volver a `reservado`, porque la confirmación correspondía al horario anterior.

#### Scenario: Turno confirmado reprogramado (Happy Path)
- **GIVEN** que el turno está `confirmado` y faltan 5 días
- **WHEN** se lo reprograma a un horario libre
- **THEN** se acepta y el turno queda `reservado` en el nuevo horario, con su seña `acreditado`

#### Scenario: Pre-reserva en espera (Error de Negocio)
- **GIVEN** que el turno está `en_espera` con la seña sin acreditar
- **WHEN** se intenta reprogramarlo
- **THEN** el sistema responde 409 `sena_pendiente` con el mensaje "Tu turno todavía no está confirmado. Cancelalo y reservá otro horario." y nada cambia

#### Scenario: Turno atendido o ausente (Caso de Borde)
- **GIVEN** que el turno está `atendido` o `ausente`
- **WHEN** se intenta reprogramarlo
- **THEN** el sistema responde 409 `turno_no_modificable` y la seña conserva su estado (`no_reembolsado` en el ausente, R9)

### Requirement: Eventos de cancelación y reprogramación para calendario y recordatorios
Después de confirmar una cancelación o reprogramación de un turno que bloqueaba agenda, el sistema SHALL publicar `turno_cancelado` o `turno_reprogramado` (id del turno, profesional, inicio y fin anteriores y nuevos, sin datos de contacto) para que Google Calendar y los recordatorios se actualicen (Flujo 2, paso 4). Una falla al publicar no SHALL revertir la operación.

#### Scenario: Cancelación publica el evento (Happy Path)
- **GIVEN** un turno `reservado` que se cancela con más de 24 horas
- **WHEN** la cancelación se confirma
- **THEN** se publica exactamente un `turno_cancelado` con el id, la profesional y el horario liberado, sin nombre ni teléfono

#### Scenario: Operación rechazada no publica nada (Error de Negocio)
- **GIVEN** una cancelación o reprogramación rechazada (409 o 422)
- **WHEN** termina la solicitud
- **THEN** no se publica ningún evento

#### Scenario: Pre-reserva cancelada o publicador caído (Caso de Borde)
- **GIVEN** que se cancela un turno `en_espera`, que nunca tuvo evento de calendario ni recordatorio (RN-SN-01), o que el publicador falla al publicar la cancelación de un `reservado`
- **WHEN** se procesa la cancelación
- **THEN** para el `en_espera` no se publica nada; para el `reservado` la respuesta sigue siendo 200, el turno queda `cancelado` y la falla se registra en el log sin datos personales

### Requirement: Pantalla de gestión del turno a 360px
El frontend del paciente SHALL ofrecer "Gestionar mi turno" a 360px de ancho sin scroll horizontal (R3), accesible por el enlace `/gestionar#<código>` (el código va en el fragmento y nunca llega al servidor en la URL) o pegando el código. SHALL mostrar el turno, el límite para cambios en hora de la clínica, la política de la seña y las acciones permitidas. La confirmación de la reserva SHALL incluir ese enlace.

#### Scenario: Cancelar desde el celular (Happy Path)
- **GIVEN** que "Carlos Sintético" abre `/gestionar#C1` en un celular de 360px con su turno `reservado` a 3 días
- **WHEN** toca "Cancelar turno" y confirma en el diálogo que explica que la clínica le devuelve la seña de $ 3.000,00
- **THEN** ve "Turno cancelado" con el aviso de la devolución, y la pantalla no tiene scroll horizontal

#### Scenario: Turno dentro de las últimas 24 horas (Error de Negocio)
- **GIVEN** que el turno empieza en 20 horas
- **WHEN** abre la pantalla de gestión
- **THEN** ve "Ya no podés cancelar ni cambiar el turno online porque faltan menos de 24 h. Comunicate con la clínica." y no hay botones de cancelar ni de cambiar horario habilitados; si el servidor igual responde 409 `fuera_de_plazo`, la pantalla muestra ese mismo mensaje

#### Scenario: Reprogramar a un horario que se ocupó mientras elegía (Caso de Borde)
- **GIVEN** que eligió un horario nuevo que otro paciente tomó antes de confirmar
- **WHEN** confirma el cambio
- **THEN** ve "Ese horario ya no está disponible" con las alternativas del 409 para elegir una, y su turno sigue en el horario original
