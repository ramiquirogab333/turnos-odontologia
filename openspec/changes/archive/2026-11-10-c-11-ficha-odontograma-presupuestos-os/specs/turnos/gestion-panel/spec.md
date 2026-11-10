# Spec Delta: turnos/gestion-panel

## Purpose
Modifica la capacidad de C-08 para que la odontóloga pueda marcar `atendido` sus propios turnos (decisión del usuario del 2026-11-10, registrada como O15 en `design.md`). Es lo que destraba la primera visita: al marcar el turno `atendido`, la odontóloga gana acceso a la ficha y el odontograma de esa persona (O2/O4 sin cambios), siempre que el turno esté vinculado con su `Paciente`.

Las referencias `(Ox)` sin prefijo remiten a las decisiones de C-11 (`design.md`); las de C-08 se citan como "C-08 Ox". Todos los datos de ejemplo son sintéticos (R19).

## MODIFIED Requirements

### Requirement: Solo recepción y admin operan la agenda
Las operaciones de escritura bajo `/api/panel/turnos` SHALL requerir rol `recepcion` o `admin` (C-08 O5), con una única excepción (O15): un usuario con rol `odontologo` SHALL poder marcar `atendido` los turnos de la profesional asociada a su usuario. Cualquier otra escritura (alta manual, `ausente`, `cancelar`, vincular paciente) SHALL seguir respondiendo 403 a la odontóloga. Sin token SHALL responder 401.

#### Scenario: Recepción opera (Happy Path)
- **WHEN** un usuario con rol `recepcion` marca un turno ya iniciado como `atendido`
- **THEN** responde 200

#### Scenario: Persona con más de un rol (Caso de Borde)
- **GIVEN** una persona con rol `odontologo` y también `recepcion`
- **WHEN** crea un turno manual en la agenda de otra profesional
- **THEN** se aplica el permiso más amplio y responde 201

#### Scenario: La odontóloga marca atendido su propio turno (Happy Path)
- **GIVEN** que `dra.ficticia@turnos.test` tiene rol `odontologo` y está asociada a la "Dra. Ana Ficticia", y que "Carlos Sintético" tiene un turno `confirmado` con ella hoy a las 11:00, con seña acreditada de "3000.00", y son las 10:45 de la clínica
- **WHEN** la odontóloga lo marca atendido
- **THEN** responde 200, el turno queda `atendido`, la seña sigue `acreditado` y existe un registro de auditoría con su `usuario_id` y origen `marcado_atendido_panel`, sin nombre ni teléfono

#### Scenario: La odontóloga intenta operar (Error de Negocio)
- **WHEN** un usuario con rol `odontologo` intenta crear un turno, marcar uno propio como `ausente` o cancelar uno propio
- **THEN** responde 403 y no cambia nada

#### Scenario: Turno de otra profesional o inexistente (Error de Negocio)
- **GIVEN** un turno `reservado` de hoy del "Dr. Bruno Ficticio", otro suyo ya `ausente`, y un id de turno que no existe
- **WHEN** la Dra. Ana Ficticia marca atendido cada uno
- **THEN** los tres responden 403 `turno_ajeno` con el mismo cuerpo (nunca 404 ni 409), ningún turno cambia y no queda auditoría

#### Scenario: Día anterior, primer instante del día y estado final en un turno propio (Caso de Borde)
- **GIVEN** un turno `reservado` de la Dra. Ana Ficticia que empieza el 2026-11-17 a las 09:00 (-03:00), y otro suyo ya `atendido`
- **WHEN** ella marca atendido el primero a las 23:59:59 del 2026-11-16 y otra vez a las 00:00:00 del 2026-11-17 (-03:00), y después el segundo
- **THEN** el primer intento responde 409 `marcado_no_habilitado` con el instante desde el que se puede, el segundo 200, y el turno ya `atendido` responde 409 `transicion_invalida` sin cambios

#### Scenario: Turno sin paciente vinculado (Caso de Borde)
- **GIVEN** un turno manual `reservado` de hoy de la Dra. Ana Ficticia, con solo nombre "Mateo Prueba" y teléfono "+5491100000012", sin `Paciente` vinculado, y el paciente "Mateo Prueba" (DNI "99000012") registrado sin turnos vinculados
- **WHEN** ella marca el turno atendido, lee la ficha de Mateo, recepción vincula el turno con Mateo y ella vuelve a leerla
- **THEN** el marcado responde 200, la primera lectura 403 `paciente_ajeno` y la segunda 200, sin volver a marcar el turno

#### Scenario: Marcado simultáneo de recepción y la odontóloga (Caso de Borde)
- **GIVEN** un turno `reservado` de hoy de la Dra. Ana Ficticia
- **WHEN** recepción y la odontóloga lo marcan atendido al mismo tiempo
- **THEN** exactamente uno responde 200 y el otro 409 `transicion_invalida`, nunca 500, y queda un solo registro `marcado_atendido_panel`

