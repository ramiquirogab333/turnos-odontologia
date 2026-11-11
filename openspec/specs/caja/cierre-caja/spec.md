# caja/cierre-caja Specification

## Purpose
Permite que recepción y admin cierren la caja de cada día en un registro que no se modifica, comprueben que el cierre sigue coincidiendo con los movimientos y obtengan la liquidación por medio de pago para conciliar con Mercado Pago y el banco (US-007 CA-2, RN-GL-01).

Las referencias `(Ox)` remiten a las decisiones de `design.md`. Todos los datos de ejemplo son sintéticos (R19).

## Requirements

### Requirement: Cierre de un día terminado
`POST /api/panel/caja/cierres` con `dia` y `observaciones` opcionales (hasta 500 caracteres) SHALL crear el cierre de ese día con sus líneas por concepto y medio y sus totales, calculados por el servidor con las reglas de `caja/movimientos-caja`, y responder 201. Solo SHALL aceptarse un día terminado: desde las 00:15 del día siguiente, hora de la clínica (O1). No SHALL aceptar importes enviados por el cliente.

#### Scenario: Cierre del día anterior (Happy Path)
- **GIVEN** el 2026-11-17 con una seña de "3000.00" por `mercadopago` y un cobro de "1500.00" por `transferencia`, y son las 09:00 del 2026-11-18
- **WHEN** recepción cierra `dia=2026-11-17`
- **THEN** recibe 201 con dos líneas, `total_ingresos` "4500.00", `total_egresos` "0.00", `total_neto` "4500.00", el usuario y el instante del cierre

#### Scenario: Día en curso o importes enviados (Error de Negocio)
- **GIVEN** que son las 20:00 del 2026-11-17
- **WHEN** recepción cierra `dia=2026-11-17`, y luego envía un cierre del 16 con un campo `total_ingresos`
- **THEN** el primero responde 409 `dia_no_terminado` con el instante desde el que se puede cerrar, el segundo 422, y no se crea ningún cierre

#### Scenario: Límite del margen y día sin movimientos (Caso de Borde)
- **GIVEN** el 2026-11-17 sin movimientos
- **WHEN** recepción lo cierra a las 00:14:59 del 18 y otra vez a las 00:15:00
- **THEN** el primer intento responde 409 `dia_no_terminado` y el segundo 201 con cero líneas y los totales en "0.00"

### Requirement: Un solo cierre vigente por día
Cada día SHALL tener como máximo un cierre vigente. Un segundo cierre del mismo día SHALL rechazarse con 409 `dia_ya_cerrado`, también si dos pedidos llegan a la vez. Los días SHALL poder cerrarse en cualquier orden y un día sin cerrar SHALL seguir `abierto`.

#### Scenario: Días cerrados en otro orden (Happy Path)
- **GIVEN** el 2026-11-15 y el 2026-11-16 sin cerrar
- **WHEN** recepción cierra primero el 16 y después el 15
- **THEN** los dos cierres se crean con 201

#### Scenario: Día ya cerrado (Error de Negocio)
- **GIVEN** un cierre vigente del 2026-11-17
- **WHEN** admin cierra otra vez `dia=2026-11-17`
- **THEN** recibe 409 `dia_ya_cerrado` con el id del cierre vigente, y este no cambia

#### Scenario: Dos cierres simultáneos (Caso de Borde)
- **GIVEN** el 2026-11-17 sin cerrar
- **WHEN** recepción y admin envían el cierre de ese día al mismo tiempo
- **THEN** uno responde 201 y el otro 409 `dia_ya_cerrado`, y existe un único cierre vigente

### Requirement: El cierre no se modifica
Un cierre y sus líneas no SHALL poder editarse ni borrarse por la API, y la base SHALL rechazar cualquier cambio de sus importes, de su día y de sus líneas (O1). El único cambio permitido SHALL ser su anulación.

#### Scenario: Cierre consultado después (Happy Path)
- **GIVEN** un cierre del 2026-11-17 por "4500.00"
- **WHEN** recepción lo consulta una semana después
- **THEN** trae los mismos importes, líneas, usuario e instante que al crearse

#### Scenario: Intento de editar o borrar (Error de Negocio)
- **WHEN** admin envía `PUT`, `PATCH` o `DELETE` sobre `/api/panel/caja/cierres/{id}`
- **THEN** recibe 405 y el cierre no cambia

#### Scenario: Cambio directo en la base (Caso de Borde)
- **GIVEN** un cierre vigente con una línea de "3000.00"
- **WHEN** una sentencia intenta cambiar el total de esa línea o el `total_neto` del cierre en la base
- **THEN** la base la rechaza y los importes quedan como estaban

