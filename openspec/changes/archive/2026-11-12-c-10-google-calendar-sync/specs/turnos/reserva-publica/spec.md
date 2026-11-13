# Spec Delta: turnos/reserva-publica

## ADDED Requirements

### Requirement: Los horarios ocupados en Google Calendar no se ofrecen ni se reservan
`GET /api/public/disponibilidad` SHALL excluir los horarios que se superponen con una franja ocupada del Google Calendar conectado de la profesional (O10), y `POST /api/public/turnos` SHALL rechazarlos con el mismo 409 de horario ocupado por la profesional (`motivo = profesional`, con alternativas), sin revelar que el motivo es Google.

#### Scenario: Franja ocupada fuera de la oferta (Happy Path)
- **GIVEN** la profesional 7 conectada con una franja ocupada en Google mañana de 15:00 a 16:00 y disponibilidad de 9:00 a 18:00
- **WHEN** se consulta la disponibilidad para un tratamiento de 30 minutos
- **THEN** no se ofrecen 15:00 ni 15:30, y sí 14:30 y 16:00

#### Scenario: Reservar un horario ocupado en Google (Error de Negocio)
- **GIVEN** la misma franja ocupada y una pantalla que todavía muestra 15:00
- **WHEN** se pide `POST /api/public/turnos` a las 15:00
- **THEN** recibe 409 con `motivo = profesional` y alternativas, y no se crea ningún turno

#### Scenario: Conexión revocada o desconectada (Caso de Borde)
- **GIVEN** la profesional 7 con la conexión `revocada`
- **WHEN** se consulta la disponibilidad
- **THEN** siguen excluyéndose las franjas ocupadas ya conocidas; si la conexión está `desconectada`, sus franjas dejan de excluirse