#### Scenario: Sin sesión o con un token de refresh (Caso de Borde)
- **WHEN** se llama sin token o con un token de tipo refresh
- **THEN** responde 401 y no cambia nada

### Requirement: El marcado atendido de la odontóloga sigue las reglas de recepción
El marcado `atendido` de un usuario `odontologo` SHALL aplicar las mismas reglas de estado y horario que a recepción (RN-TU-12: desde `reservado` o `confirmado` y desde las 00:00 del día local del turno) y la misma auditoría (`marcado_atendido_panel`). Ningún rol SHALL poder deshacer un `atendido` (estado final). Un turno sin `Paciente` vinculado SHALL poder marcarse `atendido` igual, sin otorgar acceso clínico hasta vincularlo (O1, O2).

#### Scenario: Mismas reglas, auditoría y estado final (Caso de Borde)
- **GIVEN** un turno `reservado` de la Dra. Ana Ficticia que empieza el 2026-11-17 a las 09:00 (-03:00), y otro suyo ya `atendido`
- **WHEN** ella los marca atendido a las 00:00:00 del 2026-11-17 (-03:00)
- **THEN** el primero responde 200 vía `POST /api/panel/turnos/{id}/atendido` con auditoría `marcado_atendido_panel` y su `usuario_id`, y el segundo 409 `transicion_invalida` sin cambios

### Requirement: La propiedad del turno se verifica sin revelar su existencia
La propiedad del turno SHALL verificarse antes que el estado y el horario, en la misma transacción y bajo el mismo bloqueo del turno. Para un turno de otra profesional o inexistente, la odontóloga SHALL recibir 403 `turno_ajeno` con el mismo cuerpo en ambos casos, sin revelar si el turno existe ni en qué estado está; sin profesional asociado SHALL recibir 403 `sin_profesional_asociado`. Ningún rechazo SHALL cambiar datos ni dejar auditoría.

#### Scenario: Ajeno, inexistente o sin profesional asociado (Error de Negocio)
- **GIVEN** un turno de hoy del "Dr. Bruno Ficticio", un id inexistente y un usuario `odontologo` sin profesional asociada
- **WHEN** la Dra. Ana Ficticia marca atendido los dos primeros y el usuario sin profesional intenta marcar cualquiera
- **THEN** la Dra. Ana recibe 403 `turno_ajeno` idéntico en ambos casos y el otro usuario 403 `sin_profesional_asociado`, sin cambios ni auditoría

### Requirement: Pantallas de alta manual y acciones sobre el turno
El panel SHALL ofrecer a recepción y admin el formulario de alta manual y las acciones que el servidor informa para cada turno. Marcar ausente y cancelar SHALL pedir confirmación indicando qué pasa con la seña. A un usuario `odontologo` el panel SHALL mostrarle únicamente la acción «Marcar atendido» donde el servidor la informe, y ninguna otra acción de escritura ni el alta manual. La pantalla SHALL funcionar a 360 px de ancho (R3).

#### Scenario: Alta desde la pantalla (Happy Path)
- **GIVEN** recepción con sesión iniciada
- **WHEN** toca "Nuevo turno", completa los datos, elige un horario libre y confirma
- **THEN** ve el turno en la agenda y el código de gestión una única vez, para compartirlo

#### Scenario: La odontóloga marca atendido desde la agenda (Happy Path)
- **GIVEN** la Dra. Ana Ficticia con sesión iniciada en un viewport de 360 px y un turno `reservado` suyo de "Carlos Sintético" para hoy
- **WHEN** toca "Marcar atendido" y confirma el diálogo
- **THEN** el turno figura `atendido`, el botón desaparece y en ningún momento ve "Marcar ausente", "Cancelar turno" ni "Nuevo turno"

#### Scenario: Horario tomado mientras se completa (Error de Negocio)
- **GIVEN** que otro turno ocupó el horario elegido
- **WHEN** recepción confirma el alta
- **THEN** ve "Ese horario ya no está disponible" con alternativas, y puede elegir una sin volver a cargar los datos

#### Scenario: Confirmación del ausente (Caso de Borde)
- **GIVEN** un turno iniciado con seña acreditada de "3000.00"
- **WHEN** recepción toca "Marcar ausente"
- **THEN** el diálogo avisa que la seña de $ 3.000,00 no se devuelve y que el cambio no se puede deshacer, y nada cambia hasta confirmar

#### Scenario: Turno propio de un día futuro (Caso de Borde)
- **GIVEN** la Dra. Ana Ficticia con un turno `reservado` suyo para dentro de 26 horas
- **WHEN** abre la agenda de ese día
- **THEN** ve el turno sin ningún botón de acción

#### Scenario: Alcance de la acción de la odontóloga (Caso de Borde)
- **GIVEN** la Dra. Ana Ficticia con sesión iniciada
- **WHEN** abre la agenda
- **THEN** «Marcar atendido» aparece solo en sus propios turnos, desde el día del turno (O15), con el mismo diálogo de confirmación que a recepción
