# catalogo/tratamientos-disponibilidad Specification

## Purpose
Añade CRUD admin para los catálogos `Tratamiento`, `Profesional`, `Sillon` y `Disponibilidad` bajo `/api/admin/`, protegidos por RBAC de C-03, con esquemas Pydantic de entrada/salida (R15), servicios async sobre `BaseRepository[T]` + `UnitOfWork` (R13, R16), migración Alembic 004 reversible con constraints de catálogo (R4, R6, R14) y auditoría en `RegistroAuditoria` (RN-GL-01). No modifica capacidades de C-01/C-02/C-03; los datos son 100% sintéticos (R19).

## Requirements

### Requirement: CRUD admin de Tratamiento
El sistema SHALL permitir a rol `recepcion`/`admin` crear, leer, actualizar y eliminar tratamientos (nombre, `duracion_minutos`, `precio_base`, `activo`), denegando a otros roles con 403. SHALL rechazar con 422 una `duracion_minutos` fuera de 5 a 480 o que no sea múltiplo de 5, y un `precio_base` negativo o mayor que 99999999.99. Un tratamiento nuevo nace activo.

#### Scenario: POST /api/admin/tratamientos con rol recepción → 201 creado (Happy Path)
- **GIVEN** que existe un usuario autenticado con rol `recepcion`
- **WHEN** se envía `POST /api/admin/tratamientos` con body sintético `{ "nombre": "Limpieza Dental", "duracion_minutos": 30, "precio_base": "5000.00" }`
- **THEN** el sistema responde 201 con el tratamiento creado (id, nombre, duracion_minutos=30, precio_base="5000.00", activo=true) y registra la acción en `RegistroAuditoria` (RN-GL-01)

#### Scenario: duracion_minutos <= 0 → 422 CHECK constraint (Error de Negocio)
- **GIVEN** que existe un usuario autenticado con rol `recepcion`
- **WHEN** se envía `POST /api/admin/tratamientos` con `duracion_minutos` = 0 (o negativo)
- **THEN** el sistema responde 422 por violación del `CHECK duracion_minutos > 0` y no crea el tratamiento

#### Scenario: duracion_minutos fuera de rango → 422 (Error de Negocio)
- **GIVEN** que existe un usuario autenticado con rol `recepcion`
- **WHEN** se envía `POST /api/admin/tratamientos` con `duracion_minutos` = 7 o 485
- **THEN** el sistema responde 422 nombrando el campo `duracion_minutos` y no crea el tratamiento

#### Scenario: precio_base mayor que el máximo → 422 (Error de Negocio)
- **WHEN** se envía `PUT /api/admin/tratamientos/{id}` con `precio_base` = "100000000.00"
- **THEN** el sistema responde 422 nombrando el campo `precio_base` (nunca 500) y el tratamiento no cambia

#### Scenario: rol odontólogo intenta POST /api/admin/tratamientos → 403 (Caso de Borde / RBAC)
- **GIVEN** que existe un usuario autenticado con rol `odontologo`
- **WHEN** se envía `POST /api/admin/tratamientos` con body válido
- **THEN** el sistema responde 403 (RBAC denegado: solo recepcion/admin pueden escribir catálogo)

#### Scenario: Duraciones límite (Caso de Borde)
- **WHEN** se crean tratamientos con `duracion_minutos` 5 y 480
- **THEN** ambos responden 201

### Requirement: CRUD admin de Profesional y Sillon
El sistema SHALL permitir CRUD completo de profesionales (nombre, matricula, especialidad) y sillones (nombre, estado) a rol `recepcion`/`admin`.

#### Scenario: CRUD completo con rol recepción → 201/200/204 (Happy Path)
- **GIVEN** que existe un usuario autenticado con rol `recepcion`
- **WHEN** se ejecuta `POST /api/admin/profesionales` (crear), `GET /api/admin/profesionales/{id}` (leer), `PUT /api/admin/profesionales/{id}` (actualizar) y `DELETE /api/admin/profesionales/{id}` (eliminar)
- **THEN** se obtienen respuestas 201, 200, 200 y 204 respectivamente; análogo para `Sillon` con `{ "nombre": "Sillon 1", "estado": "activo" }`

### Requirement: CRUD admin de Disponibilidad
El sistema SHALL permitir crear una franja horaria de disponibilidad con FK válidas a `Profesional` y (opcional) `Sillon`.

#### Scenario: crear franja horaria con FK válidas → 201 (Happy Path)
- **GIVEN** que existe un usuario autenticado con rol `recepcion`, un `Profesional` válido y un `Sillon` válido
- **WHEN** se envía `POST /api/admin/disponibilidad` con `{ "profesional_id": <id_profesional>, "dia_semana": 1, "hora_inicio": "09:00", "hora_fin": "17:00", "sillon_defecto_id": <id_sillon> }`
- **THEN** el sistema responde 201 con la disponibilidad creada y valida `dia_semana BETWEEN 0 AND 6` y `hora_fin > hora_inicio` (422 si se violan)

