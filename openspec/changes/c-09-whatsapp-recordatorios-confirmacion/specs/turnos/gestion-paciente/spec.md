# Spec Delta: turnos/gestion-paciente

## ADDED Requirements

### Requirement: Confirmación de asistencia con el código de gestión
`POST /api/public/gestion/confirmar`, con el código en la cabecera `X-Codigo-Gestion`, SHALL pasar un turno `reservado` que todavía no empezó a `confirmado` (RN-WA-02), con un registro de auditoría de origen `confirmacion_paciente`. La confirmación no SHALL exigir 24 horas de anticipación ni publicar eventos de calendario. Un código ausente o desconocido SHALL responder el 404 genérico de la gestión.

#### Scenario: Confirma su turno reservado (Happy Path)
- **GIVEN** que el turno de "Carlos Sintético" con código "CODIGO-SINTETICO-150" está `reservado` y empieza en 30 horas
- **WHEN** envía `POST /api/public/gestion/confirmar` con `X-Codigo-Gestion: CODIGO-SINTETICO-150`
- **THEN** recibe 200 con `estado: "confirmado"`, el turno queda `confirmado` y existe un registro de auditoría con origen `confirmacion_paciente`

#### Scenario: Código desconocido (Error de Negocio)
- **WHEN** se envía la confirmación con un código que no existe o sin la cabecera
- **THEN** responde 404 "No encontramos un turno con ese código" y ningún turno cambia

#### Scenario: Confirmar con menos de 24 horas (Caso de Borde)
- **GIVEN** que el turno `reservado` empieza en 2 horas, cuando ya no se puede cancelar ni reprogramar online
- **WHEN** el paciente lo confirma
- **THEN** recibe 200 y el turno queda `confirmado`

### Requirement: Solo se confirma un turno reservado que todavía no empezó
La confirmación SHALL rechazarse con 409 y sin cambios cuando el turno está `en_espera` (motivo `sena_pendiente`, R8), está `cancelado`, `ausente` o `atendido` (motivo `turno_no_modificable`) o su inicio ya pasó (motivo `turno_iniciado`). Confirmar un turno ya `confirmado` SHALL responder 200 sin cambios ni auditoría nueva.

#### Scenario: Confirmación repetida (Happy Path)
- **GIVEN** que el turno ya está `confirmado`
- **WHEN** el paciente vuelve a tocar "Confirmar asistencia"
- **THEN** recibe 200 con `estado: "confirmado"` y no se agrega otro registro de auditoría

#### Scenario: Pre-reserva sin seña acreditada (Error de Negocio)
- **GIVEN** que el turno está `en_espera` con la seña pendiente
- **WHEN** se intenta confirmarlo
- **THEN** responde 409 con motivo `sena_pendiente` y el turno sigue `en_espera`

#### Scenario: Turno que empieza en este instante (Caso de Borde)
- **GIVEN** que el turno `reservado` empezaba a las 10:00:00 y la confirmación llega a las 10:00:00
- **WHEN** se procesa
- **THEN** responde 409 con motivo `turno_iniciado` y el turno sigue `reservado`

### Requirement: La consulta informa si se puede confirmar
`GET /api/public/gestion` SHALL incluir `puede_confirmar` (verdadero solo para un turno `reservado` que todavía no empezó) y `motivo_no_confirmable` (`sena_pendiente`, `turno_no_modificable`, `turno_iniciado` o `ya_confirmado`) cuando no se puede, sin cambiar los demás campos.

#### Scenario: Turno reservado (Happy Path)
- **GIVEN** que el turno está `reservado` y empieza mañana
- **WHEN** se consulta la gestión
- **THEN** recibe `puede_confirmar: true` y `motivo_no_confirmable: null`

#### Scenario: Turno cancelado (Error de Negocio)
- **GIVEN** que el turno está `cancelado`
- **WHEN** se consulta la gestión
- **THEN** recibe `puede_confirmar: false` con motivo `turno_no_modificable`

#### Scenario: Turno ya confirmado (Caso de Borde)
- **GIVEN** que el turno está `confirmado`
- **WHEN** se consulta la gestión
- **THEN** recibe `puede_confirmar: false` con motivo `ya_confirmado`, y `puede_cancelar` sigue según la ventana de 24 horas

### Requirement: Pantalla de confirmación a 360px
El frontend del paciente SHALL ofrecer "Confirmar asistencia" en `/confirmar#<código>` a 360 px sin scroll horizontal (R3). SHALL mostrar día, hora (hora de la clínica), profesional y tratamiento, y confirmar solo cuando el paciente toca el botón: abrir el enlace nunca confirma. SHALL ofrecer el enlace a "Gestionar mi turno" para cancelar o cambiar el horario.

#### Scenario: Confirmar desde el celular (Happy Path)
- **GIVEN** que "Carlos Sintético" abre `/confirmar#CODIGO-SINTETICO-150` en un celular de 360 px con su turno `reservado` mañana a las 10:30
- **WHEN** toca "Confirmar asistencia"
- **THEN** ve "¡Listo! Confirmaste tu turno del martes 17/11 a las 10:30" y la pantalla no tiene scroll horizontal

#### Scenario: Turno que ya no se puede confirmar (Error de Negocio)
- **GIVEN** que el turno del código está `cancelado`
- **WHEN** abre `/confirmar#<código>`
- **THEN** ve "Este turno ya no se puede confirmar" sin botón de confirmar, y el turno no cambia

#### Scenario: Abrir el enlace sin tocar el botón (Caso de Borde)
- **GIVEN** que una vista previa de WhatsApp, o el propio paciente, abre `/confirmar#<código>` y no toca nada
- **WHEN** se cierra la pantalla
- **THEN** el turno sigue `reservado`, porque solo el botón envía la confirmación
