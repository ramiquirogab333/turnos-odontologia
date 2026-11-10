# Spec Delta: pagos/sena-turno

## MODIFIED Requirements

### Requirement: La pre-reserva en espera no dispara notificaciones
El sistema no SHALL generar recordatorio de WhatsApp ni evento de calendario para un turno `en_espera` (RN-SN-01, RN-WA-03). Solo la acreditación de la seña y el alta manual desde el panel (C-08), que nace bloqueante y sin seña, SHALL disparar esos efectos. La acreditación SHALL dejar un registro de auditoría con origen `acreditacion_sena` y el alta manual uno con origen `alta_manual_panel`, que C-09 y C-10 van a consumir.

#### Scenario: Acreditación deja el punto de enganche (Happy Path)
- **GIVEN** que el turno 63 está `en_espera`
- **WHEN** se acredita su seña
- **THEN** existe exactamente un registro de auditoría del turno 63 con origen `acreditacion_sena` y estado `reservado`

#### Scenario: Pre-reserva que vence sin pagar (Error de Negocio)
- **GIVEN** que el turno 64 se creó `en_espera` y venció sin pago
- **WHEN** se revisa la auditoría del turno 64
- **THEN** no hay ningún registro con origen `acreditacion_sena` y no se generó ningún recordatorio ni evento

#### Scenario: Alta manual deja el punto de enganche (Caso de Borde)
- **GIVEN** que recepción crea desde el panel el turno 75, que nace `reservado` y sin seña
- **WHEN** se revisa la auditoría del turno 75
- **THEN** existe exactamente un registro con origen `alta_manual_panel` y estado `reservado`, y ninguno con origen `acreditacion_sena`
