# Spec Delta: pagos/sena-turno

## MODIFIED Requirements

### Requirement: La cancelación con 24 horas o más devuelve la seña
Cuando un turno `reservado` o `confirmado` con seña acreditada se cancela con 24 horas o más de anticipación, el sistema SHALL liberar el horario y dejar el pago `a_reembolsar`, para devolución manual (RN-SN-04). Con menos de 24 horas la cancelación SHALL rechazarse (RN-TU-01). La regla vale igual para la cancelación del paciente con el código de gestión (`POST /api/public/gestion/cancelar`, C-07) y para el servicio de cambio de estado.

#### Scenario: Cancelación con más de 24 horas (Happy Path)
- **GIVEN** que el turno 65 está `reservado` con una seña acreditada de "3000.00" y faltan 48 horas para su inicio
- **WHEN** se lo cancela
- **THEN** el turno queda `cancelado`, el horario vuelve a estar libre y el pago queda `a_reembolsar` por "3000.00"

#### Scenario: Cancelación con menos de 24 horas (Error de Negocio)
- **GIVEN** que el turno 66 está `confirmado` con una seña acreditada y faltan 23 horas y 59 minutos para su inicio
- **WHEN** se intenta cancelarlo
- **THEN** se rechaza con 409 `fuera_de_plazo`, el turno sigue `confirmado` y el pago sigue `acreditado`

#### Scenario: Cancelación exactamente 24 horas antes (Caso de Borde)
- **GIVEN** que el turno 67 está `reservado` con una seña acreditada y faltan exactamente 24 horas para su inicio
- **WHEN** se lo cancela
- **THEN** la cancelación se acepta y el pago queda `a_reembolsar`

## ADDED Requirements

### Requirement: Cancelar una pre-reserva resuelve sus pagos sin cobrar
Al cancelar un turno `en_espera`, el sistema SHALL pasar su pago `pendiente` a `vencido` y cada pago `en_revision` del turno a `a_reembolsar` (RN-SN-10), sin registrar ningún cobro ni reembolso automático (R8). La ventana de 24 horas no SHALL aplicarse a un `en_espera`.

#### Scenario: Pre-reserva con pago pendiente (Happy Path)
- **GIVEN** que el turno 70 está `en_espera` con un pago de Mercado Pago `pendiente` de "3000.00"
- **WHEN** se lo cancela
- **THEN** el turno queda `cancelado` y el pago `vencido`, y no queda ningún pago `acreditado` ni `a_reembolsar` para ese turno

#### Scenario: Aprobación que llega después de cancelar (Error de Negocio)
- **GIVEN** que el turno 71 `en_espera` se canceló con su pago `pendiente`
- **WHEN** llega un webhook firmado que aprueba ese pago
- **THEN** el pago queda `a_reembolsar` (RN-SN-05), el turno sigue `cancelado` y no bloquea la agenda

#### Scenario: Pre-reserva con pago en revisión a 3 horas del inicio (Caso de Borde)
- **GIVEN** que el turno 72 está `en_espera`, faltan 3 horas para su inicio y tiene un pago `en_revision` con monto informado "2500.00"
- **WHEN** se lo cancela
- **THEN** se acepta sin aplicar la ventana de 24 horas, el turno queda `cancelado` y el pago `a_reembolsar` con su monto informado intacto

### Requirement: La seña acreditada acompaña al turno reprogramado
Al reprogramar un turno con seña acreditada, el sistema SHALL mantener el mismo pago `acreditado`, con su monto y porcentaje originales, asociado al turno en su nuevo horario: no SHALL crear un pago nuevo, cobrar una diferencia ni marcarlo `a_reembolsar`.

#### Scenario: Reprogramación con seña acreditada (Happy Path)
- **GIVEN** que el turno 75 está `reservado` con una seña `acreditado` de "3000.00" al 30%
- **WHEN** se lo reprograma con 72 horas de anticipación a un horario libre
- **THEN** el turno tiene el mismo pago `acreditado` de "3000.00" al 30% y no existe ningún otro pago activo para él

#### Scenario: Reprogramación rechazada (Error de Negocio)
- **GIVEN** que el turno 76 está `reservado` con seña `acreditado` y faltan 23 horas
- **WHEN** se intenta reprogramarlo
- **THEN** se rechaza con 409 `fuera_de_plazo` y el pago sigue `acreditado` sin cambios

#### Scenario: Porcentaje o precio cambiados antes de reprogramar (Caso de Borde)
- **GIVEN** que después de acreditar la seña del turno 77 el admin cambió el porcentaje al 40% y el precio base del tratamiento
- **WHEN** se reprograma el turno
- **THEN** la seña sigue siendo "3000.00" al 30%, sin cobro adicional ni devolución parcial
