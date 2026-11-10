# Spec Delta: pagos/pagos-presupuesto

## Purpose
Registra los cobros de presupuestos aceptados por Mercado Pago o transferencia (RN-PG-01, US-010) con saldo y tope, y deja cada pago en una forma que la caja de C-12 pueda sumar por fecha de cobro. El pago de la seña sigue en `pagos/sena-turno`.

Las referencias `(Ox)` remiten a las decisiones de `design.md` (aprobadas el 2026-11-10). Todos los datos de ejemplo son sintéticos (R19).

## ADDED Requirements

### Requirement: Registro manual de un cobro
`POST /api/panel/pacientes/{id}/presupuestos/{presupuesto_id}/pagos` SHALL registrar un pago `registrado` con medio `mercadopago` o `transferencia`, monto mayor que 0 con dos decimales, fecha de cobro (por defecto, ahora; nunca futura) y referencia opcional (O12). Solo recepción y admin SHALL registrar, y solo sobre presupuestos `aceptado`; la odontóloga recibe 403 aunque sea su paciente (O4). No SHALL iniciarse ningún cobro online.

#### Scenario: Cobro parcial por transferencia (Happy Path)
- **GIVEN** un presupuesto `aceptado` con total a cargo 4000.00 y sin pagos
- **WHEN** recepción registra 1500.00 por `transferencia` con referencia "TRF-SINT-0001"
- **THEN** recibe 201 con el pago y saldo 2500.00, y queda auditoría `registro_pago_presupuesto` con el monto y el id, sin datos del paciente

#### Scenario: Presupuesto no aceptado, medio inválido o rol sin permiso (Error de Negocio)
- **WHEN** recepción registra un pago sobre un `presentado`, o con medio `efectivo`, o una odontóloga intenta registrar
- **THEN** recibe 409 `presupuesto_no_aceptado`, 422 o 403 respectivamente, y no se crea ningún pago

#### Scenario: Fecha de cobro futura (Caso de Borde)
- **WHEN** recepción registra un pago con fecha de cobro de mañana, y otro con la fecha de cobro igual a ahora
- **THEN** el primero responde 422 y el segundo 201

### Requirement: Los pagos no superan el total a cargo
La suma de pagos `registrado` de un presupuesto no SHALL superar su total a cargo de la o el paciente. Un pago que lo supere SHALL responder 409 `monto_excede_saldo` con el saldo vigente. Dos registros simultáneos SHALL evaluarse uno después del otro, nunca ambos contra el mismo saldo.

#### Scenario: Cancelar el saldo exacto (Happy Path)
- **GIVEN** saldo 2500.00
- **WHEN** recepción registra 2500.00 por `mercadopago`
- **THEN** recibe 201 y el saldo queda en 0.00

#### Scenario: Pago mayor al saldo (Error de Negocio)
- **GIVEN** saldo 2500.00
- **WHEN** recepción registra 2500.01
- **THEN** recibe 409 `monto_excede_saldo` con saldo 2500.00 y no se crea el pago

#### Scenario: Dos cobros simultáneos (Caso de Borde)
- **GIVEN** saldo 2500.00
- **WHEN** llegan a la vez dos registros de 2000.00
- **THEN** exactamente uno responde 201 y el otro 409 `monto_excede_saldo`, nunca 500, y el saldo queda en 500.00

### Requirement: Referencia de operación única por medio
Una referencia informada SHALL ser única entre los pagos `registrado` del mismo medio, para no registrar dos veces la misma operación de Mercado Pago o la misma transferencia. Una repetición SHALL responder 409 `referencia_duplicada`.

#### Scenario: Referencias distintas (Happy Path)
- **WHEN** recepción registra dos pagos por `mercadopago` con referencias "MP-SINT-0001" y "MP-SINT-0002"
- **THEN** ambos responden 201

#### Scenario: Misma operación cargada dos veces (Error de Negocio)
- **GIVEN** un pago `registrado` por `mercadopago` con referencia "MP-SINT-0001"
- **WHEN** recepción registra otro pago por `mercadopago` con la misma referencia, en cualquier presupuesto
- **THEN** recibe 409 `referencia_duplicada`

#### Scenario: Referencia de un pago anulado (Caso de Borde)
- **GIVEN** el pago con referencia "MP-SINT-0001" `anulado`
- **WHEN** recepción registra un pago nuevo con esa referencia por el mismo medio
- **THEN** responde 201

### Requirement: Anulación de un pago sin borrado
`POST .../pagos/{pago_id}/anular` SHALL pasar un pago `registrado` a `anulado` con un motivo de 3 a 300 caracteres, registrando quién y cuándo; el pago no SHALL borrarse y el saldo SHALL volver a sumar su monto. Un pago `anulado` no SHALL volver a `registrado`.

#### Scenario: Anular un cobro mal cargado (Happy Path)
- **GIVEN** un pago `registrado` de 1500.00 y saldo 2500.00
- **WHEN** recepción lo anula con motivo "cargado en el presupuesto equivocado"
- **THEN** recibe 200, el pago queda `anulado` con usuario y fecha, el saldo vuelve a 4000.00 y queda auditoría `anulacion_pago_presupuesto`

#### Scenario: Anular dos veces o sin motivo (Error de Negocio)
- **WHEN** recepción anula un pago ya `anulado`, o envía un motivo vacío
- **THEN** recibe 409 `transicion_invalida` o 422, y el pago no cambia

#### Scenario: Pago de otro presupuesto en la ruta (Caso de Borde)
- **WHEN** recepción anula `/presupuestos/{P1}/pagos/{pago_de_P2}`
- **THEN** recibe 404 y ningún pago cambia

### Requirement: Consulta de pagos y saldo para recepción
`GET .../presupuestos/{presupuesto_id}/pagos` SHALL devolver todos los pagos del presupuesto (registrados y anulados) con medio, monto, estado, fecha de cobro y referencia, más el total pagado y el saldo. Solo recepción y admin SHALL leerlos; la odontóloga no SHALL acceder a pagos, ni siquiera de sus pacientes (O3, O4).

#### Scenario: Pagos y saldo (Happy Path)
- **GIVEN** un pago registrado de 1500.00 y otro anulado de 500.00 sobre un total de 4000.00
- **WHEN** recepción consulta los pagos
- **THEN** recibe ambos pagos, total pagado 1500.00 y saldo 2500.00

#### Scenario: Odontóloga pide los pagos (Error de Negocio)
- **WHEN** la odontóloga de la paciente consulta los pagos de su presupuesto
- **THEN** recibe 403

#### Scenario: Presupuesto sin pagos (Caso de Borde)
- **WHEN** recepción consulta los pagos de un presupuesto `aceptado` recién creado
- **THEN** recibe lista vacía, total pagado 0.00 y saldo igual al total a cargo