### Requirement: El cierre cuadra
`GET /api/panel/caja/cierres/{id}` SHALL informar `cuadra`: verdadero cuando la suma de las líneas coincide con los totales del cierre y cada línea coincide con los movimientos de ese día recalculados en el momento de la consulta (O2). Si no coincide SHALL informar `cuadra` falso y la lista de diferencias por concepto y medio, con el importe del cierre y el actual.

#### Scenario: Cierre que cuadra (Happy Path)
- **GIVEN** un cierre del 2026-11-17 por "4500.00" y ningún cambio posterior
- **WHEN** recepción lo consulta
- **THEN** recibe 200 con `cuadra` verdadero y la lista de diferencias vacía

#### Scenario: Movimiento alterado fuera de la aplicación (Error de Negocio)
- **GIVEN** un cierre del 2026-11-17 con una línea `pago_presupuesto`/`transferencia` de "1500.00", y un pago de ese día que después se anuló directamente en la base
- **WHEN** recepción consulta el cierre
- **THEN** recibe 200 con `cuadra` falso y la diferencia de esa línea: "1500.00" en el cierre y "0.00" actual

#### Scenario: Cambios posteriores que no mueven el día (Caso de Borde)
- **GIVEN** un cierre del 2026-11-17 que incluye una seña de "3000.00", cuyo turno se marcó `ausente` el 18 y otra cuya devolución se registró el 19
- **WHEN** recepción consulta el cierre del 17
- **THEN** `cuadra` sigue verdadero, porque ni el ausente ni la devolución cambian lo cobrado el 17

### Requirement: Un día cerrado no admite movimientos nuevos
Mientras un día tenga un cierre vigente, el sistema SHALL rechazar con 409 `caja_cerrada` cualquier operación que agregue, quite o cambie un movimiento con fecha en ese día (O2). La respuesta SHALL indicar el día cerrado. Los movimientos con fecha en días abiertos no SHALL verse afectados.

#### Scenario: Devolución con fecha de hoy (Happy Path)
- **GIVEN** el 2026-11-17 cerrado y una devolución pendiente de una seña cobrada ese día
- **WHEN** recepción registra la devolución con fecha 2026-11-19, día abierto
- **THEN** se acepta y figura como egreso del 19

#### Scenario: Devolución con fecha en un día cerrado (Error de Negocio)
- **GIVEN** el 2026-11-17 cerrado
- **WHEN** recepción registra una devolución con fecha 2026-11-17
- **THEN** recibe 409 `caja_cerrada` con el día "2026-11-17" y la devolución sigue pendiente

#### Scenario: Cierre y movimiento a la vez (Caso de Borde)
- **GIVEN** el 2026-11-17 sin cerrar
- **WHEN** el cierre de ese día y el registro de un movimiento con fecha 17 llegan al mismo tiempo
- **THEN** o el movimiento entra y el cierre lo incluye, o el movimiento recibe 409 `caja_cerrada`; nunca queda un movimiento del 17 fuera de su cierre

### Requirement: Anulación de un cierre
`POST /api/panel/caja/cierres/{id}/anular` con un motivo de 3 a 300 caracteres SHALL pasar un cierre vigente a `anulado`, registrando quién y cuándo, sin borrarlo, y dejar el día `abierto` para corregir y volver a cerrar. Solo `admin` SHALL poder anular (O15). Un cierre `anulado` no SHALL volver a `vigente`.

#### Scenario: Admin anula y se vuelve a cerrar (Happy Path)
- **GIVEN** un cierre vigente del 2026-11-17
- **WHEN** admin lo anula con motivo "cobro cargado en el presupuesto equivocado" y, tras la corrección, recepción cierra de nuevo el 17
- **THEN** la anulación responde 200, el nuevo cierre 201, y existen dos cierres del 17: uno `anulado` y uno `vigente`

#### Scenario: Recepción intenta anular, o falta el motivo (Error de Negocio)
- **WHEN** un usuario con solo el rol `recepcion` anula un cierre, y luego admin lo anula con un motivo vacío
- **THEN** recibe 403 y 422 respectivamente, y el cierre sigue `vigente`

#### Scenario: Anular dos veces o un cierre inexistente (Caso de Borde)
- **WHEN** admin anula un cierre ya `anulado`, y luego un id que no existe
- **THEN** recibe 409 `transicion_invalida` y 404 respectivamente

### Requirement: Consulta de cierres
`GET /api/panel/caja/cierres?desde=&hasta=` SHALL listar los cierres cuyo día está en el rango (hasta 366 días), del más reciente al más antiguo, con día, estado, totales, usuario e instante. Los anulados SHALL figurar con su motivo.

