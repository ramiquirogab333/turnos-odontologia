# Spec Delta: turnos/agenda-panel

## ADDED Requirements

### Requirement: La agenda muestra las franjas ocupadas en Google Calendar
`GET /api/panel/agenda` SHALL devolver, además de los turnos, las franjas ocupadas de Google de las profesionales del alcance del usuario que caen en el período (`ocupados_google` con profesional, inicio y fin), sin título ni otro dato del evento (O19). La pantalla SHALL mostrarlas como "Ocupado en Google".

#### Scenario: Día con una franja ocupada (Happy Path)
- **GIVEN** la profesional 7 conectada con una franja ocupada mañana de 15:00 a 16:00
- **WHEN** recepción pide la agenda del día de mañana
- **THEN** la respuesta incluye la franja con `profesional_id = 7`, inicio y fin en hora de la clínica, y la pantalla la muestra como "Ocupado en Google"

#### Scenario: Franjas de otra profesional (Error de Negocio)
- **GIVEN** la usuaria de la profesional 8
- **WHEN** pide su agenda
- **THEN** no recibe las franjas ocupadas de la profesional 7

#### Scenario: Cliente anterior (Caso de Borde)
- **GIVEN** un cliente del panel que no conoce `ocupados_google`
- **WHEN** pide la agenda
- **THEN** los campos de turnos existentes no cambian y el campo nuevo se ignora

### Requirement: La agenda marca los turnos con conflicto de calendario
Cada turno de la agenda SHALL informar el estado de su evento (`sin_evento`, `pendiente`, `sincronizado`, `desvinculado`) y si tiene un conflicto de Google Calendar abierto. La tarjeta del turno con conflicto SHALL mostrar el aviso "Conflicto con Google Calendar" con un enlace a la sección.

#### Scenario: Turno con conflicto abierto (Happy Path)
- **GIVEN** el turno 512 con conflicto `movido_en_google` abierto
- **WHEN** recepción ve la agenda en un viewport de 360 px
- **THEN** la tarjeta muestra "Conflicto con Google Calendar" sin desplazamiento horizontal y el enlace lleva a la sección "Google Calendar"

#### Scenario: Pre-reserva (Error de Negocio)
- **GIVEN** el turno 502 `en_espera`
- **WHEN** se ve la agenda
- **THEN** figura `sin_evento` y sin aviso de conflicto (R8)

#### Scenario: Profesional sin conexión (Caso de Borde)
- **GIVEN** un turno `reservado` de la profesional 8 sin Google Calendar conectado
- **WHEN** se ve la agenda
- **THEN** figura `sin_evento` sin aviso
