# Spec Delta: pagos/sena-turno

## Purpose
Gestiona la seña de los turnos de la reserva pública: cuánto se cobra, cómo se inicia el pago por Mercado Pago o por transferencia, cómo se acredita y pasa el turno de `en_espera` a `reservado` (el único momento en que bloquea agenda), cuándo vence la pre-reserva, cuándo se devuelve (cancelación con 24 h o más) y por qué no se devuelve ante un ausente (R8, R9, RN-SN-01..08, RN-PG-01).

## ADDED Requirements

### Requirement: Monto de la seña derivado del porcentaje configurado
El sistema SHALL calcular la seña en el servidor como `precio_base del tratamiento × sena_porcentaje / 100`, redondeada a 2 decimales con redondeo half-up y guardada como decimal exacto (nunca float). El cliente nunca envía el monto. El porcentaje aplicado SHALL guardarse en el pago, para que un cambio posterior de la configuración no altere las señas ya iniciadas.

#### Scenario: Seña del 30% sobre el precio base (Happy Path)
- **GIVEN** que `sena_porcentaje` es 30 y el tratamiento "Limpieza" tiene precio base 10000.00
- **WHEN** el paciente inicia la seña de un turno `en_espera` de ese tratamiento
- **THEN** el pago se registra con monto "3000.00" y porcentaje aplicado "30.00"

#### Scenario: Monto con redondeo en el borde del centavo (Caso de Borde)
- **GIVEN** que `sena_porcentaje` es 30 y el tratamiento tiene precio base 3333.33
- **WHEN** el paciente inicia la seña
- **THEN** el pago se registra con monto "1000.00" (999.999 redondeado half-up) y la respuesta lo serializa como texto decimal

#### Scenario: Cambio de porcentaje con una seña ya iniciada (Error de Negocio)
- **GIVEN** que existe una seña pendiente de "3000.00" calculada al 30% y el admin cambia `sena_porcentaje` a 40
- **WHEN** el paciente consulta el estado de esa seña
- **THEN** la seña sigue en "3000.00" con porcentaje aplicado "30.00"; el 40% solo rige para las señas que se inicien después

### Requirement: Turno de tratamiento sin precio queda exento de seña
Cuando la seña calculada es 0.00 (tratamiento con precio base 0), el sistema SHALL crear el turno público directamente en `reservado`, con anti-solape, sin generar ningún pago (RN-SN-06).

#### Scenario: Reserva de tratamiento con precio base cero (Caso de Borde)
- **GIVEN** que el tratamiento "Control" tiene precio base 0.00 y el horario está libre
- **WHEN** el paciente "Lucía Ficticia" (+5491155556666) lo reserva por `POST /api/public/turnos`
- **THEN** el sistema responde 201 con estado `reservado`, sin bloque de seña, y el horario deja de figurar como libre

### Requirement: Inicio de la seña con Mercado Pago
El sistema SHALL permitir iniciar la seña de un turno `en_espera` con `POST /api/public/turnos/{id}/sena` y medio `mercadopago`. Para eso SHALL crear en la pasarela una preferencia por el monto de la seña, con una referencia externa única y un vencimiento que no supere el de la pre-reserva, y devolver 201 con la URL de checkout, el monto, el vencimiento y el texto de la política de reembolso.

#### Scenario: Inicio de seña con Mercado Pago (Happy Path)
- **GIVEN** que el turno 41 está `en_espera`, su código de gestión es válido y Mercado Pago está habilitado
- **WHEN** se envía `POST /api/public/turnos/41/sena` con medio `mercadopago` y el código de gestión
- **THEN** el sistema responde 201 con `estado` "pendiente", `monto`, `referencia_externa`, `checkout_url`, `vence_en` y `texto_politica_reembolso`, y persiste un único pago pendiente para el turno

#### Scenario: Reintento del inicio con el mismo medio (Caso de Borde)
- **GIVEN** que el turno 41 ya tiene un pago pendiente por Mercado Pago que no venció
- **WHEN** se vuelve a enviar `POST /api/public/turnos/41/sena` con medio `mercadopago`
- **THEN** el sistema responde 200 con el mismo pago pendiente (misma referencia externa) y no crea otra preferencia

#### Scenario: Seña sobre un turno que no está en espera (Error de Negocio)
- **GIVEN** que el turno 42 está `reservado`, `cancelado` o `ausente`
- **WHEN** se envía `POST /api/public/turnos/42/sena`
- **THEN** el sistema responde 409 con motivo `estado_invalido` y no crea ningún pago