#### Scenario: Cierres del mes (Happy Path)
- **GIVEN** cierres vigentes del 2026-11-16 y 2026-11-17
- **WHEN** recepción lista `desde=2026-11-01&hasta=2026-11-30`
- **THEN** recibe los dos, primero el del 17

#### Scenario: Rango inválido (Error de Negocio)
- **WHEN** recepción lista con `hasta` anterior a `desde`, o un rango de 400 días
- **THEN** recibe 422

#### Scenario: Día con un cierre anulado y otro vigente (Caso de Borde)
- **GIVEN** el 2026-11-17 con un cierre `anulado` y otro `vigente`
- **WHEN** recepción lista ese día
- **THEN** recibe los dos, cada uno con su estado, y el anulado con su motivo

### Requirement: Liquidación por medio de pago
`GET /api/panel/caja/liquidacion?desde=&hasta=` SHALL consolidar los cierres vigentes del rango y devolver, por medio de pago, los ingresos, los egresos y el neto, más el detalle por concepto y la lista de días del rango sin cierre vigente (O3). Los cierres anulados y los días abiertos no SHALL sumar.

#### Scenario: Liquidación de dos días (Happy Path)
- **GIVEN** cierres vigentes del 16 ("3000.00" por `mercadopago`) y del 17 ("3000.00" por `mercadopago` y "1500.00" por `transferencia`)
- **WHEN** recepción pide la liquidación del 16 al 17
- **THEN** recibe `mercadopago` neto "6000.00", `transferencia` neto "1500.00" y ningún día sin cerrar

#### Scenario: La odontóloga pide la liquidación (Error de Negocio)
- **WHEN** un usuario con solo el rol `odontologo` pide la liquidación
- **THEN** recibe 403 y ningún importe

#### Scenario: Días sin cerrar y devoluciones (Caso de Borde)
- **GIVEN** del 16 al 18 solo el 17 cerrado, con ingresos por `transferencia` de "1500.00" y una devolución de "500.00" por el mismo medio
- **WHEN** recepción pide la liquidación del 16 al 18
- **THEN** `transferencia` informa ingresos "1500.00", egresos "500.00" y neto "1000.00", y los días 16 y 18 figuran sin cerrar

### Requirement: Auditoría del cierre
Cada cierre y cada anulación aceptados SHALL dejar, en la misma transacción, un registro de auditoría con el usuario, la acción (`cierre_caja` o `anulacion_cierre_caja`), el id del cierre, el día y los totales, sin datos personales (RN-GL-01, R19). Una operación rechazada no SHALL dejar registro.

#### Scenario: Cierre auditado (Happy Path)
- **WHEN** recepción cierra el 2026-11-17
- **THEN** existe un registro `cierre_caja` con su `usuario_id`, el día y el total neto

#### Scenario: Cierre rechazado (Error de Negocio)
- **WHEN** un cierre se rechaza por `dia_no_terminado` o `dia_ya_cerrado`
- **THEN** no queda ningún registro nuevo de auditoría

#### Scenario: Anulación auditada sin el texto del motivo (Caso de Borde)
- **GIVEN** una anulación con motivo "error de Lucía Ejemplo"
- **WHEN** se inspecciona el registro `anulacion_cierre_caja`
- **THEN** trae el id del cierre y el día, y no contiene el texto del motivo, que queda solo en el cierre

### Requirement: Pantalla de cierre de caja
La pantalla de caja SHALL ofrecer «Cerrar caja» solo para días terminados y sin cierre vigente, pedir confirmación mostrando los totales que se van a congelar, y mostrar en un día cerrado quién y cuándo lo cerró y si cuadra. A un admin SHALL ofrecerle «Anular cierre» con motivo obligatorio. SHALL funcionar a 360 px (R3).

#### Scenario: Cierre desde la pantalla (Happy Path)
- **GIVEN** recepción en un viewport de 360 px mirando la caja de ayer, sin cerrar
- **WHEN** toca «Cerrar caja» y confirma
- **THEN** ve el día como cerrado, con su nombre de usuario, la hora y el aviso "El cierre cuadra"

#### Scenario: Día en curso (Error de Negocio)
- **WHEN** recepción mira la caja de hoy
- **THEN** no ve «Cerrar caja» sino el aviso de que el día se podrá cerrar desde mañana a las 00:15

#### Scenario: Cierre que no cuadra y anulación (Caso de Borde)
- **GIVEN** un admin mirando un cierre que no cuadra
- **WHEN** abre el día
- **THEN** ve el aviso "El cierre no cuadra" con las diferencias y la acción «Anular cierre», que recepción no ve
