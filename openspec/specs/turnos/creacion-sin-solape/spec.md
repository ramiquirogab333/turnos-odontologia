# turnos/creacion-sin-solape Specification

## Purpose

Esta capability funda la agenda: permite crear un turno que bloquea su slot e impide cualquier solape por profesional o por sillón/box, con garantía a nivel de base de datos que todos los changes posteriores heredan.

## Requirements

### Requirement: Crear turno con fin derivado del tratamiento

El sistema SHALL crear un turno a partir de `profesional_id`, `sillon_id`, `tratamiento_id` e `inicio`, calculando `fin = inicio + duracion_minutos del tratamiento` (RN-TU-04). El endpoint es identity-free: no recibe ni persiste Paciente/nombre/teléfono (primitiva interna que `POST /api/public/turnos` de C-05 reutiliza). Un campo `fin` enviado por el cliente SHALL ser rechazado o ignorado y nunca determinar la duración.

#### Scenario: Creación válida

- **Dado** que existen el profesional P, el sillón S y el tratamiento T (duración 30 minutos), no hay turnos registrados sobre P ni S, y el `inicio` solicitado es futuro
- **Cuando** se envía `POST /api/turnos` con `profesional_id`, `sillon_id`, `tratamiento_id` e `inicio` válido
- **Entonces** el sistema responde 201 y persiste el turno con `fin` exactamente igual a `inicio + 30 minutos`

#### Scenario: Fin enviado por el cliente no prevalece

- **Dado** que existen P, S y T (duración 30 minutos) sin turnos registrados sobre P ni S
- **Cuando** se envía `POST /api/turnos` incluyendo un campo `fin` distinto del derivado
- **Entonces** el sistema responde 422 (si `fin` es campo prohibido) sin persistir nada, o responde 201 ignorando ese valor y persistiendo el turno con el `fin` derivado

#### Scenario: Inicio en el pasado

- **Dado** que existen P, S y T en la base de datos
- **Cuando** se envía `POST /api/turnos` con `inicio` anterior al momento actual
- **Entonces** el sistema responde 422 y no crea ningún turno

#### Scenario: Referencias inexistentes o datos incompletos

- **Dado** el estado actual de la base de datos (con o sin recursos cargados)
- **Cuando** se envía `POST /api/turnos` con `profesional_id`, `sillon_id` o `tratamiento_id` inexistente, o falta alguno de los cuatro campos requeridos (incluido `sillon_id`, siempre NOT NULL)
- **Entonces** el sistema responde 422 y no crea ningún turno

### Requirement: Sin solape por profesional

El sistema SHALL rechazar con 409 y motivo `profesional` todo turno cuyo rango `[inicio, fin)` se solape con otro turno BLOQUEANTE del mismo `profesional_id` (RN-TU-03). Rangos adyacentes (`fin` de uno == `inicio` de otro) NO se consideran solape. La garantía SHALL vivir en la base de datos (constraint EXCLUDE), no solo en la aplicación.

#### Scenario: Solape por profesional

- **Dado** que existe un turno bloqueante del profesional P en `[10:00, 10:30)`
- **Cuando** se envía `POST /api/turnos` para P en `[10:15, 10:45)`
- **Entonces** el sistema responde 409 con motivo `profesional` y no crea ningún turno

#### Scenario: Slots adyacentes no colisionan

- **Dado** que existe un turno bloqueante del profesional P en `[10:00, 10:30)`
- **Cuando** se envía `POST /api/turnos` para P en `[10:30, 11:00)`
- **Entonces** el sistema responde 201 y persiste el turno

#### Scenario: Mismo horario con distinto profesional no colisiona por profesional

- **Dado** que existe un turno bloqueante del profesional P1 en `[10:00, 10:30)` en el sillón S1
- **Cuando** se envía `POST /api/turnos` para el profesional P2 en `[10:00, 10:30)` en el sillón S2
- **Entonces** el sistema responde 201 y persiste el turno (ningún recurso coincide)

