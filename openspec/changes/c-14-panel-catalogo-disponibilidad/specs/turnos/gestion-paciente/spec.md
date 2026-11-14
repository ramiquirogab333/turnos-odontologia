# Spec Delta

## ADDED Requirements

### Requirement: La reprogramación no usa ítems inactivos
`POST /api/public/gestion/reprogramar` SHALL responder 422 con `motivo: "no_reservable"` y el campo (`profesional_id` o `tratamiento_id`) cuando el profesional o el tratamiento del turno están inactivos, sin modificar el turno ni publicar eventos. Un sillón que no está `activo` SHALL no asignarse (la reprogramación responde 409 por falta de sillón libre). El panel del paciente SHALL explicar que el turno ya no se puede reprogramar por internet y pedir comunicarse con la clínica.

#### Scenario: Reprogramar con todo activo (Happy Path)
- **GIVEN** un turno `reservado` de "Dra. Ana Ficticia" para "Limpieza dental", ambos activos, a más de 24 h
- **WHEN** el paciente envía `POST /api/public/gestion/reprogramar` con otro horario libre dentro de su franja
- **THEN** responde 200 y el turno queda en el horario nuevo, como hasta ahora

#### Scenario: Profesional o tratamiento desactivado (Error de Negocio)
- **GIVEN** que "Dra. Ana Ficticia" (o "Limpieza dental") se desactivó después de tomarse el turno
- **WHEN** el paciente intenta reprogramarlo
- **THEN** responde 422 `no_reservable` con el campo correspondiente, el turno conserva su horario, estado y sillón, y no se publica ningún evento

#### Scenario: Único sillón en mantenimiento (Caso de Borde)
- **GIVEN** que todos los sillones pasaron a `mantenimiento`
- **WHEN** el paciente intenta reprogramar a un horario de la franja
- **THEN** responde 409 sin sillón libre (nunca 500) y el turno no cambia
