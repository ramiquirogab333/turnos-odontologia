# Spec Delta: turnos/creacion-sin-solape

## MODIFIED Requirements

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
