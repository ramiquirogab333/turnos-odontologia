# turnos/creacion-sin-solape Specification

## Purpose

Esta capability funda la agenda: permite crear un turno que bloquea su slot e impide cualquier solape por profesional o por sillón/box, con garantía a nivel de base de datos que todos los changes posteriores heredan.

## Requirements

### Requirement: Crear turno con fin derivado del tratamiento

El sistema SHALL crear un turno a partir de `profesional_id`, `sillon_id`, `tratamiento_id` e `inicio`, calculando `fin = inicio + duracion_minutos del tratamiento` (RN-TU-04). El endpoint es identity-free: no recibe ni persiste Paciente/nombre/teléfono (primitiva interna que `POST /api/public/turnos` de C-05 reutiliza). Un campo `fin` enviado por el cliente SHALL ser rechazado o ignorado y nunca determinar la duración.

#### Scenario: Creación válida

- **GIVEN** que existen el profesional P, el sillón S y el tratamiento T (duración 30 minutos), no hay turnos registrados sobre P ni S, y el `inicio` solicitado es futuro
- **WHEN** se envía `POST /api/turnos` con `profesional_id`, `sillon_id`, `tratamiento_id` e `inicio` válido
- **THEN** el sistema responde 201 y persiste el turno con `fin` exactamente igual a `inicio + 30 minutos`

#### Scenario: Fin enviado por el cliente no prevalece

- **GIVEN** que existen P, S y T (duración 30 minutos) sin turnos registrados sobre P ni S
- **WHEN** se envía `POST /api/turnos` incluyendo un campo `fin` distinto del derivado
- **THEN** el sistema responde 422 (si `fin` es campo prohibido) sin persistir nada, o responde 201 ignorando ese valor y persistiendo el turno con el `fin` derivado

#### Scenario: Inicio en el pasado

- **GIVEN** que existen P, S y T en la base de datos
- **WHEN** se envía `POST /api/turnos` con `inicio` anterior al momento actual
- **THEN** el sistema responde 422 y no crea ningún turno

#### Scenario: Referencias inexistentes o datos incompletos

- **GIVEN** el estado actual de la base de datos (con o sin recursos cargados)
- **WHEN** se envía `POST /api/turnos` con `profesional_id`, `sillon_id` o `tratamiento_id` inexistente, o falta alguno de los cuatro campos requeridos (incluido `sillon_id`, siempre NOT NULL)
- **THEN** el sistema responde 422 y no crea ningún turno

### Requirement: Sin solape por profesional

El sistema SHALL rechazar con 409 y motivo `profesional` todo turno cuyo rango `[inicio, fin)` se solape con otro turno BLOQUEANTE del mismo `profesional_id` (RN-TU-03). Rangos adyacentes (`fin` de uno == `inicio` de otro) NO se consideran solape. La garantía SHALL vivir en la base de datos (constraint EXCLUDE), no solo en la aplicación.

#### Scenario: Solape por profesional

- **GIVEN** que existe un turno bloqueante del profesional P en `[10:00, 10:30)`
- **WHEN** se envía `POST /api/turnos` para P en `[10:15, 10:45)`
- **THEN** el sistema responde 409 con motivo `profesional` y no crea ningún turno

#### Scenario: Slots adyacentes no colisionan

- **GIVEN** que existe un turno bloqueante del profesional P en `[10:00, 10:30)`
- **WHEN** se envía `POST /api/turnos` para P en `[10:30, 11:00)`
- **THEN** el sistema responde 201 y persiste el turno

#### Scenario: Mismo horario con distinto profesional no colisiona por profesional

- **GIVEN** que existe un turno bloqueante del profesional P1 en `[10:00, 10:30)` en el sillón S1
- **WHEN** se envía `POST /api/turnos` para el profesional P2 en `[10:00, 10:30)` en el sillón S2
- **THEN** el sistema responde 201 y persiste el turno (ningún recurso coincide)

### Requirement: Sin solape por sillón/box

El sistema SHALL rechazar con 409 y motivo `sillon` todo turno cuyo rango `[inicio, fin)` se solape con otro turno BLOQUEANTE del mismo `sillon_id` (extensión día-1 de RN-TU-03, Resolución 2026-09-30 nº1). Rangos adyacentes NO se consideran solape. La garantía SHALL vivir en la base de datos (constraint EXCLUDE), no solo en la aplicación.

#### Scenario: Solape por sillón