### Requirement: Inicio de la seña por transferencia
El sistema SHALL permitir iniciar la seña con medio `transferencia` (RN-SN-08): registra un pago pendiente y devuelve el monto, el alias y el CBU configurados por el admin, un código de referencia corto y único del turno para el concepto de la transferencia, el vencimiento y el texto de la política de reembolso. Si había un pago pendiente con otro medio, SHALL quedar `vencido` (un solo pago activo por turno).

#### Scenario: Inicio de seña por transferencia (Happy Path)
- **GIVEN** que el turno 43 está `en_espera` y la transferencia está habilitada con alias "clinica.demo.sintetica" y CBU sintético "0000003100000000000043"
- **WHEN** se envía `POST /api/public/turnos/43/sena` con medio `transferencia` y el código de gestión
- **THEN** el sistema responde 201 con `estado` "pendiente", `monto`, `alias` "clinica.demo.sintetica", `cbu` "0000003100000000000043", una `referencia_concepto` de 20 caracteres o menos que identifica al turno 43 (por ejemplo "SENA-43-A1B2C3"), `vence_en` y `texto_politica_reembolso`

#### Scenario: Cambio de medio con un pago pendiente (Caso de Borde)
- **GIVEN** que el turno 43 tiene un pago pendiente por Mercado Pago
- **WHEN** se envía `POST /api/public/turnos/43/sena` con medio `transferencia`
- **THEN** el pago de Mercado Pago queda `vencido`, se crea el de transferencia como único pago activo y se responde 201

#### Scenario: Medio deshabilitado o fuera de RN-PG-01 (Error de Negocio)
- **GIVEN** que el admin deshabilitó la transferencia
- **WHEN** se envía `POST /api/public/turnos/43/sena` con medio `transferencia` o con un medio inexistente como `efectivo`
- **THEN** el sistema responde 422 indicando los medios habilitados y no crea ningún pago

### Requirement: Acceso a la seña solo con el código de gestión
Los endpoints públicos de seña SHALL exigir el código de gestión del turno en la cabecera `X-Codigo-Gestion`. Si falta o no corresponde al turno, el sistema SHALL responder 404, sin revelar si el turno existe, y no SHALL exponer el teléfono ni el nombre de contacto.

#### Scenario: Código de gestión correcto (Happy Path)
- **GIVEN** que el turno 44 tiene el código de gestión `c0d1g0-s1nt3t1c0-44`
- **WHEN** se envía `GET /api/public/turnos/44/sena` con `X-Codigo-Gestion: c0d1g0-s1nt3t1c0-44`
- **THEN** el sistema responde 200 con el estado de la seña y sin datos de contacto

#### Scenario: Código ajeno o ausente (Error de Negocio)
- **GIVEN** que el turno 44 existe y el código enviado es el de otro turno, o no se envía la cabecera
- **WHEN** se envía `POST` o `GET` a `/api/public/turnos/44/sena`
- **THEN** el sistema responde 404 sin crear ni mostrar ningún pago

### Requirement: Revalidación del horario al iniciar la seña
Antes de crear un pago, el sistema SHALL verificar que el profesional y algún sillón activo sigan libres en el rango del turno frente a los turnos bloqueantes. Si otro turno ya lo bloqueó, SHALL responder 409 con alternativas libres sin crear ningún pago, para no cobrar un horario que ya no se puede dar.

#### Scenario: Horario tomado entre la reserva y el pago (Error de Negocio)
- **GIVEN** que los turnos 45 y 46 están `en_espera` en el mismo horario y profesional, y la seña del turno 46 ya se acreditó
- **WHEN** se envía `POST /api/public/turnos/45/sena`
- **THEN** el sistema responde 409 con motivo `profesional` y alternativas libres, no crea ningún pago y el turno 45 sigue `en_espera` hasta que venza

#### Scenario: Horario libre al iniciar (Happy Path)
- **GIVEN** que el turno 45 está `en_espera` y nadie bloqueó su horario
- **WHEN** se envía `POST /api/public/turnos/45/sena` con un medio habilitado
- **THEN** el sistema responde 201 y crea el pago pendiente

### Requirement: Consulta del estado de la seña
El sistema SHALL exponer `GET /api/public/turnos/{id}/sena` con el estado del turno y del último pago (`pendiente`, `acreditado`, `vencido`, `no_reembolsado` o `a_reembolsar`), el monto, el medio, el vencimiento y el texto de la política de reembolso, para que la pantalla de pago sepa cuándo terminó la espera.

