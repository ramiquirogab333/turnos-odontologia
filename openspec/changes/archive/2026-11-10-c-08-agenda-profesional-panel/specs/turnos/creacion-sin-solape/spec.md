# Spec Delta: turnos/creacion-sin-solape

## MODIFIED Requirements

### Requirement: El turno creado bloquea el slot; estados no bloqueantes nunca colisionan

El turno creado por `POST /api/turnos` (alta interna) SHALL nacer en estado bloqueante (`reservado`). Los EXCLUDE parciales SHALL cubrir `reservado`, `confirmado` y `atendido`: un `atendido` SHALL ocupar su horario hasta `fin` aunque se haya marcado antes del inicio (O19 de C-08). `en_espera` (R8), `cancelado` y `ausente` nunca SHALL colisionar ni bloquear, y el paso de `en_espera` a `reservado` queda sujeto a los EXCLUDE.

#### Scenario: Turno creado bloquea su slot

- **GIVEN** que no hay turnos registrados sobre el profesional P ni el sillón S
- **WHEN** se crea un turno en `[10:00, 10:30)` para P y S, y luego se envía un segundo `POST /api/turnos` para P o para S en un rango solapado
- **THEN** la primera creación responde 201 y persiste, y la segunda responde 409 sin persistir nada

#### Scenario: Estados liberados no bloquean

- **GIVEN** que el único turno existente sobre P/S en `[10:00, 10:30)` está en estado `cancelado` o `ausente`
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

#### Scenario: Un atendido marcado antes de su hora sigue ocupando el horario (Happy Path)
- **GIVEN** que el turno de P y S en `[11:00, 11:30)` se marcó `atendido` a las 09:30 del mismo día
- **WHEN** se piden un alta interna, un alta manual del panel y una reserva pública para P o para S en `[11:00, 11:30)`, y se consulta la disponibilidad pública de P
- **THEN** las tres altas responden 409 sin persistir nada, y `[11:00, 11:30)` no figura como libre

#### Scenario: La base rechaza un solape con un atendido y el ausente libera (Error de Negocio)
- **GIVEN** que un turno de P en `[12:00, 12:30)` está `atendido` y otro de P en `[14:00, 14:30)` está `ausente`
- **WHEN** se insertan directamente en la base dos turnos `reservado` de P, en `[12:15, 12:45)` y en `[14:15, 14:45)`
- **THEN** PostgreSQL rechaza el primero con violación de exclusión (SQLSTATE 23P01) y acepta el segundo

#### Scenario: Turno que empieza exactamente en el fin de un atendido (Caso de Borde)
- **GIVEN** que el turno de P y S en `[11:00, 11:30)` está `atendido`
- **WHEN** se crea otro turno para P y S que empieza a las 11:30
- **THEN** el sistema responde 201 y los dos turnos quedan bloqueantes sin solaparse

## ADDED Requirements

### Requirement: El alta interna exige rol de recepción o admin
`POST /api/turnos` SHALL requerir un token de acceso válido con rol `recepcion` o `admin`. Sin token SHALL responder 401 y con otro rol 403, sin crear ningún turno (decisión O3 de C-08).

#### Scenario: Recepción crea un turno interno (Happy Path)
- **GIVEN** un usuario con rol `recepcion` y un horario libre
- **WHEN** envía `POST /api/turnos` con su token
- **THEN** responde 201 y el turno queda `reservado`

#### Scenario: Pedido sin token o con rol sin permiso (Error de Negocio)
- **WHEN** se envía `POST /api/turnos` sin token, o con el token de un usuario `odontologo`
- **THEN** responde 401 en el primer caso y 403 en el segundo, y no se crea ningún turno

#### Scenario: Token de tipo refresh (Caso de Borde)
- **WHEN** se envía `POST /api/turnos` con un token de refresh como Bearer
- **THEN** responde 401 y no se crea ningún turno
