# Spec Delta: pagos/devoluciones-sena

## Purpose
Da a recepción y admin el lugar donde resolver los pagos de seña que quedaron sin cerrar desde C-06: los que están `en_revision` (se acreditan o se rechazan) y los que hay que devolver (`a_reembolsar`), dejando constancia de cada devolución hecha a mano (RN-SN-04, RN-SN-05, RN-SN-09, RN-SN-10). El sistema no devuelve dinero por sí mismo.

Las referencias `(Ox)` remiten a las decisiones de `design.md`. Todos los datos de ejemplo son sintéticos (R19).

## ADDED Requirements

### Requirement: Lista de pagos de seña pendientes de resolver
`GET /api/panel/caja/pendientes` SHALL devolver los pagos `en_revision` y las devoluciones pendientes: las señas `a_reembolsar` y los pagos excedentes de Mercado Pago. Cada elemento SHALL traer su tipo, importe, medio, id del pago en la pasarela si existe, el turno y su estado, y desde cuándo está pendiente, del más antiguo al más nuevo. No SHALL contener nombre ni teléfono (R19).

#### Scenario: Una revisión y una devolución (Happy Path)
- **GIVEN** un pago `en_revision` informado por "2999.99" y una seña `a_reembolsar` de "3000.00" por una cancelación con 48 horas
- **WHEN** recepción consulta los pendientes
- **THEN** recibe 200 con un elemento en revisión por "2999.99" y una devolución pendiente de tipo `sena` por "3000.00"

#### Scenario: La odontóloga pide los pendientes (Error de Negocio)
- **WHEN** un usuario con solo el rol `odontologo` consulta los pendientes
- **THEN** recibe 403 y ningún dato

#### Scenario: Revisión de una pre-reserva ya vencida (Caso de Borde)
- **GIVEN** un pago `en_revision` cuyo turno venció y quedó `cancelado`
- **WHEN** recepción consulta los pendientes
- **THEN** el pago sigue en la lista de revisión, con el estado `cancelado` del turno, hasta que alguien lo resuelva

### Requirement: Rechazar un pago en revisión
`POST /api/panel/caja/revisiones/{pago_id}/rechazar` SHALL pasar un pago `en_revision` a `a_reembolsar`, por el importe que informó la pasarela, sin acreditarlo ni cambiar el turno (O6, RN-SN-09). Aceptarlo SHALL seguir haciéndose con la acreditación manual existente. Un pago que no está `en_revision` SHALL responder 409 `no_esta_en_revision`.

#### Scenario: Rechazo de un pago con otro importe (Happy Path)
- **GIVEN** un pago `en_revision` de una seña de "3000.00" informado por "2999.99", con el turno `en_espera`
- **WHEN** recepción lo rechaza
- **THEN** recibe 200, el pago queda `a_reembolsar` por "2999.99", el turno sigue `en_espera` con su vencimiento y no ocupa agenda (R8)

#### Scenario: Pago que no está en revisión (Error de Negocio)
- **WHEN** recepción rechaza un pago `acreditado`, y luego un id que no existe
- **THEN** recibe 409 `no_esta_en_revision` y 404 respectivamente, y ningún pago cambia

#### Scenario: Rechazo y acreditación simultáneos (Caso de Borde)
- **GIVEN** un pago `en_revision` con el turno vigente
- **WHEN** recepción lo rechaza y admin lo acredita al mismo tiempo
- **THEN** gana uno solo: el pago queda `a_reembolsar` o `acreditado`, nunca los dos, y el otro pedido no cambia nada

### Requirement: Registro de la devolución de una seña
`POST /api/panel/caja/devoluciones/senas/{pago_id}` con una referencia de 3 a 64 caracteres y una fecha opcional SHALL pasar una seña `a_reembolsar` a `reembolsado`, registrando quién, cuándo y la referencia (O5). El importe SHALL ser el recibido y no SHALL poder enviarse. La fecha SHALL ser por defecto ahora, nunca futura ni anterior a la recepción del dinero.

#### Scenario: Devolución de una cancelación (Happy Path)
- **GIVEN** una seña `a_reembolsar` de "3000.00" por `transferencia`
- **WHEN** recepción registra la devolución con referencia "DEV-SINT-0001"
- **THEN** recibe 200, el pago queda `reembolsado` con su usuario, la fecha y la referencia, y deja de figurar entre los pendientes

#### Scenario: Seña que no está por devolverse (Error de Negocio)
- **WHEN** recepción registra la devolución de un pago `acreditado`, de uno `no_reembolsado` o de uno `en_revision`
- **THEN** recibe 409 `no_es_devolucion_pendiente` en los tres casos y ningún pago cambia (R9)

#### Scenario: Fecha futura, importe enviado o sin referencia (Caso de Borde)
- **WHEN** recepción envía una fecha de mañana, o un campo `monto`, o una referencia de dos caracteres
- **THEN** recibe 422 en los tres casos y la seña sigue `a_reembolsar`

