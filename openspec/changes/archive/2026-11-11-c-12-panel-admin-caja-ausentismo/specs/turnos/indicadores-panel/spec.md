# Spec Delta: turnos/indicadores-panel

## Purpose
Muestra a recepción y admin las métricas de éxito del producto: cuánto se ocupa cada sillón y cuánta gente falta a su turno, con lo recuperado por las señas retenidas (`01_vision_y_objetivos.md` §Métricas de éxito, US-007 CA-1).

Las referencias `(Ox)` remiten a las decisiones de `design.md`. Todos los datos de ejemplo son sintéticos (R19).

## ADDED Requirements

### Requirement: Ocupación por sillón y por día
`GET /api/panel/ocupacion?desde=&hasta=` SHALL devolver, por cada sillón y cada día de la clínica del rango (hasta 31 días), los minutos ocupados, los minutos de atención de ese día, el porcentaje de ocupación con dos decimales y la cantidad de turnos. Un turno SHALL contar en el día en que empieza (O11, O14). `sillon_id` opcional SHALL limitar el resultado a ese sillón.

#### Scenario: Un sillón con dos turnos (Happy Path)
- **GIVEN** el sillón "Sillón 1" con atención de 09:00 a 13:00 el 2026-11-17 y dos turnos `reservado` de 30 y 60 minutos
- **WHEN** recepción consulta `desde=2026-11-17&hasta=2026-11-17`
- **THEN** recibe para ese sillón y día 90 minutos ocupados, 240 de atención, "37.50" de porcentaje y 2 turnos

#### Scenario: Rango o sillón inválidos (Error de Negocio)
- **WHEN** recepción consulta un rango de 32 días, o con `hasta` anterior a `desde`, o con un `sillon_id` que no existe
- **THEN** recibe 422 en los tres casos

#### Scenario: Turno a medianoche y filtro por sillón (Caso de Borde)
- **GIVEN** un turno del "Sillón 2" que empieza el 2026-11-17 a las 23:30 y termina el 18 a las 00:30
- **WHEN** recepción consulta del 17 al 18 con ese `sillon_id`
- **THEN** los 60 minutos cuentan el 17, el 18 no tiene minutos y la respuesta no trae otros sillones

### Requirement: Solo cuentan los turnos que ocupan agenda
La ocupación SHALL sumar solo turnos `reservado`, `confirmado` y `atendido`. Un turno `en_espera` no SHALL contar nunca (R8, RN-SN-01); tampoco uno `cancelado`. Los minutos de turnos `ausente` no SHALL contar como ocupados y SHALL informarse aparte como minutos perdidos (O11).

#### Scenario: Reservado, confirmado y atendido (Happy Path)
- **GIVEN** en el mismo sillón y día un turno `reservado`, uno `confirmado` y uno `atendido`, de 30 minutos cada uno
- **WHEN** recepción consulta la ocupación
- **THEN** los minutos ocupados son 90

#### Scenario: Pre-reserva en espera (Error de Negocio)
- **GIVEN** un sillón con un único turno `en_espera` de 60 minutos ese día, con la seña pendiente
- **WHEN** recepción consulta la ocupación
- **THEN** ese sillón informa 0 minutos ocupados, "0.00" de porcentaje y 0 turnos

#### Scenario: La pre-reserva se acredita y hay un ausente (Caso de Borde)
- **GIVEN** esa pre-reserva, que se acredita y pasa a `reservado`, y otro turno de 30 minutos marcado `ausente`
- **WHEN** recepción vuelve a consultar
- **THEN** los minutos ocupados son 60 y los minutos perdidos por ausentes son 30

### Requirement: Minutos de atención de un sillón
Los minutos de atención de un sillón activo en un día SHALL ser la duración de la unión de las franjas de disponibilidad activas de ese día de la semana, sin contar dos veces las que se superponen (O11). Un sillón que no está activo, o un día sin franjas, SHALL informar 0 minutos de atención y el porcentaje vacío.

#### Scenario: Dos profesionales con franjas superpuestas (Happy Path)
- **GIVEN** un martes con franjas activas de 09:00 a 13:00 y de 11:00 a 15:00
- **WHEN** recepción consulta ese día
- **THEN** cada sillón activo informa 360 minutos de atención

#### Scenario: Sillón en mantenimiento con turnos (Error de Negocio)
- **GIVEN** un sillón en `mantenimiento` que tiene un turno `atendido` de 30 minutos ese día
- **WHEN** recepción consulta la ocupación
- **THEN** ese sillón informa 30 minutos ocupados, 0 de atención y el porcentaje vacío, sin dividir por cero

#### Scenario: Día sin atención (Caso de Borde)
- **GIVEN** un domingo sin franjas ni turnos
- **WHEN** recepción consulta ese día
- **THEN** cada sillón activo informa 0 minutos ocupados, 0 de atención y el porcentaje vacío

