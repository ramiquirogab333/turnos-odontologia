# caja/movimientos-caja Specification

## Purpose
Muestra a recepción y admin el dinero de cada día de la clínica: las señas recibidas y los cobros de presupuestos, menos las devoluciones hechas, por concepto y medio de pago (US-007, Flujo 5). Es la base sobre la que se cierra la caja (`caja/cierre-caja`).

Las referencias `(Ox)` remiten a las decisiones de `design.md`. Todos los datos de ejemplo son sintéticos (R19).

## Requirements

### Requirement: Caja del día por concepto y medio
`GET /api/panel/caja?dia=AAAA-MM-DD` SHALL devolver los ingresos y egresos de ese día agrupados por concepto (`sena`, `pago_presupuesto`, `devolucion_sena`) y medio (`mercadopago`, `transferencia`), con cantidad y total, más `total_ingresos`, `total_egresos` y `total_neto`. Los importes SHALL ser decimales exactos de dos cifras (R4). Sin `dia` SHALL usar el día actual de la clínica (O4, O14).

#### Scenario: Día con señas y cobros (Happy Path)
- **GIVEN** el 2026-11-17 una seña acreditada por `mercadopago` de "3000.00" y un pago de presupuesto `registrado` por `transferencia` de "1500.00"
- **WHEN** recepción consulta `dia=2026-11-17`
- **THEN** recibe 200 con una línea `sena`/`mercadopago` (1, "3000.00"), una `pago_presupuesto`/`transferencia` (1, "1500.00"), `total_ingresos` "4500.00", `total_egresos` "0.00" y `total_neto` "4500.00"

#### Scenario: Fecha inválida (Error de Negocio)
- **WHEN** recepción consulta `dia=17-11-2026` o `dia=2026-02-30`
- **THEN** recibe 422 y no se devuelve ningún importe

#### Scenario: Día sin movimientos (Caso de Borde)
- **WHEN** recepción consulta un día sin señas, cobros ni devoluciones
- **THEN** recibe 200 con la lista de líneas vacía y los tres totales en "0.00"

### Requirement: Qué cuenta como ingreso y como egreso
Una seña SHALL contar como ingreso el día en que la clínica recibió el dinero, por el importe recibido, sin importar su estado posterior (O4). Un pago de presupuesto SHALL contar el día de su fecha de cobro mientras esté `registrado`; uno `anulado` no cuenta. Una devolución de seña registrada SHALL contar como egreso el día de la devolución. Los pagos `pendiente`, `vencido` y `en_revision` y los pagos excedentes de Mercado Pago no SHALL entrar en los totales.

#### Scenario: Seña cobrada un día y devuelta otro (Happy Path)
- **GIVEN** una seña de "3000.00" acreditada el 2026-11-17, cuyo turno se canceló con más de 24 horas, y cuya devolución se registró el 2026-11-19
- **WHEN** recepción consulta el 17 y el 19
- **THEN** el 17 muestra el ingreso de "3000.00" y el 19 un egreso `devolucion_sena` de "3000.00"; el total del 17 no cambia por la devolución

#### Scenario: Pago en revisión o anulado (Error de Negocio)
- **GIVEN** el 2026-11-17 un pago de seña `en_revision` por "2999.99" y un pago de presupuesto `anulado` de "1500.00"
- **WHEN** recepción consulta ese día
- **THEN** ninguno de los dos suma en los totales, y el pago en revisión figura solo en la lista de pendientes

#### Scenario: Seña acreditada a mano con otro importe (Caso de Borde)
- **GIVEN** una seña de "3000.00" que la pasarela informó por "2999.99", quedó `en_revision` y recepción acreditó a mano
- **WHEN** recepción consulta el día de la acreditación
- **THEN** el ingreso es de "2999.99", que es lo que se recibió

### Requirement: La seña de un ausente queda retenida en caja
Cuando un turno con seña acreditada pasa a `ausente`, la seña SHALL seguir contando como ingreso del día en que se cobró, no SHALL generar ningún egreso ni figurar entre las devoluciones pendientes, y la caja SHALL informarla como retenida, con cantidad y total (R9, RN-SN-02).

#### Scenario: Ausente con seña acreditada (Happy Path)
- **GIVEN** una seña de "3000.00" acreditada el 2026-11-16 para un turno del 2026-11-17 que recepción marcó `ausente`
- **WHEN** recepción consulta la caja del 16
- **THEN** el ingreso de "3000.00" sigue en el total y `senas_retenidas` informa 1 por "3000.00"

#### Scenario: Intento de devolver la seña de un ausente (Error de Negocio)
- **GIVEN** esa misma seña, en estado `no_reembolsado`
- **WHEN** recepción intenta registrar su devolución
- **THEN** recibe 409 `no_es_devolucion_pendiente`, el pago sigue `no_reembolsado` y la caja no cambia