### Requirement: Baja lógica de tratamientos, profesionales y franjas
Tratamientos, profesionales y franjas SHALL tener un campo `activo` que recepción/admin leen y cambian con `PUT`; los sillones lo expresan con su `estado`. Un ítem inactivo SHALL conservarse con su historia y SHALL dejar de ofrecerse para turnos nuevos. Cada cambio de `activo` SHALL auditarse como `UPDATE` con antes y después.

#### Scenario: Desactivar un tratamiento (Happy Path)
- **GIVEN** "Ortodoncia demo" activo con turnos pasados
- **WHEN** recepción envía `PUT /api/admin/tratamientos/{id}` con `{ "activo": false }`
- **THEN** responde 200 con `activo=false`, el tratamiento sigue en `GET /api/admin/tratamientos` y la auditoría guarda `activo` true → false con la IP del pedido

#### Scenario: Campo activo inválido (Error de Negocio)
- **WHEN** se envía `PUT /api/admin/profesionales/{id}` con `{ "activo": "quizas" }`
- **THEN** responde 422 y el profesional no cambia ni se audita nada

#### Scenario: Reactivar (Caso de Borde)
- **GIVEN** una franja pausada (`activo=false`)
- **WHEN** se envía `PUT /api/admin/disponibilidad/{id}` con `{ "activo": true }`
- **THEN** responde 200 y la franja vuelve a ofrecer horarios libres, salvo que se superponga con otra franja activa (409 `franja_superpuesta`)

### Requirement: Borrar un ítem en uso responde 409
`DELETE` de un tratamiento, profesional o sillón que tenga turnos (de cualquier estado), líneas de presupuesto o una conexión de calendario SHALL responder 409 con `motivo: "en_uso"` y un mensaje que sugiere desactivarlo, sin borrar nada ni auditar. Una franja SHALL poder borrarse siempre: los turnos no dependen de ella.

#### Scenario: Borrar un sillón sin uso (Happy Path)
- **GIVEN** "Sillón de prueba" sin turnos
- **WHEN** recepción envía `DELETE /api/admin/sillones/{id}`
- **THEN** responde 204 y se audita `DELETE`

#### Scenario: Borrar un profesional con turnos (Error de Negocio)
- **GIVEN** "Dra. Ana Ficticia" con un turno `cancelado` del mes pasado
- **WHEN** recepción envía `DELETE /api/admin/profesionales/{id}`
- **THEN** responde 409 `en_uso` (nunca 500), la profesional y sus franjas siguen y no hay registro de auditoría nuevo

#### Scenario: Borrar una franja con turnos futuros (Caso de Borde)
- **GIVEN** una franja del lunes de 14:00 a 18:00 con 3 turnos futuros `reservado`
- **WHEN** recepción envía `DELETE /api/admin/disponibilidad/{id}`
- **THEN** responde 204, los 3 turnos siguen `reservado` con su horario y se audita `DELETE`

### Requirement: Los cambios del catálogo no alteran turnos existentes
Cambiar duración o precio de un tratamiento, desactivar un ítem, cambiar el estado de un sillón o pausar, editar o borrar una franja SHALL dejar intactos los turnos existentes (estado, inicio, fin, sillón, seña). La duración y el precio nuevos SHALL aplicarse solo a turnos que se crean o reprograman después del cambio (RN-TU-04).

#### Scenario: Alargar un tratamiento con turnos tomados (Happy Path)
- **GIVEN** un turno futuro de "Limpieza dental" de 10:00 a 10:45 y una seña acreditada de 7500.00
- **WHEN** recepción cambia la duración a 60 y el precio a 30000.00
- **THEN** el turno sigue de 10:00 a 10:45 con la misma seña, y los horarios libres nuevos de ese tratamiento duran 60 minutos

#### Scenario: Desactivar un profesional con turnos futuros no los cancela (Error de Negocio)
- **GIVEN** "Dr. Juan Ejemplo" con 2 turnos futuros `confirmado`
- **WHEN** recepción lo desactiva
- **THEN** responde 200, los 2 turnos siguen `confirmado` y en la agenda, y no se envía ningún aviso ni se mueve ninguna seña

#### Scenario: Reprogramar después del cambio de duración (Caso de Borde)
- **GIVEN** un turno de 45 minutos tomado antes de que su tratamiento pasara a 60 minutos
- **WHEN** el paciente lo reprograma a otro día
- **THEN** el turno nuevo dura 60 minutos (duración vigente)

### Requirement: Consulta del impacto de un cambio
`GET /api/admin/{tratamientos|profesionales|sillones|disponibilidad}/{id}/impacto` SHALL devolver a recepción/admin la cantidad de turnos futuros vigentes (`en_espera`, `reservado`, `confirmado`) que usan el ítem —para una franja, los del mismo profesional que empiezan ese día de la semana dentro de su horario, en la hora de la clínica— y la fecha del primero, sin datos de pacientes.