- **GIVEN** que existe un turno bloqueante en el sillón S en `[10:00, 10:30)` (de otro profesional)
- **WHEN** se envía `POST /api/turnos` para S en `[10:15, 10:45)`
- **THEN** el sistema responde 409 con motivo `sillon` y no crea ningún turno

#### Scenario: Mismo horario en distinto sillón no colisiona por sillón

- **GIVEN** que existe un turno bloqueante en el sillón S1 en `[10:00, 10:30)`
- **WHEN** se envía `POST /api/turnos` para el sillón S2 en `[10:00, 10:30)` con profesional libre
- **THEN** el sistema responde 201 y persiste el turno

### Requirement: El turno creado bloquea el slot; estados no bloqueantes nunca colisionan

El turno creado por `POST /api/turnos` (alta interna) SHALL nacer en estado bloqueante (`reservado`). Desde C-06 existe `en_espera` (pre-reserva pública con seña pendiente), que no bloquea (R8). Los EXCLUDE parciales SHALL cubrir solo `reservado` y `confirmado`, de modo que `en_espera`, `cancelado`, `ausente` y `atendido` nunca colisionen ni bloqueen, y el paso de `en_espera` a `reservado` quede sujeto a ellos.

#### Scenario: Turno creado bloquea su slot

- **GIVEN** que no hay turnos registrados sobre el profesional P ni el sillón S
- **WHEN** se crea un turno en `[10:00, 10:30)` para P y S, y luego se envía un segundo `POST /api/turnos` para P o para S en un rango solapado
- **THEN** la primera creación responde 201 y persiste, y la segunda responde 409 sin persistir nada

#### Scenario: Estados liberados no bloquean

- **GIVEN** que el único turno existente sobre P/S en `[10:00, 10:30)` está en estado `cancelado` (o `ausente`/`atendido`)
- **WHEN** se envía `POST /api/turnos` para P/S en `[10:00, 10:30)`
- **THEN** el sistema responde 201 y persiste el turno

#### Scenario: Una pre-reserva en espera no bloquea el alta interna

- **GIVEN** que el único turno existente sobre P/S en `[10:00, 10:30)` está en estado `en_espera`
- **WHEN** se envía `POST /api/turnos` para P/S en `[10:00, 10:30)`
- **THEN** el sistema responde 201 y persiste el turno bloqueante, y el `en_espera` sigue existiendo sin bloquear

#### Scenario: El paso a reservado respeta el EXCLUDE en la base de datos

- **GIVEN** que existe un turno `reservado` sobre P en `[10:00, 10:30)` y un turno `en_espera` sobre P en `[10:15, 10:45)`
- **WHEN** se intenta actualizar directamente en la base el `en_espera` a `reservado`
- **THEN** PostgreSQL rechaza la actualización con violación de exclusión (SQLSTATE 23P01) y el turno sigue `en_espera`

### Requirement: Carrera concurrente por el mismo slot

Ante dos `POST /api/turnos` concurrentes sobre el mismo profesional/sillón/horario, el sistema SHALL persistir exactamente un turno (201) y rechazar el otro con 409. La violación del constraint de exclusión (SQLSTATE 23P01) SHALL mapearse a 409 y nunca a 500.

#### Scenario: Doble reserva concurrente

- **GIVEN** que no hay turnos registrados sobre P ni S, y dos clientes preparan el mismo `POST /api/turnos` (mismo profesional, sillón, inicio y tratamiento)
- **WHEN** ambos envían la solicitud en simultáneo
- **THEN** exactamente uno recibe 201 con su turno persistido, y el otro recibe 409 con motivo `profesional` o `sillon` sin persistir nada

#### Scenario: Violación del EXCLUDE nunca es 500

- **GIVEN** que existe un turno bloqueante sobre P/S y un INSERT concurrente viola el constraint de exclusión a nivel DB
- **WHEN** la aplicación procesa esa violación (SQLSTATE 23P01)
- **THEN** la respuesta es 409 con el motivo correspondiente, nunca 500, y no persiste ningún turno duplicado

### Requirement: Salud mínima del backend

El sistema SHALL exponer `GET /api/health` que responde 200 cuando la API y la conexión a PostgreSQL están operativas.

#### Scenario: Health check

- **GIVEN** que la API está levantada y PostgreSQL está disponible
- **WHEN** se consulta `GET /api/health`
- **THEN** el sistema responde 200 con estado operativo