#### Scenario: Seña acreditada (Happy Path)
- **GIVEN** que la seña del turno 47 se acreditó
- **WHEN** se consulta `GET /api/public/turnos/47/sena` con el código de gestión
- **THEN** el sistema responde 200 con `estado_turno` "reservado" y `estado_pago` "acreditado"

#### Scenario: Turno sin pago iniciado (Caso de Borde)
- **GIVEN** que el turno 48 está `en_espera` y el paciente todavía no eligió medio
- **WHEN** se consulta `GET /api/public/turnos/48/sena`
- **THEN** el sistema responde 200 con `estado_turno` "en_espera", `estado_pago` null, el monto a pagar y `vence_en`

### Requirement: Webhook de Mercado Pago con firma verificada
El sistema SHALL recibir notificaciones en `POST /api/webhooks/mercadopago` y SHALL verificar la firma HMAC-SHA256 de la cabecera `x-signature` con el secreto configurado, usando `x-request-id` y el id notificado. Si la firma no es válida, falta o su timestamp está fuera de la tolerancia, SHALL responder 401 sin cambiar ningún estado.

#### Scenario: Firma válida de un pago aprobado (Happy Path)
- **GIVEN** que existe un pago pendiente con referencia externa `ref-sintetica-0001` y la pasarela informa el pago `PAY-1` aprobado con esa referencia
- **WHEN** llega `POST /api/webhooks/mercadopago` con tipo `payment`, id `PAY-1` y una firma válida
- **THEN** el sistema responde 200, el pago queda `acreditado` con el id `PAY-1` y el turno pasa a `reservado`

#### Scenario: Firma inválida (Error de Negocio)
- **GIVEN** que existe un pago pendiente con referencia `ref-sintetica-0001`
- **WHEN** llega el webhook con una firma calculada con otro secreto, o sin la cabecera `x-signature`
- **THEN** el sistema responde 401, no consulta la pasarela y el pago y el turno no cambian

#### Scenario: Notificación de un pago desconocido o no aprobado (Caso de Borde)
- **GIVEN** que la pasarela informa el pago `PAY-9` como `rejected`, o con una referencia externa que no existe en el sistema
- **WHEN** llega el webhook firmado correctamente
- **THEN** el sistema responde 200 (para que Mercado Pago no reintente), no cambia ningún estado y registra el evento en el log sin datos personales

### Requirement: Acreditación idempotente
La acreditación SHALL ser idempotente por referencia externa y por id de pago de la pasarela: una notificación repetida o concurrente sobre un pago ya acreditado SHALL responder 200 sin acreditar dos veces, sin duplicar la auditoría y sin cambiar el estado del turno.

#### Scenario: Webhook duplicado (Caso de Borde)
- **GIVEN** que el pago con referencia `ref-sintetica-0002` ya se acreditó con el id `PAY-2`
- **WHEN** llega otra vez el mismo webhook firmado para `PAY-2`
- **THEN** el sistema responde 200, hay un único registro de auditoría de acreditación y el turno sigue `reservado`

#### Scenario: Dos webhooks simultáneos del mismo pago (Caso de Borde)
- **GIVEN** que el pago con referencia `ref-sintetica-0003` está pendiente
- **WHEN** llegan en simultáneo dos webhooks firmados para el mismo pago aprobado
- **THEN** ambos responden 200, el pago queda acreditado una sola vez y el turno pasa a `reservado` una sola vez

### Requirement: La seña acreditada bloquea la agenda con anti-solape
Al acreditar, el sistema SHALL pasar el turno de `en_espera` a `reservado` solo si el profesional sigue libre y hay un sillón activo libre (puede reasignarlo), y la base de datos SHALL ser la garantía final (RN-TU-03, R5). Si el horario ya está bloqueado, el turno SHALL quedar `cancelado` y el pago `a_reembolsar`, nunca dos turnos bloqueantes solapados (RN-SN-05).

#### Scenario: Acreditación bloquea el horario (Happy Path)
- **GIVEN** que el turno 50 está `en_espera` de 10:00 a 10:30 con el profesional P y su horario está libre
- **WHEN** se acredita su seña
- **THEN** el turno queda `reservado`, `GET /api/public/disponibilidad` deja de ofrecer ese horario para P y un `POST /api/turnos` solapado sobre P responde 409

