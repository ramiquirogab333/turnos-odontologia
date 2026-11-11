# Spec Delta: pagos/sena-turno

## MODIFIED Requirements

### Requirement: Transiciones de estado válidas del turno
El sistema SHALL permitir solo estas transiciones: `en_espera → reservado | cancelado`; `reservado → confirmado | cancelado | ausente | atendido`; `confirmado → cancelado | ausente | atendido`. `cancelado`, `ausente` y `atendido` son finales, con una única excepción: `atendido → reservado` por la corrección de un marcado equivocado, que solo existe como operación propia de recepción y admin (`turnos/gestion-panel`, C-12 O7). Una transición inválida SHALL rechazarse con 409 sin modificar nada.

#### Scenario: Transición permitida (Happy Path)
- **GIVEN** que el turno 60 está `reservado`
- **WHEN** se lo pasa a `confirmado`
- **THEN** el turno queda `confirmado` y su seña acreditada no cambia

#### Scenario: Transición desde un estado final (Error de Negocio)
- **GIVEN** que el turno 61 está `atendido`
- **WHEN** se intenta pasarlo a `reservado` o a `en_espera` por un cambio de estado común (marcar, cancelar, confirmar o acreditar)
- **THEN** se rechaza con 409 `transicion_invalida` y el turno sigue `atendido`

#### Scenario: Cancelación de una pre-reserva en espera (Caso de Borde)
- **GIVEN** que el turno 62 está `en_espera` con un pago pendiente
- **WHEN** se lo pasa a `cancelado`
- **THEN** el turno queda `cancelado` y el pago `vencido`, sin devolución porque no se cobró nada

#### Scenario: Corrección de un atendido y estados que siguen finales (Caso de Borde)
- **GIVEN** el turno 63 `atendido` dentro del plazo de corrección, el turno 64 `ausente` y el turno 65 `cancelado`
- **WHEN** recepción aplica la corrección de C-12 a cada uno
- **THEN** el 63 queda `reservado` con su seña sin cambios, y el 64 y el 65 responden 409 `transicion_invalida` y siguen como estaban
