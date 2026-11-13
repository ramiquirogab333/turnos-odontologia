# Spec Delta: turnos/reserva-publica

## ADDED Requirements

### Requirement: La reserva informa el límite de solicitudes sin perder lo cargado
Si la reserva, el inicio de la seña o la consulta de horarios responden 429, el sitio del paciente SHALL mostrar "Hiciste muchos pedidos seguidos. Probá de nuevo en N minutos", con N desde `Retry-After` redondeado hacia arriba (mínimo 1), SHALL conservar los datos ya cargados del formulario y no SHALL dar el turno por reservado. El mensaje SHALL leerse completo a 360 px (R3).

#### Scenario: Reserva limitada (Happy Path del mensaje)
- **GIVEN** un paciente con "Paciente Ficticio" y `+5491100000001` cargados en el último paso
- **WHEN** confirma y la reserva responde 429 con `Retry-After: 300`
- **THEN** ve "Hiciste muchos pedidos seguidos. Probá de nuevo en 5 minutos", sigue en el mismo paso con sus datos y no ve ningún código de gestión

#### Scenario: Horario ocupado antes del límite (Error de Negocio)
- **GIVEN** que la reserva responde 409 por horario ocupado
- **WHEN** el paciente confirma
- **THEN** ve las alternativas de siempre, no el mensaje de límite

#### Scenario: Pantalla angosta (Caso de Borde)
- **GIVEN** un viewport de 360 x 800
- **WHEN** aparece el mensaje de límite
- **THEN** se lee completo sin desplazamiento horizontal y el botón para reintentar mide al menos 48 px de alto