#### Scenario: Dos pre-reservas compiten por el mismo horario (Error de Negocio)
- **GIVEN** que los turnos 51 y 52 están `en_espera` en el mismo horario y profesional, y la seña del 51 ya se acreditó
- **WHEN** se aprueba y notifica el pago del turno 52
- **THEN** el turno 52 queda `cancelado`, su pago queda `a_reembolsar`, el webhook responde 200 y el 51 sigue siendo el único turno bloqueante

#### Scenario: Solo el sillón original está ocupado (Caso de Borde)
- **GIVEN** que el turno 53 está `en_espera` en el sillón S1, S1 fue tomado por otro turno bloqueante y el sillón S2 está libre en ese rango
- **WHEN** se acredita su seña
- **THEN** el turno 53 queda `reservado` en el sillón S2 y la auditoría registra la reasignación

### Requirement: La pre-reserva en espera no dispara notificaciones
El sistema no SHALL generar recordatorio de WhatsApp ni evento de calendario para un turno `en_espera` (RN-SN-01, RN-WA-03). La acreditación SHALL ser el único disparador de esos efectos y SHALL dejar un registro de auditoría con origen `acreditacion_sena`, que C-09 y C-10 van a consumir.

#### Scenario: Acreditación deja el punto de enganche (Happy Path)
- **GIVEN** que el turno 63 está `en_espera`
- **WHEN** se acredita su seña
- **THEN** existe exactamente un registro de auditoría del turno 63 con origen `acreditacion_sena` y estado `reservado`

#### Scenario: Pre-reserva que vence sin pagar (Error de Negocio)
- **GIVEN** que el turno 64 se creó `en_espera` y venció sin pago
- **WHEN** se revisa la auditoría del turno 64
- **THEN** no hay ningún registro con origen `acreditacion_sena` y no se generó ningún recordatorio ni evento

### Requirement: Acreditación manual de transferencias
El sistema SHALL permitir que un usuario con rol `recepcion` o `admin` acredite un pago pendiente por transferencia con `POST /api/admin/pagos-sena/{id}/acreditar` (RN-SN-08), con la misma regla de anti-solape, registrando en la auditoría quién lo hizo (RN-GL-01). Los demás roles SHALL recibir 403.

#### Scenario: Recepción acredita una transferencia (Happy Path)
- **GIVEN** que existe un pago pendiente por transferencia del turno 54 `en_espera` y el usuario autenticado tiene rol `recepcion`
- **WHEN** envía `POST /api/admin/pagos-sena/{id}/acreditar`
- **THEN** el sistema responde 200, el pago queda `acreditado` con el usuario que lo acreditó, el turno queda `reservado` y se registra en `RegistroAuditoria`

#### Scenario: Rol sin permiso (Error de Negocio)
- **GIVEN** que el usuario autenticado tiene rol `odontologo`
- **WHEN** envía `POST /api/admin/pagos-sena/{id}/acreditar`
- **THEN** el sistema responde 403 y el pago sigue pendiente

#### Scenario: Acreditar a mano un pago de Mercado Pago o ya vencido (Caso de Borde)
- **GIVEN** que el pago es de Mercado Pago, o es una transferencia ya `vencida`
- **WHEN** recepción intenta acreditarlo a mano
- **THEN** el sistema responde 409 con el motivo y no cambia el pago ni el turno

### Requirement: Vencimiento de la pre-reserva en espera
Todo turno `en_espera` SHALL tener un vencimiento (RN-SN-07: 30 min con Mercado Pago, 24 h con transferencia, editables por el admin) que no supere su inicio. Al vencer, un barrido periódico SHALL pasarlo a `cancelado` y sus pagos pendientes a `vencido`, con auditoría. Una pre-reserva vencida SHALL contar como no vigente aunque el barrido aún no haya corrido.

#### Scenario: Pre-reserva vence sin pago (Happy Path)
- **GIVEN** que el turno 55 está `en_espera`, vence a las 10:30 y no se acreditó ningún pago
- **WHEN** corre el barrido a las 10:31
- **THEN** el turno 55 queda `cancelado`, su pago pendiente (si lo hay) queda `vencido` y se registra en la auditoría

#### Scenario: Pre-reserva no vencida (Error de Negocio)
- **GIVEN** que el turno 56 está `en_espera` y vence a las 10:30
- **WHEN** corre el barrido a las 10:29:59
- **THEN** el turno 56 sigue `en_espera` y su pago sigue `pendiente`

