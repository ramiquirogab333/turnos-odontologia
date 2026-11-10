# clinica/presupuestos Specification

## Purpose
Permite armar presupuestos de tratamiento por paciente cuyo importe a cargo de la o el paciente descuenta la cobertura de su obra social según el nomenclador AR precargado (RN-PG-02, US-009 CA-2), con estados y un congelamiento que los vuelve inalterables al presentarse.

Las referencias `(Ox)` remiten a las decisiones de `design.md` (aprobadas el 2026-11-10). Los montos son en pesos, con dos decimales (R4). Todos los datos de ejemplo son sintéticos (R19) y usan el seed de C-02 (Limpieza dental $25.000,00; Swiss Medical 90 %; Omint 85 %; Particular 0 %).

## Requirements

### Requirement: Cálculo de cada línea con la cobertura del nomenclador
El servidor SHALL calcular cada línea: bruto = precio base del tratamiento × cantidad; cobertura = bruto × `cobertura_porcentaje` / 100 redondeado half-up a centavos; diferencial = `arancel_diferencial` × cantidad; a cargo de la o el paciente = bruto − cobertura + diferencial (O9). Sin obra social o sin fila de nomenclador para ese tratamiento, la cobertura y el diferencial SHALL ser 0 y la línea SHALL marcarse `sin_cobertura`. El cliente no SHALL poder enviar importes.

#### Scenario: Limpieza con Swiss Medical (Happy Path)
- **GIVEN** "Lucía Ejemplo" con Swiss Medical y el seed aplicado
- **WHEN** recepción crea un presupuesto con una línea "Limpieza dental" × 1
- **THEN** la línea muestra bruto 25000.00, cobertura 22500.00, diferencial 0.00 y a cargo de la paciente 2500.00

#### Scenario: Importes enviados por el cliente (Error de Negocio)
- **WHEN** recepción envía una línea con `importe_paciente` o `precio_unitario`
- **THEN** recibe 422 y no se crea el presupuesto

#### Scenario: Redondeo half-up y diferencial por unidad (Caso de Borde)
- **GIVEN** un tratamiento sintético de precio 10.10 con Omint al 85 %, y otro de 25000.00 con cobertura 90 % y `arancel_diferencial` 1500.00
- **WHEN** se presupuestan el primero × 1 y el segundo × 2
- **THEN** la primera línea da cobertura 8.59 y a cargo 1.51, y la segunda bruto 50000.00, cobertura 45000.00, diferencial 3000.00 y a cargo 8000.00

### Requirement: Totales del presupuesto
El presupuesto SHALL exponer subtotal, cobertura total, diferencial total y total a cargo de la o el paciente, cada uno igual a la suma de las líneas ya redondeadas (O9). La base de datos SHALL rechazar un total que no cumpla total = subtotal − cobertura + diferencial o que sea negativo.

#### Scenario: Dos líneas (Happy Path)
- **GIVEN** paciente con Swiss Medical
- **WHEN** se presupuestan "Limpieza dental" × 1 y "Consulta odontológica" × 1 ($15.000,00)
- **THEN** subtotal 40000.00, cobertura 36000.00, diferencial 0.00 y total a cargo 4000.00

#### Scenario: Totales inconsistentes en la base (Error de Negocio)
- **WHEN** se intenta persistir directamente un presupuesto con total a cargo distinto de subtotal − cobertura + diferencial
- **THEN** la base lo rechaza por `CHECK` y no queda nada guardado

#### Scenario: Paciente particular (Caso de Borde)
- **GIVEN** un paciente sin obra social
- **WHEN** se presupuesta "Limpieza dental" × 1
- **THEN** cobertura 0.00, total a cargo 25000.00 y la línea marcada `sin_cobertura`

### Requirement: Alta y edición en borrador
`POST /api/panel/pacientes/{id}/presupuestos` SHALL crear un presupuesto `borrador` con 1 a 50 líneas (tratamiento, cantidad 1–99, pieza FDI y cara opcionales) y la obra social activa del paciente, salvo que se indique otra activa. `PUT` sobre un `borrador` SHALL reemplazar líneas, obra social y notas y recalcular todo con los valores vigentes. Solo recepción y admin SHALL escribir; la odontóloga SHALL recibir 403 en el alta, la edición y cualquier transición, incluso sobre sus pacientes (O4).

#### Scenario: Corregir la cantidad en borrador (Happy Path)
- **GIVEN** un borrador con "Limpieza dental" × 1
- **WHEN** recepción lo reemplaza por "Limpieza dental" × 2
- **THEN** recibe 200 con los importes recalculados y queda auditoría `edicion_presupuesto`

#### Scenario: Editar un presentado o la odontóloga intenta crear (Error de Negocio)
- **GIVEN** un presupuesto `presentado` de "Lucía Ejemplo", que tiene un turno `atendido` con la "Dra. Ana Ficticia"
- **WHEN** recepción envía un `PUT` sobre ese presupuesto, o la Dra. Ana Ficticia intenta crear un presupuesto nuevo para Lucía o presentar uno en borrador
- **THEN** recibe 409 `presupuesto_no_editable` o 403 respectivamente, nada cambia y no queda auditoría de escritura

