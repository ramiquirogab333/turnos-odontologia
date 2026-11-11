# Spec Delta: pagos/pagos-presupuesto

## ADDED Requirements

### Requirement: Los cobros de un día cerrado no se registran ni se anulan
Registrar un pago con fecha de cobro en un día que tiene un cierre de caja vigente, o anular un pago cuya fecha de cobro está en un día cerrado, SHALL rechazarse con 409 `caja_cerrada` indicando el día, sin crear ni cambiar ningún pago (C-12 O2). El día SHALL ser el de la clínica. Con el día abierto, las reglas de C-11 no cambian.

#### Scenario: Cobro de hoy con días anteriores cerrados (Happy Path)
- **GIVEN** el 2026-11-17 cerrado y un presupuesto `aceptado` con saldo 4000.00
- **WHEN** recepción registra el 2026-11-18 un pago de 1500.00 sin indicar fecha de cobro
- **THEN** recibe 201 y el pago cuenta en la caja del 18

#### Scenario: Cobro con fecha en un día cerrado, o anulación de un cobro cerrado (Error de Negocio)
- **GIVEN** el 2026-11-17 cerrado, con un pago `registrado` de 1500.00 de ese día
- **WHEN** recepción registra otro pago con fecha de cobro 2026-11-17, y luego anula el pago existente
- **THEN** recibe 409 `caja_cerrada` con el día "2026-11-17" las dos veces, no se crea ningún pago y el existente sigue `registrado`

#### Scenario: Corrección después de anular el cierre (Caso de Borde)
- **GIVEN** ese mismo pago y un admin que anula el cierre del 17 con motivo
- **WHEN** recepción anula el pago y vuelve a cerrar el 17
- **THEN** la anulación responde 200, el saldo vuelve a sumar 1500.00 y el nuevo cierre del 17 no incluye ese pago