#### Scenario: Vencimiento limitado por el inicio del turno (Caso de Borde)
- **GIVEN** que el vencimiento configurado es de 30 minutos y el turno empieza dentro de 10 minutos
- **WHEN** el paciente lo reserva
- **THEN** `vence_en` es igual al inicio del turno, no 30 minutos después

### Requirement: Pago aprobado después del vencimiento
Si la pasarela aprueba un pago cuando el turno ya no está `en_espera` (venció o fue cancelado), el sistema SHALL registrar el pago como `a_reembolsar`, sin revivir el turno ni bloquear agenda, para que la clínica lo devuelva a mano (RN-SN-05).

#### Scenario: Pago tardío sobre un turno vencido (Caso de Borde)
- **GIVEN** que el turno 57 venció y quedó `cancelado`, y su pago de Mercado Pago quedó `vencido`
- **WHEN** llega un webhook firmado que informa ese pago como aprobado
- **THEN** el pago queda `a_reembolsar`, el turno sigue `cancelado` y el webhook responde 200

### Requirement: El ausente retiene la seña
Cuando un turno `reservado` o `confirmado` con seña acreditada pasa a `ausente`, el sistema SHALL dejar el pago como `no_reembolsado` (recupero en caja) y no SHALL iniciar ningún reembolso (R9, RN-SN-02).

#### Scenario: Ausente con seña acreditada (Happy Path)
- **GIVEN** que el turno 58 está `confirmado` con una seña acreditada de "3000.00"
- **WHEN** recepción lo marca como `ausente`
- **THEN** el turno queda `ausente`, el pago queda `no_reembolsado` por "3000.00" y no se pide ningún reembolso a la pasarela

#### Scenario: Ausente sobre un turno en espera (Error de Negocio)
- **GIVEN** que el turno 59 está `en_espera`
- **WHEN** se intenta marcarlo como `ausente`
- **THEN** la transición se rechaza por inválida y el turno y su pago no cambian

### Requirement: Transiciones de estado válidas del turno
El sistema SHALL permitir solo estas transiciones: `en_espera → reservado | cancelado`; `reservado → confirmado | cancelado | ausente | atendido`; `confirmado → cancelado | ausente | atendido`. `cancelado`, `ausente` y `atendido` son finales. Una transición inválida SHALL rechazarse con 409 sin modificar nada.

#### Scenario: Transición permitida (Happy Path)
- **GIVEN** que el turno 60 está `reservado`
- **WHEN** se lo pasa a `confirmado`
- **THEN** el turno queda `confirmado` y su seña acreditada no cambia

#### Scenario: Transición desde un estado final (Error de Negocio)
- **GIVEN** que el turno 61 está `atendido`
- **WHEN** se intenta pasarlo a `reservado` o a `en_espera`
- **THEN** se rechaza con 409 `transicion_invalida` y el turno sigue `atendido`

#### Scenario: Cancelación de una pre-reserva en espera (Caso de Borde)
- **GIVEN** que el turno 62 está `en_espera` con un pago pendiente
- **WHEN** se lo pasa a `cancelado`
- **THEN** el turno queda `cancelado` y el pago `vencido`, sin devolución porque no se cobró nada

### Requirement: La cancelación con 24 horas o más devuelve la seña
Cuando un turno `reservado` o `confirmado` con seña acreditada se cancela con 24 horas o más de anticipación, el sistema SHALL liberar el horario y dejar el pago `a_reembolsar`, para devolución manual (RN-SN-04). Con menos de 24 horas la cancelación SHALL rechazarse (RN-TU-01). C-06 define la regla en la máquina de estados; C-07 la expone en el endpoint de cancelación.

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

### Requirement: Configuración de la seña por el admin
El sistema SHALL permitir que `recepcion`/`admin` consulten y actualicen con `GET/PUT /api/admin/config/sena` el porcentaje (mayor que 0 y hasta 100), los medios habilitados (subconjunto no vacío de `mercadopago` y `transferencia`, RN-PG-01), el texto de la política de reembolso, los vencimientos y los datos de transferencia (alias, CBU, titular), con auditoría. Los valores inválidos SHALL rechazarse con 422.