### Requirement: Una seña reembolsada es un estado final
Un pago `reembolsado` no SHALL volver a ningún otro estado ni devolverse otra vez, y su turno no SHALL revivir. Dos registros simultáneos de la misma devolución SHALL dejar una sola.

#### Scenario: Consulta posterior (Happy Path)
- **GIVEN** una seña `reembolsado` con referencia "DEV-SINT-0001"
- **WHEN** recepción consulta la agenda del día de ese turno
- **THEN** el turno sigue `cancelado` y su seña figura como devuelta

#### Scenario: Segunda devolución (Error de Negocio)
- **WHEN** recepción registra otra vez la devolución de una seña `reembolsado`
- **THEN** recibe 409 `no_es_devolucion_pendiente` y la referencia original no cambia

#### Scenario: Dos registros a la vez (Caso de Borde)
- **GIVEN** una seña `a_reembolsar`
- **WHEN** recepción y admin registran su devolución al mismo tiempo
- **THEN** uno responde 200 y el otro 409, y la caja muestra un único egreso

### Requirement: Devolución de pagos excedentes de Mercado Pago
Un pago aprobado de Mercado Pago distinto del que se aplicó a la seña (RN-SN-10) SHALL figurar como devolución pendiente de tipo `excedente_mp` y resolverse con `POST /api/panel/caja/devoluciones/excedentes/{id}`, con las mismas reglas de referencia y fecha. No SHALL cambiar el estado de la seña ni del turno, ni sumar en los totales de la caja (O5).

#### Scenario: Pago duplicado devuelto (Happy Path)
- **GIVEN** una seña `acreditado` de "3000.00" y un segundo pago aprobado por "3000.00" registrado para devolver
- **WHEN** recepción registra la devolución del excedente con referencia "DEV-SINT-0002"
- **THEN** recibe 200, el excedente queda devuelto, la seña sigue `acreditado` y el turno `reservado`

#### Scenario: Excedente ya devuelto o inexistente (Error de Negocio)
- **WHEN** recepción registra la devolución de un excedente ya devuelto, y luego de un id que no existe
- **THEN** recibe 409 `no_es_devolucion_pendiente` y 404 respectivamente

#### Scenario: Excedente sin importe informado (Caso de Borde)
- **GIVEN** un excedente del que la pasarela no informó el importe
- **WHEN** recepción consulta los pendientes
- **THEN** el elemento trae el importe vacío y la marca `importe_a_verificar`, y se puede registrar su devolución igual

### Requirement: Solo recepción y admin resuelven pagos y todo queda auditado
Las operaciones de este spec SHALL requerir rol `recepcion` o `admin`. Cada rechazo y cada devolución aceptados SHALL dejar, en la misma transacción, un registro de auditoría con el usuario, la acción (`sena_revision_rechazada`, `devolucion_sena_registrada` o `devolucion_excedente_registrada`), el pago, el turno y el importe, sin datos personales (RN-GL-01, R19).

#### Scenario: Devolución auditada (Happy Path)
- **WHEN** recepción registra la devolución de una seña de "3000.00"
- **THEN** existe un registro `devolucion_sena_registrada` con su `usuario_id`, el id del pago y "3000.00"

#### Scenario: La odontóloga intenta resolver (Error de Negocio)
- **WHEN** un usuario con solo el rol `odontologo` rechaza una revisión o registra una devolución
- **THEN** recibe 403, el pago no cambia y no queda registro de auditoría

#### Scenario: Operación rechazada (Caso de Borde)
- **WHEN** una devolución se rechaza por `no_es_devolucion_pendiente` o `caja_cerrada`
- **THEN** no queda ningún registro nuevo de auditoría

### Requirement: Pantalla de pendientes de la seña
La pantalla de caja SHALL listar los pagos en revisión y las devoluciones pendientes con su importe y su turno, y ofrecer «Acreditar» y «Rechazar» en las revisiones y «Registrar devolución» en las devoluciones, cada una con confirmación que diga qué pasa con el dinero y con el turno. SHALL funcionar a 360 px (R3).

#### Scenario: Registrar una devolución desde la pantalla (Happy Path)
- **GIVEN** recepción en un viewport de 360 px con una devolución pendiente de "$ 3.000,00"
- **WHEN** toca «Registrar devolución», escribe la referencia "DEV-SINT-0001" y confirma
- **THEN** la devolución desaparece de los pendientes y el día muestra el egreso

#### Scenario: Referencia faltante (Error de Negocio)
- **WHEN** recepción confirma sin escribir la referencia
- **THEN** ve "Escribí la referencia de la devolución (el número de operación)" y nada se envía

#### Scenario: Sin pendientes (Caso de Borde)
- **WHEN** no hay pagos en revisión ni devoluciones pendientes
- **THEN** la sección dice "No hay pagos por resolver"
