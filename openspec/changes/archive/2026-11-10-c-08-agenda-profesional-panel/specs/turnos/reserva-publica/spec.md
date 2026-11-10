# Spec Delta: turnos/reserva-publica

## MODIFIED Requirements

### Requirement: Consulta de disponibilidad de turnos libres
El sistema SHALL permitir la consulta pública de franjas horarias disponibles para una fecha o rango de fechas, profesional y tratamiento determinado, considerando la duración del tratamiento y los turnos existentes. Solo los turnos que ocupan agenda (`reservado`, `confirmado`, `atendido`) ocupan un horario; un `atendido` lo ocupa hasta su `fin` aunque se haya marcado antes (O19 de C-08). Las pre-reservas `en_espera` (R8) y los turnos `ausente` o `cancelado` no lo ocupan.

#### Scenario: Consulta de disponibilidad con horarios libres
- **WHEN** un paciente solicita disponibilidad para un profesional y un tratamiento de 30 minutos en una fecha laboral
- **THEN** el sistema devuelve una lista de intervalos de inicio y fin donde tanto el profesional como al menos un sillón físico están desocupados con código HTTP 200

#### Scenario: Una pre-reserva en espera no ocupa el horario (Caso de Borde)
- **GIVEN** que el único turno del profesional P el 2026-11-16 es un `en_espera` de 10:00 a 10:30
- **WHEN** un paciente consulta la disponibilidad de P para ese día con un tratamiento de 30 minutos
- **THEN** el horario de 10:00 a 10:30 figura como libre

#### Scenario: Un turno con seña acreditada ocupa el horario (Error de Negocio)
- **GIVEN** que el profesional P tiene un turno `reservado` (seña acreditada) de 10:00 a 10:30 el 2026-11-16
- **WHEN** un paciente consulta la disponibilidad de P para ese día
- **THEN** el horario de 10:00 a 10:30 no figura como libre

#### Scenario: Un atendido marcado antes de su hora sigue ocupado (Happy Path)
- **GIVEN** que el turno de P de 11:00 a 11:30 del 2026-11-16 se marcó `atendido` a las 09:30 de ese día
- **WHEN** un paciente consulta la disponibilidad de P para ese día o intenta reservar a las 11:00
- **THEN** el horario de 11:00 a 11:30 no figura como libre y la reserva responde 409 con alternativas

#### Scenario: El horario de un ausente vuelve a estar libre (Error de Negocio)
- **GIVEN** que el turno de P de 12:00 a 12:30 del 2026-11-16 se marcó `ausente` a las 12:10
- **WHEN** a las 12:11 un paciente consulta la disponibilidad de P para ese día con un tratamiento de 15 minutos
- **THEN** el ausente ya no cuenta como ocupación: los inicios futuros dentro de la franja entre 12:11 y 12:30, como 12:15, figuran como libres

#### Scenario: Turno que empieza en el fin de un atendido (Caso de Borde)
- **GIVEN** que el turno de P de 11:00 a 11:30 del 2026-11-16 está `atendido`
- **WHEN** un paciente consulta la disponibilidad de P para ese día con un tratamiento de 30 minutos
- **THEN** el horario de 11:30 a 12:00 figura como libre