#### Scenario: Admin actualiza el porcentaje (Happy Path)
- **GIVEN** que el usuario autenticado tiene rol `admin`
- **WHEN** envía `PUT /api/admin/config/sena` con `sena_porcentaje` "40.00", ambos medios habilitados y un texto de la política de reembolso
- **THEN** el sistema responde 200 con la configuración nueva y registra el cambio en `RegistroAuditoria`

#### Scenario: Porcentaje o medios inválidos (Error de Negocio)
- **GIVEN** que el usuario autenticado tiene rol `admin`
- **WHEN** envía `sena_porcentaje` "0" o "100.01", una lista de medios vacía o un medio `efectivo`
- **THEN** el sistema responde 422 y la configuración no cambia

#### Scenario: Porcentaje en el límite superior (Caso de Borde)
- **GIVEN** que el usuario autenticado tiene rol `admin`
- **WHEN** envía `sena_porcentaje` "100.00"
- **THEN** el sistema lo acepta y las señas nuevas se calculan por el precio base completo

#### Scenario: Configuración inicial (Happy Path)
- **GIVEN** que se acaba de aplicar la migración y nadie editó la configuración
- **WHEN** el admin envía `GET /api/admin/config/sena`
- **THEN** recibe `sena_porcentaje` "30.00", ambos medios habilitados, 30 minutos de vencimiento para Mercado Pago, 1440 para transferencia y el texto de política "Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve." (RN-SN-02, RN-SN-04)

### Requirement: Credenciales de la pasarela fuera del código
El sistema SHALL leer el token de acceso y el secreto del webhook de Mercado Pago solo de variables de entorno, y no SHALL iniciar con la pasarela real si falta alguno. Las respuestas, los logs y la auditoría no SHALL incluir el token, el secreto ni datos de tarjeta (R17).

#### Scenario: Arranque sin credenciales con la pasarela real (Error de Negocio)
- **GIVEN** que la pasarela configurada es la real de Mercado Pago y `MP_ACCESS_TOKEN` está vacío
- **WHEN** se inicia el backend
- **THEN** la configuración falla con un mensaje que nombra la variable faltante sin mostrar ningún valor

#### Scenario: Pasarela falsa fuera de test o e2e (Error de Negocio)
- **GIVEN** que `MP_GATEWAY=fake` y `APP_ENV` es `development` o `production`, o que no se definió ninguna de las dos variables
- **WHEN** se inicia el backend
- **THEN** la configuración falla indicando que la pasarela falsa solo se permite con `APP_ENV=test` o `APP_ENV=e2e`: sin definir nada, el backend arranca como producción con Mercado Pago real y exige sus credenciales

#### Scenario: Pasarela falsa en tests (Caso de Borde)
- **GIVEN** que el entorno es de test o E2E y la pasarela configurada es la falsa
- **WHEN** se inicia una seña con Mercado Pago
- **THEN** no hay ninguna llamada de red a Mercado Pago y la URL de checkout apunta al retorno local de la aplicación

### Requirement: Pantalla de pago de la seña a 360px
Después de reservar, el frontend del paciente SHALL mostrar a 360px de ancho, sin scroll horizontal, la pantalla "Pagá la seña para confirmar tu turno" con el monto, el vencimiento en hora de la clínica, el texto de la política de reembolso y un botón por medio habilitado, y SHALL avisar que el turno no está confirmado hasta acreditar la seña (R3, R8).

#### Scenario: Pago con Mercado Pago y acreditación (Happy Path)
- **GIVEN** que el paciente "Carlos Sintético" reservó y ve la pantalla de seña a 360px
- **WHEN** elige Mercado Pago, vuelve del checkout y llega el webhook aprobado
- **THEN** la pantalla pasa a "Turno reservado" con el código de gestión, sin recargar a mano

#### Scenario: Pre-reserva vencida mientras espera (Error de Negocio)
- **GIVEN** que el paciente está en la pantalla de seña y la pre-reserva vence sin pago
- **WHEN** la pantalla consulta el estado
- **THEN** muestra que la reserva venció y ofrece elegir otro horario, sin mostrar el turno como reservado

#### Scenario: Transferencia pendiente (Caso de Borde)
- **GIVEN** que el paciente elige transferencia
- **WHEN** la pantalla muestra los datos
- **THEN** se ven el alias, el CBU, el monto y el código de referencia para poner en el concepto, cada uno con botón para copiar, y el aviso de que la clínica confirma el turno al acreditar la transferencia

