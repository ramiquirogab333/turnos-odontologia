# Spec Delta: turnos/gestion-panel

## ADDED Requirements

### Requirement: El alta manual avisa si el horario está ocupado en Google Calendar
El alta manual de recepción o admin SHALL aceptarse aunque el horario se superponga con una franja ocupada del Google Calendar de la profesional (O10), y la respuesta SHALL incluir `aviso_google_calendar = true`. El turno creado SHALL quedar con un conflicto `solapa_evento_externo` para resolver a mano (RN-GC-02).

#### Scenario: Alta sobre un horario libre en Google (Happy Path)
- **GIVEN** la profesional 7 conectada sin franjas ocupadas a las 11:00
- **WHEN** recepción da de alta un turno a las 11:00
- **THEN** recibe 201 con `aviso_google_calendar = false`

#### Scenario: Alta sobre una franja ocupada en Google (Error de Negocio)
- **GIVEN** una franja ocupada en Google de 15:00 a 16:00 de la profesional 7
- **WHEN** recepción da de alta un turno a las 15:00
- **THEN** recibe 201 con `aviso_google_calendar = true`, el panel muestra "Ese horario figura ocupado en el Google Calendar de la profesional" y tras la sincronización hay un conflicto `solapa_evento_externo` abierto

#### Scenario: Profesional sin Google Calendar conectado (Caso de Borde)
- **GIVEN** la profesional 8 sin conexión
- **WHEN** recepción da de alta un turno
- **THEN** recibe 201 con `aviso_google_calendar = false`