#### Scenario: Ausente sin seña (Caso de Borde)
- **GIVEN** un turno manual sin seña marcado `ausente` el 2026-11-17
- **WHEN** recepción consulta la caja de ese día
- **THEN** no hay ningún movimiento por ese turno y `senas_retenidas` informa 0 por "0.00"

### Requirement: El día de la caja es el de la clínica
Cada movimiento SHALL pertenecer al día calendario de la zona horaria de la clínica en que ocurrió, sin importar la zona del servidor ni la del navegador (O14). El día SHALL abarcar desde las 00:00:00 hasta antes de las 00:00:00 del día siguiente en esa zona.

#### Scenario: Cobro a la noche (Happy Path)
- **GIVEN** una seña acreditada el 2026-11-17 a las 22:30 de la clínica (2026-11-18 01:30 UTC)
- **WHEN** recepción consulta el 17 y el 18
- **THEN** la seña figura el 17 y no el 18

#### Scenario: Navegador en otra zona (Error de Negocio)
- **GIVEN** un navegador configurado en la zona de Tokio
- **WHEN** recepción abre la caja de "hoy"
- **THEN** ve el día actual de la clínica y no el de Tokio

#### Scenario: Primer y último instante del día (Caso de Borde)
- **GIVEN** un cobro a las 00:00:00 del 2026-11-17 y otro a las 23:59:59 del mismo día, hora de la clínica
- **WHEN** recepción consulta el 17
- **THEN** los dos figuran el 17, y un tercero a las 00:00:00 del 18 no

### Requirement: Detalle de los movimientos del día
La caja SHALL incluir el detalle de cada movimiento del día con su concepto, medio, importe, hora de la clínica, referencia y el turno o presupuesto al que pertenece, e indicar si el día está `abierto` o `cerrado`. El detalle no SHALL contener nombre, DNI, teléfono ni email (R19).

#### Scenario: Detalle con referencias (Happy Path)
- **GIVEN** un pago de presupuesto del 2026-11-17 con referencia "TRF-SINT-0001"
- **WHEN** recepción consulta ese día
- **THEN** el detalle trae ese movimiento con su referencia, su hora con el offset de la clínica y el id del presupuesto, y el día figura `abierto`

#### Scenario: Sin datos personales (Error de Negocio)
- **GIVEN** una seña del turno de "Lucía Ejemplo" (+5491100000011)
- **WHEN** se inspecciona la respuesta de la caja
- **THEN** no contiene ni el nombre ni el teléfono

#### Scenario: Día ya cerrado (Caso de Borde)
- **GIVEN** un día con un cierre vigente
- **WHEN** recepción consulta ese día
- **THEN** la respuesta indica `cerrado` y trae el id del cierre

### Requirement: Solo recepción y admin ven la caja
Todas las rutas bajo `/api/panel/caja` SHALL requerir rol `recepcion` o `admin` (O15). Un usuario con solo el rol `odontologo` SHALL recibir 403 y sin token SHALL responderse 401. Cada consulta aceptada de la caja SHALL quedar auditada con el usuario y el día consultado, sin datos personales (RN-GL-01, RN-CL-03).

#### Scenario: Recepción consulta (Happy Path)
- **WHEN** un usuario con rol `recepcion` consulta la caja de un día
- **THEN** recibe 200 y queda un registro de auditoría `lectura_caja` con su usuario y el día

#### Scenario: La odontóloga pide la caja (Error de Negocio)
- **WHEN** la Dra. Ana Ficticia, con solo el rol `odontologo`, consulta la caja
- **THEN** recibe 403, no ve ningún importe y no queda registro de auditoría

#### Scenario: Sin sesión o con más de un rol (Caso de Borde)
- **WHEN** se consulta sin token, y luego con un usuario que tiene los roles `odontologo` y `admin`
- **THEN** la primera responde 401 y la segunda 200, porque vale el permiso más amplio

### Requirement: Pantalla de caja
El panel SHALL ofrecer a recepción y admin una pantalla de caja con selector de día, los totales por concepto y medio, las señas retenidas, el detalle del día y los pendientes por resolver, cargando en paralelo lo que no depende entre sí (R2). SHALL funcionar a 360 px de ancho sin desplazamiento horizontal (R3) y mostrar los importes en pesos con el formato de la clínica.

#### Scenario: Caja del día a 360 px (Happy Path)
- **GIVEN** recepción con sesión iniciada en un viewport de 360 px y un día con una seña de "3000.00"
- **WHEN** abre la sección Caja
- **THEN** ve el total del día "$ 3.000,00", la línea de señas por Mercado Pago y ningún desplazamiento horizontal

#### Scenario: Falla al cargar (Error de Negocio)
- **GIVEN** que el servidor no responde
- **WHEN** recepción abre la caja
- **THEN** ve un mensaje que dice qué pasó y un botón para reintentar, y ningún importe a medias

#### Scenario: Día sin movimientos (Caso de Borde)
- **WHEN** recepción elige un día sin movimientos
- **THEN** ve "No hubo movimientos este día" y puede cambiar de día sin recargar la página