#### Scenario: Impacto de una franja (Happy Path)
- **GIVEN** una franja del lunes de 14:00 a 18:00 y turnos futuros de esa profesional el lunes 14:30 (`reservado`), el lunes 17:30 (`en_espera`) y el lunes 18:00 (`reservado`)
- **WHEN** recepción pide su impacto
- **THEN** responde 200 con `turnos_futuros: 2` y la fecha del primero, sin nombres ni teléfonos

#### Scenario: Impacto pedido por la odontóloga o de un id inexistente (Error de Negocio)
- **WHEN** `dra.ficticia@turnos.test` pide el impacto de un tratamiento, o recepción pide el de un id que no existe
- **THEN** responde 403 o 404 respectivamente

#### Scenario: Turnos pasados, cancelados o ausentes no cuentan (Caso de Borde)
- **GIVEN** un tratamiento cuyo único uso es un turno `atendido` de ayer y un turno `cancelado` de la semana próxima
- **WHEN** recepción pide su impacto
- **THEN** responde `turnos_futuros: 0` y fecha `null`

### Requirement: Franjas activas sin superposición
Dos franjas activas del mismo profesional y día de la semana SHALL no superponerse; la base de datos SHALL garantizarlo. Crear, editar o reactivar una franja que se superpone SHALL responder 409 `franja_superpuesta` indicando la franja con la que choca. Las franjas contiguas SHALL aceptarse.

#### Scenario: Franja de otro día o de otro profesional (Happy Path)
- **GIVEN** una franja activa de "Dra. Ana Ficticia" el lunes de 09:00 a 13:00
- **WHEN** se crea una franja de la misma profesional el martes de 09:00 a 13:00 y otra de "Dr. Juan Ejemplo" el lunes de 09:00 a 13:00
- **THEN** ambas responden 201

#### Scenario: Superposición rechazada (Error de Negocio)
- **WHEN** se crea una franja de "Dra. Ana Ficticia" el lunes de 12:00 a 15:00
- **THEN** responde 409 `franja_superpuesta` con el id y el horario de la franja de 09:00 a 13:00, y no se crea nada

#### Scenario: Dos altas superpuestas al mismo tiempo (Caso de Borde)
- **WHEN** llegan en simultáneo dos `POST` de franjas del lunes de 10:00 a 12:00 y de 11:00 a 14:00 para la misma profesional
- **THEN** una responde 201 y la otra 409 `franja_superpuesta` (la base decide), nunca 500

### Requirement: Edición de franjas validada con los valores guardados
Un `PUT` parcial de una franja SHALL validarse combinando lo enviado con lo guardado: `hora_fin` mayor que `hora_inicio` y `dia_semana` entre 0 y 6. Si no se cumple SHALL responder 422 sin cambiar nada (nunca 500).

#### Scenario: Cambiar solo el fin (Happy Path)
- **GIVEN** una franja de 09:00 a 13:00
- **WHEN** se envía `PUT` con `{ "hora_fin": "14:00" }`
- **THEN** responde 200 con la franja de 09:00 a 14:00

#### Scenario: Fin anterior al inicio guardado (Error de Negocio)
- **GIVEN** una franja de 09:00 a 13:00
- **WHEN** se envía `PUT` con `{ "hora_fin": "08:00" }`
- **THEN** responde 422 nombrando `hora_fin` y la franja sigue de 09:00 a 13:00

#### Scenario: Fin igual al inicio (Caso de Borde)
- **WHEN** se envía `PUT` con `{ "hora_inicio": "13:00" }` sobre una franja de 09:00 a 13:00
- **THEN** responde 422

### Requirement: Nombres y matrículas únicos
El nombre de un tratamiento y el de un sillón SHALL ser únicos sin distinguir mayúsculas ni espacios en los extremos, y la matrícula de un profesional SHALL ser única con el mismo criterio. Un duplicado SHALL responder 409 `duplicado` con el campo; la base de datos SHALL garantizarlo.

#### Scenario: Nombre nuevo (Happy Path)
- **WHEN** se crea el tratamiento "Control de prueba"
- **THEN** responde 201

#### Scenario: Nombre repetido con otras mayúsculas (Error de Negocio)
- **GIVEN** el tratamiento "Limpieza dental"
- **WHEN** se crea " limpieza DENTAL "
- **THEN** responde 409 `duplicado` con campo `nombre` y no se crea nada

#### Scenario: Renombrar al mismo nombre (Caso de Borde)
- **GIVEN** el sillón "Sillón 1"
- **WHEN** se envía `PUT` con `{ "nombre": "Sillón 1" }` sobre ese mismo sillón
- **THEN** responde 200 sin error de duplicado