#### Scenario: Tratamiento inexistente o lista vacía (Caso de Borde)
- **WHEN** recepción crea un presupuesto sin líneas, o con un `tratamiento_id` inexistente
- **THEN** recibe 422 y no se crea nada

### Requirement: Estados del presupuesto
Las transiciones SHALL ser `borrador → presentado`, `presentado → aceptado | rechazado`, y `borrador | presentado | aceptado → anulado` con motivo; `aceptado → anulado` solo sin pagos `registrado` (O10). Cualquier otra SHALL responder 409 `transicion_invalida`. Cada transición aceptada SHALL quedar auditada.

#### Scenario: Presentar y aceptar (Happy Path)
- **WHEN** recepción presenta un borrador y luego lo acepta
- **THEN** ambas responden 200 y el presupuesto queda `aceptado` con la fecha de cada paso

#### Scenario: Transición no permitida (Error de Negocio)
- **WHEN** recepción intenta aceptar un `borrador` o volver a `borrador` un `rechazado`
- **THEN** recibe 409 `transicion_invalida` y el estado no cambia

#### Scenario: Anular un aceptado con pagos (Caso de Borde)
- **GIVEN** un presupuesto `aceptado` con un pago `registrado`
- **WHEN** recepción intenta anularlo
- **THEN** recibe 409 `presupuesto_con_pagos`; tras anular ese pago, la anulación del presupuesto se acepta

### Requirement: El presupuesto presentado queda congelado
Al presentarse, el presupuesto SHALL recalcularse una última vez y desde entonces sus líneas, precios, porcentajes e importes SHALL quedar fijos (O10): cambiar después el precio del tratamiento, el nomenclador o la obra social del paciente no SHALL alterarlo.

#### Scenario: Cambia el precio después de presentar (Happy Path)
- **GIVEN** un presupuesto presentado con "Limpieza dental" a 25000.00
- **WHEN** el admin sube el precio del tratamiento a 30000.00
- **THEN** el presupuesto sigue mostrando 25000.00

#### Scenario: Recalcular un presentado (Error de Negocio)
- **WHEN** recepción intenta editar líneas u obra social de un presupuesto presentado
- **THEN** recibe 409 `presupuesto_no_editable`

#### Scenario: Cambia el nomenclador con un borrador abierto (Caso de Borde)
- **GIVEN** un borrador calculado con cobertura 90 %
- **WHEN** el nomenclador pasa a 80 % y recepción presenta el borrador
- **THEN** el presupuesto presentado queda calculado con 80 %

### Requirement: Consulta de presupuestos por rol
`GET /api/panel/pacientes/{id}/presupuestos` y `GET .../presupuestos/{presupuesto_id}` SHALL devolver los presupuestos del paciente con líneas y totales. La odontóloga SHALL poder leerlos (solo lectura) únicamente de sus pacientes (al menos un turno `atendido` con su profesional, O2) y sin pagos ni saldo (O3, O4). Un presupuesto de otro paciente pedido por la ruta de este SHALL responder 404.

#### Scenario: Odontóloga lee el plan de su paciente (Happy Path)
- **WHEN** la odontóloga de "Lucía Ejemplo" consulta sus presupuestos
- **THEN** recibe 200 con líneas y totales, sin pagos ni saldo, y queda auditoría `lectura_presupuesto`

#### Scenario: Odontóloga y paciente ajeno (Error de Negocio)
- **WHEN** una odontóloga consulta presupuestos de un paciente que solo tiene con ella turnos `reservado` o `confirmado`, o que fue atendido por otra profesional
- **THEN** recibe 403 `paciente_ajeno`

#### Scenario: Presupuesto de otro paciente (Caso de Borde)
- **WHEN** recepción pide `/pacientes/{id_A}/presupuestos/{presupuesto_de_B}`
- **THEN** recibe 404

### Requirement: Sin facturación electrónica
Ningún presupuesto ni pago SHALL emitir comprobantes fiscales ni comunicarse con ARCA (RN-PG-03). La respuesta no SHALL presentar el presupuesto como factura.

#### Scenario: Aceptar un presupuesto (Happy Path)
- **WHEN** recepción acepta un presupuesto
- **THEN** no se realiza ninguna llamada externa de facturación y la respuesta no incluye número de comprobante fiscal

#### Scenario: Pedido de factura (Error de Negocio)
- **WHEN** un cliente envía un campo `emitir_factura` al presentar
- **THEN** recibe 422

#### Scenario: Presupuesto con total cero (Caso de Borde)
- **GIVEN** un presupuesto con cobertura del 100 % y sin diferencial
- **WHEN** se presenta y se acepta
- **THEN** ambos pasos se aceptan con total a cargo 0.00 y sin comprobante
