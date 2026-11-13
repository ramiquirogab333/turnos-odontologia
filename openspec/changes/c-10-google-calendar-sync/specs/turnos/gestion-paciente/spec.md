# Spec Delta: turnos/gestion-paciente

## ADDED Requirements

### Requirement: La reprogramación no lleva a un horario ocupado en Google Calendar
`POST /api/public/gestion/reprogramar` SHALL tratar una franja ocupada del Google Calendar conectado de la profesional como un horario ocupado por la profesional: 409 con el mismo motivo y alternativas que hoy, sin modificar el turno y sin revelar que el motivo es Google (O10).

#### Scenario: Reprogramar a un horario libre en ambos (Happy Path)
- **GIVEN** el turno 520 `reservado` de la profesional 7 a 3 días, y una franja ocupada en Google de 15:00 a 16:00 del día nuevo
- **WHEN** la paciente reprograma a las 16:00 de ese día
- **THEN** el turno se mueve a las 16:00 y su evento de Google se mueve en el ciclo siguiente

#### Scenario: Reprogramar sobre la franja ocupada (Error de Negocio)
- **WHEN** la paciente pide reprogramar el turno 520 a las 15:30 de ese día
- **THEN** recibe 409 con el motivo de horario ocupado por la profesional y alternativas que no incluyen 15:00 ni 15:30, y el turno no cambia

#### Scenario: Reprogramar a un horario que empieza cuando termina la franja (Caso de Borde)
- **WHEN** la paciente pide las 16:00 justas
- **THEN** se acepta: la franja de Google es `[15:00, 16:00)`
