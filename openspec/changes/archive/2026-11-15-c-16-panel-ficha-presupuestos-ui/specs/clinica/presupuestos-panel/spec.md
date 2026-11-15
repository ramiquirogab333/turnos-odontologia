# Spec Delta

## Purpose

Pantallas del panel para que recepción y admin armen presupuestos con cobertura de obra social, los lleven por sus estados y registren o anulen sus cobros, y para que la odontóloga los consulte sin pagos ni saldo.

## ADDED Requirements

### Requirement: Lista de presupuestos por rol
La pestaña Presupuestos SHALL listar los presupuestos del paciente del más reciente al más antiguo con estado como texto, obra social o "Sin obra social", total a cargo del paciente y fecha. Recepción y admin SHALL ver además total pagado y saldo de los aceptados. La odontóloga SHALL verlos sin pagos, sin saldo y sin ninguna acción.

#### Scenario: Recepción ve sus presupuestos (Happy Path)
- **GIVEN** "Lucía Ejemplo" con un presupuesto `aceptado` de total "$ 2.500" con un cobro de "$ 1.000", y uno `borrador`
- **WHEN** recepción abre la pestaña Presupuestos
- **THEN** ve los dos, el aceptado con "Pagado $ 1.000 · Saldo $ 1.500" y el borrador con "Editar"

#### Scenario: La odontóloga no ve pagos (Error de Negocio)
- **GIVEN** la Dra. Ana Ficticia con acceso a Lucía
- **WHEN** abre la pestaña Presupuestos
- **THEN** ve los dos presupuestos con sus líneas e importes, y en ningún lugar de la página aparecen pagos, saldo ni botones de acción

#### Scenario: Sin presupuestos (Caso de Borde)
- **WHEN** recepción abre la pestaña de un paciente sin presupuestos
- **THEN** ve "Este paciente todavía no tiene presupuestos" con "Nuevo presupuesto"

### Requirement: Armado de un presupuesto en borrador
Recepción y admin SHALL poder crear y editar un borrador con 1 a 50 líneas (tratamiento activo, cantidad 1–99, pieza FDI y cara opcionales; la cara exige la pieza), la obra social del paciente por defecto, otra activa o "Sin obra social" (particular), y notas (≤ 1000). Los importes SHALL ser siempre los que devuelve el servidor (RN-PG-04): el panel no SHALL calcularlos.

#### Scenario: Borrador con cobertura (Happy Path)
- **GIVEN** Lucía con Swiss Medical (cobertura sintética del 90 %) y el tratamiento "Limpieza dental" de precio base "$ 25.000"
- **WHEN** recepción agrega una línea de "Limpieza dental" × 1 y elige "Guardar borrador"
- **THEN** ve la línea con bruto "$ 25.000", cobertura "$ 22.500" y a cargo del paciente "$ 2.500", tal como los devolvió el servidor

#### Scenario: Obra social desactivada (Error de Negocio)
- **GIVEN** que la obra social elegida se desactivó después de abrir el formulario
- **WHEN** recepción guarda el borrador y el servidor responde 422 `obra_social_inactiva`
- **THEN** ve "Esa obra social ya no está activa. Elegí otra o «Sin obra social»", la lista se actualiza y lo cargado se conserva

#### Scenario: Línea sin cobertura en el nomenclador (Caso de Borde)
- **GIVEN** un tratamiento sin fila de nomenclador para la obra social del presupuesto
- **WHEN** recepción guarda el borrador
- **THEN** la línea muestra cobertura "$ 0" con la nota "Sin cobertura para esta prestación"

### Requirement: Estados del presupuesto desde el panel
Recepción y admin SHALL poder presentar un borrador, aceptar o rechazar uno presentado y anular uno borrador, presentado o aceptado con un motivo de 3 a 300 caracteres (RN-PG-05). Cada acción SHALL pedir confirmación, y presentar SHALL avisar que los importes quedan congelados. Solo SHALL ofrecerse las acciones válidas para el estado actual.

#### Scenario: Presentar y aceptar (Happy Path)
- **GIVEN** un borrador de Lucía
- **WHEN** recepción elige "Presentar", confirma el aviso "Los importes quedan fijos desde ahora", y luego "Aceptar" y confirma
- **THEN** el presupuesto queda `aceptado` y aparece "Registrar cobro"

#### Scenario: Anular un aceptado con cobros (Error de Negocio)
- **GIVEN** un presupuesto `aceptado` con un cobro registrado
- **WHEN** recepción elige "Anular", escribe "Error de carga (sintético)" y el servidor responde 409 `presupuesto_con_pagos`
- **THEN** ve "No se puede anular un presupuesto con cobros registrados. Anulá antes los cobros" y el presupuesto sigue `aceptado`

#### Scenario: Otra persona cambió el estado antes (Caso de Borde)
- **GIVEN** recepción y admin con el mismo presupuesto `presentado` abierto, y admin ya lo rechazó
- **WHEN** recepción elige "Aceptar" y el servidor responde 409 `transicion_invalida`
- **THEN** ve "El presupuesto cambió de estado mientras lo mirabas" y la lista se actualiza mostrándolo `rechazado`

