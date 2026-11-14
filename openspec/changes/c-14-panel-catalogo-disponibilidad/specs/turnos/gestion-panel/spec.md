# Spec Delta

## ADDED Requirements

### Requirement: El alta manual no usa ítems inactivos
`POST /api/panel/turnos` SHALL responder 422 con `motivo: "no_reservable"` y el campo cuando el tratamiento o el profesional están inactivos, o cuando el sillón indicado no está `activo`, sin crear nada. `GET /api/panel/agenda/opciones` SHALL informar `activo` en cada tratamiento y profesional; la pantalla de alta manual SHALL ofrecer solo los activos, y los filtros de la agenda SHALL seguir mostrando a los inactivos marcados como tales.

#### Scenario: Alta con ítems activos (Happy Path)
- **GIVEN** "Dra. Ana Ficticia" y "Limpieza dental" activos y un horario libre dentro de su franja
- **WHEN** recepción crea un turno manual para "Carlos Sintético"
- **THEN** responde 201 como hasta ahora

#### Scenario: Alta con un profesional inactivo (Error de Negocio)
- **GIVEN** "Dr. Juan Ejemplo" inactivo
- **WHEN** recepción envía `POST /api/panel/turnos` con ese profesional
- **THEN** responde 422 `no_reservable` con campo `profesional_id` y no se crea ningún turno ni registro de auditoría

#### Scenario: Filtrar la agenda por un profesional inactivo (Caso de Borde)
- **GIVEN** "Dr. Juan Ejemplo" inactivo con 2 turnos futuros
- **WHEN** recepción abre la agenda
- **THEN** el filtro de profesional lo ofrece con la marca "(inactivo)", filtrar por él muestra sus 2 turnos, y el formulario "Nuevo turno" no lo ofrece