### Requirement: Ausentismo del período
`GET /api/panel/ausentismo?desde=&hasta=` SHALL devolver, para los turnos que empiezan en el rango (hasta 366 días), la cantidad de `atendido` y de `ausente`, y la tasa de ausentismo: ausentes sobre atendidos más ausentes, en porcentaje con dos decimales (O12). SHALL informar también los turnos ya terminados que siguen `reservado` o `confirmado`, como `sin_marcar`, y el mismo desglose por profesional.

#### Scenario: Ocho atendidos y dos ausentes (Happy Path)
- **GIVEN** en noviembre 8 turnos `atendido` y 2 `ausente`
- **WHEN** recepción consulta `desde=2026-11-01&hasta=2026-11-30`
- **THEN** recibe 8 atendidos, 2 ausentes y una tasa de "20.00"

#### Scenario: Rango inválido o rol sin permiso (Error de Negocio)
- **WHEN** recepción consulta un rango de 400 días, y luego un usuario con solo el rol `odontologo` consulta un rango válido
- **THEN** recibe 422 y 403 respectivamente

#### Scenario: Período sin turnos resueltos (Caso de Borde)
- **GIVEN** un período con 3 turnos terminados que siguen `reservado`, uno `cancelado` y uno `en_espera`
- **WHEN** recepción consulta el ausentismo
- **THEN** recibe 0 atendidos, 0 ausentes, la tasa vacía y `sin_marcar` en 3; el cancelado y la pre-reserva no cuentan

### Requirement: Recupero por señas retenidas
El ausentismo SHALL informar el recupero del período: cuántos turnos `ausente` tienen su seña retenida, el importe total retenido y el porcentaje de ausentes con seña retenida (O12, R9). Una seña retenida nunca SHALL figurar como devuelta ni por devolver.

#### Scenario: Dos ausentes, uno con seña (Happy Path)
- **GIVEN** dos turnos `ausente` en el período: uno con seña retenida de "3000.00" y uno manual sin seña
- **WHEN** recepción consulta el ausentismo
- **THEN** el recupero informa 1 seña retenida, "3000.00" y "50.00" por ciento

#### Scenario: Seña cancelada con devolución (Error de Negocio)
- **GIVEN** un turno `cancelado` con 48 horas cuya seña quedó `a_reembolsar`
- **WHEN** recepción consulta el ausentismo
- **THEN** ese turno no cuenta como ausente ni su seña como recupero

#### Scenario: Sin ausentes (Caso de Borde)
- **GIVEN** un período con solo turnos `atendido`
- **WHEN** recepción consulta el ausentismo
- **THEN** el recupero informa 0 señas, "0.00" y el porcentaje vacío

### Requirement: Solo recepción y admin ven los indicadores
`GET /api/panel/ocupacion` y `GET /api/panel/ausentismo` SHALL requerir rol `recepcion` o `admin` (O15); un usuario con solo el rol `odontologo` SHALL recibir 403 y sin token SHALL responderse 401. Las respuestas SHALL contener solo cantidades, minutos, importes y nombres de sillones y profesionales, nunca datos de pacientes (R19).

#### Scenario: Admin consulta (Happy Path)
- **WHEN** un usuario con rol `admin` consulta la ocupación de la semana
- **THEN** recibe 200

#### Scenario: La odontóloga consulta (Error de Negocio)
- **WHEN** la Dra. Ana Ficticia, con solo el rol `odontologo`, consulta la ocupación
- **THEN** recibe 403 y ningún dato

#### Scenario: Sin datos de pacientes (Caso de Borde)
- **GIVEN** turnos de "Mateo Prueba" (+5491100000012) en el período
- **WHEN** se inspeccionan las dos respuestas
- **THEN** no contienen su nombre ni su teléfono

### Requirement: Pantalla de indicadores
El panel SHALL ofrecer a recepción y admin una pantalla con la ocupación por sillón de la semana elegida y el ausentismo con su recupero, cargando las dos consultas en paralelo (R2). Cada valor SHALL mostrarse con su número y su texto, no solo con color o con una barra. SHALL funcionar a 360 px sin desplazamiento horizontal (R3).

#### Scenario: Indicadores a 360 px (Happy Path)
- **GIVEN** recepción en un viewport de 360 px y una semana con turnos
- **WHEN** abre la sección Indicadores
- **THEN** ve, por sillón, el porcentaje de ocupación con sus minutos, y la tasa de ausentismo con lo recuperado en pesos

#### Scenario: Falla una de las dos consultas (Error de Negocio)
- **GIVEN** que la consulta de ausentismo falla y la de ocupación responde
- **WHEN** recepción abre la pantalla
- **THEN** ve la ocupación, y en el lugar del ausentismo un mensaje con qué pasó y un botón para reintentar

#### Scenario: Pre-reserva visible como no ocupada (Caso de Borde)
- **GIVEN** un sillón cuyo único turno del día es una pre-reserva `en_espera`
- **WHEN** recepción mira la ocupación de ese día
- **THEN** el sillón figura con 0 % ocupado
