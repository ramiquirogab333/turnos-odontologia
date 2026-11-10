# Spec Delta: turnos/agenda-panel

## Purpose
Ajusta las acciones que la agenda de C-08 informa a la odontóloga: desde C-11 (O15) puede figurar `atendido` en sus propios turnos, con las mismas condiciones que para recepción, y nunca `ausente` ni `cancelar`.

Las referencias `(Ox)` sin prefijo remiten a las decisiones de C-11 (`design.md`). Todos los datos de ejemplo son sintéticos (R19).

## MODIFIED Requirements

### Requirement: Contenido de cada turno de la agenda
Cada turno SHALL traer inicio y fin con el offset de la clínica, estado, si bloquea la agenda, origen, profesional, sillón, tratamiento, nombre de la o el paciente, estado de la seña y las acciones que quien consulta puede hacer en ese momento, calculadas por el servidor con las mismas reglas que aplican los endpoints. Para `odontologo` la única acción posible SHALL ser `atendido` (RN-TU-12, O15).

#### Scenario: Turno con seña acreditada (Happy Path)
- **GIVEN** un turno `reservado` de "Carlos Sintético" con seña acreditada de "3000.00" que empieza el 2026-11-17 a las 09:00 (-03:00)
- **WHEN** recepción consulta el 2026-11-16 a las 20:00, con menos de 24 horas de anticipación
- **THEN** el turno trae inicio "2026-11-17T09:00:00-03:00", seña `acreditado` por "3000.00" y ninguna acción disponible

#### Scenario: Un rol sin permisos de escritura (Error de Negocio)
- **GIVEN** un turno `reservado` de la odontóloga que consulta, que empezó hace 20 minutos, y otro suyo `reservado` que empieza en 48 horas
- **WHEN** consulta la agenda
- **THEN** el primero trae solo la acción `atendido` (recepción vería `atendido` y `ausente`) y el segundo la lista vacía (recepción vería `cancelar`); las opciones del panel traen `puede_escribir` en `false`

#### Scenario: Acciones según el momento en un turno manual sin seña (Caso de Borde)
- **GIVEN** un turno manual `reservado`, sin seña, que empieza a las 09:00 con tolerancia de ausente de 10 minutos
- **WHEN** recepción consulta a las 08:00, a las 09:09:59 y a las 09:10:00 del mismo día
- **THEN** el turno trae `sena: null` y origen `manual`; las acciones son `atendido` en las dos primeras consultas, y `atendido` y `ausente` en la tercera

#### Scenario: Acciones del rol odontologo y opciones del panel (Caso de Borde)
- **GIVEN** un usuario `odontologo` sin otro rol más amplio y un turno suyo `reservado` ya iniciado
- **WHEN** consulta la agenda
- **THEN** la única acción posible es `atendido`, en las mismas condiciones que para recepción, y nunca `ausente` ni `cancelar`
- **AND** el indicador `puede_escribir` de las opciones del panel sigue en `false` (no da altas manuales)
