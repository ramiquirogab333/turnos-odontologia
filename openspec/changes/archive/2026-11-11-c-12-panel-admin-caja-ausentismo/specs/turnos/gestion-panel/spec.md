# Spec Delta: turnos/gestion-panel

## ADDED Requirements

### Requirement: Deshacer un atendido marcado por error
`POST /api/panel/turnos/{id}/deshacer-atendido` con un `motivo` del catálogo (`turno_equivocado`, `paciente_no_asistio`, `otro`) SHALL devolver un turno `atendido` a `reservado` (O7). Solo `recepcion` y `admin` SHALL poder hacerlo; la odontóloga SHALL recibir 403 también sobre sus turnos (C-11 O15). La seña no SHALL cambiar y el turno SHALL seguir ocupando su horario. Es la única salida del estado `atendido`.

#### Scenario: Recepción corrige un marcado (Happy Path)
- **GIVEN** un turno de ayer marcado `atendido` por error, con seña acreditada de "3000.00"
- **WHEN** recepción envía deshacer con motivo `paciente_no_asistio`
- **THEN** recibe 200, el turno queda `reservado`, el pago sigue `acreditado` y el horario sigue sin figurar como libre

#### Scenario: Estado que no es atendido, rol sin permiso o motivo inválido (Error de Negocio)
- **WHEN** recepción deshace un turno `ausente`, la Dra. Ana Ficticia deshace un turno `atendido` suyo, y recepción envía el motivo "porque sí"
- **THEN** recibe 409 `transicion_invalida`, 403 y 422 respectivamente, y ningún turno cambia

#### Scenario: Deshacer y volver a marcar (Caso de Borde)
- **GIVEN** un turno de hoy que empezó hace 30 minutos, marcado `atendido` por error y con seña acreditada
- **WHEN** recepción lo deshace y después lo marca `ausente`
- **THEN** el turno queda `ausente`, la seña `no_reembolsado` (R9) y las dos acciones quedan auditadas

### Requirement: Plazo para deshacer un atendido
Deshacer SHALL aceptarse hasta 7 días corridos después del inicio del turno, comparando instantes absolutos; exactamente 7 días se acepta (O8). Pasado el plazo SHALL responder 409 `plazo_vencido` con el instante límite en la hora de la clínica. Un id inexistente SHALL responder 404.

#### Scenario: Corrección al día siguiente (Happy Path)
- **GIVEN** un turno `atendido` que empezó hace 26 horas
- **WHEN** admin lo deshace
- **THEN** recibe 200 y el turno queda `reservado`

#### Scenario: Turno de hace diez días (Error de Negocio)
- **GIVEN** un turno `atendido` que empezó hace 10 días
- **WHEN** recepción lo deshace
- **THEN** recibe 409 `plazo_vencido` con el instante límite, y el turno sigue `atendido`

#### Scenario: Límite exacto y turno inexistente (Caso de Borde)
- **GIVEN** un turno `atendido` que empezó el 2026-11-10 a las 09:00 (-03:00)
- **WHEN** recepción lo deshace a las 09:00:00 del 2026-11-17, otro igual a las 09:00:01, y un id que no existe
- **THEN** el primero se acepta, el segundo responde 409 `plazo_vencido` y el tercero 404

### Requirement: Deshacer un atendido queda auditado y no avisa a nadie
Cada corrección aceptada SHALL dejar, en la misma transacción, un registro de auditoría con el usuario, el turno, el estado anterior y nuevo, el motivo del catálogo y el origen `deshacer_atendido_panel` (RN-GL-01), sin nombre ni teléfono (R19). No SHALL publicar eventos de calendario ni de recordatorios. Dos correcciones simultáneas SHALL dejar una sola.

#### Scenario: Corrección auditada (Happy Path)
- **WHEN** recepción deshace un `atendido` con motivo `turno_equivocado`
- **THEN** existe un registro con su `usuario_id`, `atendido` → `reservado`, el motivo y el origen `deshacer_atendido_panel`, y no se publicó ningún evento

#### Scenario: Corrección rechazada (Error de Negocio)
- **WHEN** una corrección se rechaza por `plazo_vencido` o `transicion_invalida`
- **THEN** no queda ningún registro nuevo de auditoría

#### Scenario: Dos correcciones a la vez (Caso de Borde)
- **GIVEN** un turno `atendido` dentro del plazo
- **WHEN** recepción y admin lo deshacen al mismo tiempo
- **THEN** uno responde 200 y el otro 409 `transicion_invalida`, y hay un solo registro de auditoría

### Requirement: Deshacer un atendido recalcula el acceso clínico
El acceso de la odontóloga a la ficha y al odontograma SHALL calcularse con los turnos `atendido` que existen en cada momento (C-11 O2, O16): un `atendido` deshecho deja de contar. Lo que se haya escrito mientras el turno figuraba `atendido` SHALL conservarse (O9).

#### Scenario: Quedan otras atenciones (Happy Path)
- **GIVEN** "Mateo Prueba" con dos turnos `atendido` con la Dra. Ana Ficticia, uno de hace un mes y el de ayer, marcado por error
- **WHEN** recepción deshace el de ayer
- **THEN** la odontóloga sigue leyendo y escribiendo su ficha

#### Scenario: Era su única atención (Error de Negocio)
- **GIVEN** "Lucía Ejemplo" cuyo único turno `atendido` con la Dra. Ana Ficticia es el marcado por error
- **WHEN** recepción lo deshace y la odontóloga pide la ficha
- **THEN** recibe 403 `paciente_ajeno`

#### Scenario: Registros cargados antes de la corrección (Caso de Borde)
- **GIVEN** que, antes de la corrección, la odontóloga cargó un registro de odontograma de "Lucía Ejemplo"
- **WHEN** recepción deshace el `atendido` y luego consulta el odontograma
- **THEN** el registro sigue en el historial con su autora

### Requirement: Pantalla para deshacer un atendido
El panel SHALL mostrar a recepción y admin la acción «Deshacer atendido» donde el servidor la informe, con un diálogo que pida el motivo y avise que el turno vuelve a `reservado` y que la odontóloga puede perder el acceso a la ficha. A un usuario `odontologo` no SHALL mostrársela. SHALL funcionar a 360 px (R3).

#### Scenario: Corrección desde la agenda (Happy Path)
- **GIVEN** recepción en un viewport de 360 px con un turno `atendido` de hoy
- **WHEN** toca «Deshacer atendido», elige el motivo "La persona no vino" y confirma
- **THEN** el turno figura `reservado` y vuelve a ofrecer «Marcar atendido» y «Marcar ausente»

#### Scenario: La odontóloga mira su turno atendido (Error de Negocio)
- **GIVEN** la Dra. Ana Ficticia con un turno suyo `atendido` de hoy
- **WHEN** abre la agenda
- **THEN** no ve «Deshacer atendido»

#### Scenario: El plazo venció mientras el diálogo estaba abierto (Caso de Borde)
- **GIVEN** un diálogo de corrección abierto y un turno cuyo plazo vence antes de confirmar
- **WHEN** recepción confirma
- **THEN** ve "Ya pasaron 7 días: este turno no se puede corregir" y el turno sigue `atendido`