### Requirement: El monto informado por la pasarela debe coincidir con la seña
Al procesar un pago aprobado de Mercado Pago, el sistema SHALL exigir que la pasarela informe el monto y la moneda, y compararlos con la seña (decimal exacto, ARS; RN-SN-09). Si faltan, son ilegibles o no coinciden, SHALL NOT acreditar: el pago pasa a `en_revision` con lo informado, el turno sigue `en_espera`, se audita sin datos personales y el webhook responde 200 de forma idempotente. Recepción o admin SHALL poder acreditarlo a mano; si el turno ya no está vigente queda `a_reembolsar`.

#### Scenario: Monto exacto (Happy Path)
- **GIVEN** que el pago pendiente del turno 70 es de "3000.00" y la pasarela informa el pago aprobado por 3000.00 ARS
- **WHEN** llega el webhook firmado
- **THEN** el sistema responde 200, acredita el pago y el turno pasa a `reservado`

#### Scenario: Monto distinto del de la seña (Error de Negocio)
- **GIVEN** que el pago pendiente del turno 71 es de "3000.00" y la pasarela informa el pago aprobado por 2999.99 (o por 3000.01, o en otra moneda)
- **WHEN** llega el webhook firmado
- **THEN** el sistema responde 200, el pago queda `en_revision` con el monto informado "2999.99", el turno 71 sigue `en_espera`, no bloquea agenda y se audita sin datos personales

#### Scenario: Re-entrega y resolución manual (Caso de Borde)
- **GIVEN** que el pago del turno 72 quedó `en_revision`
- **WHEN** llega otra vez el mismo webhook con el mismo monto distinto, y luego recepción acredita el pago a mano estando el turno vigente
- **THEN** la re-entrega responde 200 sin cambios ni auditoría nueva, y la acreditación manual deja el pago `acreditado` y el turno `reservado`; si el turno hubiera vencido, el pago queda `a_reembolsar`

#### Scenario: Monto o moneda no informados por la pasarela (Caso de Borde)
- **GIVEN** que el pago pendiente del turno 74 es de "3000.00" y la respuesta de la pasarela para el pago aprobado no trae el monto (o no trae la moneda, o el monto no es un número)
- **WHEN** llega el webhook firmado, y luego el mismo webhook otra vez
- **THEN** ambos responden 200, el pago queda `en_revision` una sola vez (con una única auditoría sin datos personales), el turno 74 sigue `en_espera` y no se acredita nada sin poder verificar el monto; la acreditación manual de recepción/admin no depende de datos de la pasarela

### Requirement: Pago vencido aprobado con el turno vigente se acredita
Si la pasarela aprueba un pago que había quedado `vencido` por un cambio de medio y el turno sigue `en_espera` y vigente, el sistema SHALL acreditarlo (el dinero llegó y el turno está vivo) y dejar `vencidos` los demás pagos pendientes del turno.

#### Scenario: Pago por Mercado Pago tras pasar a transferencia (Caso de Borde)
- **GIVEN** que el turno 73 tuvo un pago de Mercado Pago, el paciente cambió a transferencia (el de Mercado Pago quedó `vencido`) y el turno sigue `en_espera` dentro de su plazo
- **WHEN** llega el webhook firmado del pago de Mercado Pago aprobado por el monto de la seña
- **THEN** el pago de Mercado Pago queda `acreditado`, el de transferencia `vencido` y el turno `reservado`

### Requirement: La pantalla de pago informa el pago en revisión y sobrevive al retorno del checkout
La pantalla de espera SHALL tratar el estado `en_revision` como una pantalla clara ("Estamos revisando tu pago", la clínica se comunica) sin mostrar "La reserva venció" aunque el barrido haya cancelado el turno. La seña pendiente SHALL guardarse en `localStorage` con vencimiento (la pre-reserva más 30 minutos, tope 24 horas) y clave versionada, sin el código de gestión en la URL, y borrarse al llegar a un estado terminal.

#### Scenario: Pago en revisión (Error de Negocio)
- **GIVEN** que el pago del turno 75 quedó `en_revision` y el paciente espera en la pantalla
- **WHEN** la pantalla consulta el estado, incluso después de que el barrido canceló el turno
- **THEN** muestra "Estamos revisando tu pago" y "La clínica se va a comunicar con vos", sigue consultando y pasa a "Turno reservado" si la clínica lo acredita

#### Scenario: Retorno en una pestaña nueva (Happy Path)
- **GIVEN** que el paciente eligió Mercado Pago y el retorno se abre en otra pestaña del mismo navegador
- **WHEN** la app lee `?pago=retorno&turno=75`
- **THEN** encuentra el turno y el código en `localStorage` y retoma la espera, y al llegar a un estado terminal borra esos datos