### Requirement: Sin solape por sillón/box

El sistema SHALL rechazar con 409 y motivo `sillon` todo turno cuyo rango `[inicio, fin)` se solape con otro turno BLOQUEANTE del mismo `sillon_id` (extensión día-1 de RN-TU-03, Resolución 2026-09-30 nº1). Rangos adyacentes NO se consideran solape. La garantía SHALL vivir en la base de datos (constraint EXCLUDE), no solo en la aplicación.

#### Scenario: Solape por sillón

- **Dado** que existe un turno bloqueante en el sillón S en `[10:00, 10:30)` (de otro profesional)
- **Cuando** se envía `POST /api/turnos` para S en `[10:15, 10:45)`
- **Entonces** el sistema responde 409 con motivo `sillon` y no crea ningún turno

#### Scenario: Mismo horario en distinto sillón no colisiona por sillón

- **Dado** que existe un turno bloqueante en el sillón S1 en `[10:00, 10:30)`
- **Cuando** se envía `POST /api/turnos` para el sillón S2 en `[10:00, 10:30)` con profesional libre
- **Entonces** el sistema responde 201 y persiste el turno

### Requirement: El turno creado bloquea el slot; estados no bloqueantes nunca colisionan

En este change todo turno creado SHALL nacer en estado bloqueante (sin `en_espera`: R8 — `en_espera` no bloqueante llega en C-06). Los EXCLUDE parciales SHALL cubrir solo estados bloqueantes, de modo que `cancelado`, `ausente`, `atendido` y el futuro `en_espera` nunca colisionen ni bloqueen.

#### Scenario: Turno creado bloquea su slot

- **Dado** que no hay turnos registrados sobre el profesional P ni el sillón S
- **Cuando** se crea un turno en `[10:00, 10:30)` para P y S, y luego se envía un segundo `POST /api/turnos` para P o para S en un rango solapado
- **Entonces** la primera creación responde 201 y persiste, y la segunda responde 409 sin persistir nada

#### Scenario: Estados liberados no bloquean

- **Dado** que el único turno existente sobre P/S en `[10:00, 10:30)` está en estado `cancelado` (o `ausente`/`atendido`)
- **Cuando** se envía `POST /api/turnos` para P/S en `[10:00, 10:30)`
- **Entonces** el sistema responde 201 y persiste el turno

### Requirement: Carrera concurrente por el mismo slot

Ante dos `POST /api/turnos` concurrentes sobre el mismo profesional/sillón/horario, el sistema SHALL persistir exactamente un turno (201) y rechazar el otro con 409. La violación del constraint de exclusión (SQLSTATE 23P01) SHALL mapearse a 409 y nunca a 500.

#### Scenario: Doble reserva concurrente

- **Dado** que no hay turnos registrados sobre P ni S, y dos clientes preparan el mismo `POST /api/turnos` (mismo profesional, sillón, inicio y tratamiento)
- **Cuando** ambos envían la solicitud en simultáneo
- **Entonces** exactamente uno recibe 201 con su turno persistido, y el otro recibe 409 con motivo `profesional` o `sillon` sin persistir nada

#### Scenario: Violación del EXCLUDE nunca es 500

- **Dado** que existe un turno bloqueante sobre P/S y un INSERT concurrente viola el constraint de exclusión a nivel DB
- **Cuando** la aplicación procesa esa violación (SQLSTATE 23P01)
- **Entonces** la respuesta es 409 con el motivo correspondiente, nunca 500, y no persiste ningún turno duplicado

### Requirement: Salud mínima del backend

El sistema SHALL exponer `GET /api/health` que responde 200 cuando la API y la conexión a PostgreSQL están operativas.

#### Scenario: Health check

- **Dado** que la API está levantada y PostgreSQL está disponible
- **Cuando** se consulta `GET /api/health`
- **Entonces** el sistema responde 200 con estado operativo