### Requirement: Presupuesto presentado de solo lectura
Un presupuesto que no está en borrador SHALL mostrarse sin edición de líneas, obra social ni notas; si al editar un borrador el servidor responde 409 `presupuesto_no_editable`, el panel SHALL explicarlo y recargar el presupuesto.

#### Scenario: Ver un presupuesto presentado (Happy Path)
- **WHEN** recepción abre un presupuesto `presentado`
- **THEN** ve sus líneas e importes congelados, sin "Editar"

#### Scenario: El borrador se presentó mientras se editaba (Error de Negocio)
- **GIVEN** recepción editando un borrador que admin acaba de presentar
- **WHEN** recepción elige "Guardar borrador" y el servidor responde 409 `presupuesto_no_editable`
- **THEN** ve "Este presupuesto ya fue presentado y no se puede editar", el presupuesto se recarga como `presentado` y lo cargado no se envía

#### Scenario: Tratamiento desactivado en un borrador existente (Caso de Borde)
- **GIVEN** un borrador con una línea de un tratamiento que después se desactivó
- **WHEN** recepción abre el borrador para editarlo
- **THEN** la línea muestra el tratamiento con "(inactivo)" y el selector de líneas nuevas no lo ofrece

### Requirement: Registro de cobros de un presupuesto aceptado
Recepción y admin SHALL poder registrar un cobro sobre un presupuesto aceptado con medio (Mercado Pago o transferencia), monto mayor que 0 y hasta el saldo (sugerido por defecto), fecha de cobro (hoy por defecto, nunca futura) y referencia opcional (≤ 64). El panel SHALL traducir los rechazos de RN-PG-06 a mensajes con qué pasó y cómo seguir.

#### Scenario: Cobro parcial (Happy Path)
- **GIVEN** un presupuesto `aceptado` con saldo "$ 2.500"
- **WHEN** recepción registra "$ 1.000" por transferencia con referencia "TRF-0001"
- **THEN** ve el cobro en la lista y "Pagado $ 1.000 · Saldo $ 1.500"

#### Scenario: Monto mayor que el saldo (Error de Negocio)
- **GIVEN** saldo "$ 1.500" en pantalla y otra persona registró "$ 1.000" antes
- **WHEN** recepción registra "$ 1.500" y el servidor responde 409 `monto_excede_saldo` con saldo "500.00"
- **THEN** ve "El monto supera el saldo. El saldo actual es $ 500", el monto sugerido pasa a "$ 500" y no se registra nada

#### Scenario: Día de caja cerrado o referencia repetida (Caso de Borde)
- **WHEN** recepción registra un cobro con fecha de un día cuya caja está cerrada (409 `caja_cerrada`), y otro con una referencia ya usada en el mismo medio (409 `referencia_duplicada`)
- **THEN** ve "La caja de ese día está cerrada. Un admin tiene que anular el cierre para registrar este cobro" en el primero y "Ya hay un cobro registrado con esa referencia" junto al campo en el segundo; no se registra ninguno

### Requirement: Anulación de cobros
Recepción y admin SHALL poder anular un cobro registrado con motivo (3 a 300 caracteres), con confirmación; el cobro anulado SHALL seguir visible como "Anulado" con su motivo y el saldo SHALL actualizarse. Nunca SHALL ofrecerse borrar un cobro.

#### Scenario: Anular un cobro cargado por error (Happy Path)
- **GIVEN** un cobro de "$ 1.000" registrado hoy
- **WHEN** recepción elige "Anular cobro", escribe "Monto equivocado (sintético)" y confirma
- **THEN** el cobro queda "Anulado · Monto equivocado (sintético)" y el saldo vuelve a sumar "$ 1.000"

#### Scenario: Cobro de un día cerrado (Error de Negocio)
- **GIVEN** un cobro de un día con caja cerrada
- **WHEN** recepción lo anula y el servidor responde 409 `caja_cerrada`
- **THEN** ve el mensaje de caja cerrada y el cobro sigue registrado

#### Scenario: Motivo demasiado corto (Caso de Borde)
- **WHEN** recepción escribe "ok" como motivo
- **THEN** "Anular cobro" queda deshabilitado con "Escribí al menos 3 caracteres" y nada se envía

### Requirement: Presupuestos a 360 px
La lista, el formulario de líneas y los cobros SHALL funcionar a 360 px sin desplazamiento horizontal: cada línea y cada cobro en una tarjeta de una columna con importes alineados, y acciones de al menos 48 px (R3). Los montos SHALL mostrarse en pesos con separador de miles y sin decimales cuando son cero.

#### Scenario: Presupuesto de 3 líneas a 360 px (Happy Path)
- **GIVEN** un viewport de 360 × 800 y un borrador de 3 líneas
- **WHEN** recepción lo abre y lo presenta
- **THEN** el ancho del documento no supera la ventana y todas las acciones miden al menos 48 px de alto

#### Scenario: Rechazo de cobro a 360 px (Error de Negocio)
- **GIVEN** un viewport de 360 × 800
- **WHEN** un cobro responde 409 `monto_excede_saldo`
- **THEN** el mensaje y el saldo se leen completos sin desplazamiento horizontal

#### Scenario: Importe máximo (Caso de Borde)
- **GIVEN** una línea con total "9999999999.99"
- **WHEN** se muestra a 360 px
- **THEN** se lee "$ 9.999.999.999,99" completo, cortando la fila si hace falta, sin desbordar