#### Scenario: Seña pendiente vencida (Caso de Borde)
- **GIVEN** que la seña guardada venció (más de 30 minutos después de la pre-reserva o más de 24 horas)
- **WHEN** la app vuelve a abrirse con `?pago=retorno`
- **THEN** no la usa y avisa que no encontró la reserva

### Requirement: Cada pago de la pasarela se registra por su id
El sistema SHALL registrar cada pago aprobado por su id de la pasarela (RN-SN-10). La re-entrega del mismo id SHALL ser idempotente; un pago aprobado con otro id sobre una seña ya acreditada o resuelta SHALL quedar `a_reembolsar`; y los pagos `en_revision` no aceptados SHALL quedar `a_reembolsar` al acreditarse otro.

#### Scenario: Segundo pago distinto sobre una seña acreditada (Error de Negocio)
- **GIVEN** que la seña del turno 76 se acreditó con el pago `PAY-1`
- **WHEN** llega el webhook firmado de otro pago aprobado `PAY-2` con la misma referencia
- **THEN** el turno sigue `reservado`, la seña sigue `acreditado` con `PAY-1`, `PAY-2` queda registrado `a_reembolsar` con una auditoría y el webhook responde 200

#### Scenario: Re-entrega del pago sobrante (Caso de Borde)
- **GIVEN** que `PAY-2` ya quedó registrado `a_reembolsar`
- **WHEN** llega otra vez el webhook de `PAY-2` (o el de `PAY-1`)
- **THEN** responde 200 sin cambios ni auditoría nueva

#### Scenario: Pago en revisión reemplazado por uno correcto (Caso de Borde)
- **GIVEN** que el pago del turno 77 quedó `en_revision` por `PAY-1` con un monto distinto
- **WHEN** llega el webhook de `PAY-2` con el monto exacto
- **THEN** la seña queda `acreditado` con `PAY-2` y `PAY-1` queda registrado `a_reembolsar` con su monto informado

### Requirement: Un deadlock no se convierte en reembolso
Ante un deadlock o un error de serialización, la acreditación SHALL reintentarse en una transacción nueva; si se agota, SHALL responder un error reintentable (503 en el webhook y en la acreditación manual) sin cancelar el turno ni marcar el pago a reembolsar. Solo un conflicto real de agenda (23P01) SHALL resolverse como `a_reembolsar`. Todas las operaciones SHALL tomar los locks en el mismo orden: advisory de reservas, turno y pago.

#### Scenario: Deadlock agotado (Error de Negocio)
- **GIVEN** que la acreditación del pago del turno 78 choca con un deadlock en todos los intentos
- **WHEN** llega el webhook firmado
- **THEN** responde 503, el turno sigue `en_espera` y el pago `pendiente`, y Mercado Pago reintenta más tarde

#### Scenario: Deadlock pasajero (Caso de Borde)
- **GIVEN** que el primer intento de acreditar el turno 79 choca con un deadlock
- **WHEN** se reintenta en una transacción nueva y el horario sigue libre
- **THEN** el turno queda `reservado`

### Requirement: La acreditación manual se valida bajo lock
La acreditación manual de recepción/admin SHALL re-validar bajo lock que el pago sea una transferencia pendiente y vigente (o un pago en revisión), sin confiar en lecturas previas.

#### Scenario: El paciente cambió de medio mientras recepción acreditaba (Caso de Borde)
- **GIVEN** que recepción leyó una transferencia pendiente y el paciente pasó a Mercado Pago antes de la acreditación (la transferencia quedó `vencida`)
- **WHEN** recepción confirma la acreditación
- **THEN** responde 409 `pago_no_pendiente` y no cambia el pago ni el turno

### Requirement: Cabeceras de firma malformadas se rechazan con 401
El webhook SHALL aceptar en la cabecera `x-signature` solo un `ts` de dígitos ASCII con un largo acotado; cualquier cabecera malformada SHALL responder 401 sin consultar la pasarela y sin error interno.

#### Scenario: Timestamp con dígitos no ASCII o desmedido (Error de Negocio)
- **GIVEN** que llega un webhook con `ts=²` o con un `ts` de 400 dígitos
- **WHEN** el sistema verifica la firma
- **THEN** responde 401, no consulta la pasarela y no hay error interno
