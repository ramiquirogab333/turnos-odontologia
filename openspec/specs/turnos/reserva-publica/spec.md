# turnos/reserva-publica Specification

## Purpose
Provee la capacidad para que pacientes no autenticados consulten disponibilidad horaria en tiempo real y reserven turnos odontológicos ingresando únicamente nombre y teléfono, calculando automáticamente la duración del tratamiento y garantizando la ausencia de solapamiento por profesional y sillón.

## Requirements

### Requirement: Consulta de disponibilidad de turnos libres
El sistema SHALL permitir la consulta pública de franjas horarias disponibles para una fecha o rango de fechas, profesional y tratamiento determinado, considerando la duración del tratamiento y los turnos existentes. Solo los turnos que ocupan agenda (`reservado`, `confirmado`, `atendido`) ocupan un horario; un `atendido` lo ocupa hasta su `fin` aunque se haya marcado antes (O19 de C-08). Las pre-reservas `en_espera` (R8) y los turnos `ausente` o `cancelado` no lo ocupan.

#### Scenario: Consulta de disponibilidad con horarios libres
- **WHEN** un paciente solicita disponibilidad para un profesional y un tratamiento de 30 minutos en una fecha laboral
- **THEN** el sistema devuelve una lista de intervalos de inicio y fin donde tanto el profesional como al menos un sillón físico están desocupados con código HTTP 200

#### Scenario: Una pre-reserva en espera no ocupa el horario (Caso de Borde)
- **GIVEN** que el único turno del profesional P el 2026-11-16 es un `en_espera` de 10:00 a 10:30
- **WHEN** un paciente consulta la disponibilidad de P para ese día con un tratamiento de 30 minutos
- **THEN** el horario de 10:00 a 10:30 figura como libre

#### Scenario: Un turno con seña acreditada ocupa el horario (Error de Negocio)
- **GIVEN** que el profesional P tiene un turno `reservado` (seña acreditada) de 10:00 a 10:30 el 2026-11-16
- **WHEN** un paciente consulta la disponibilidad de P para ese día
- **THEN** el horario de 10:00 a 10:30 no figura como libre

#### Scenario: Un atendido marcado antes de su hora sigue ocupado (Happy Path)
- **GIVEN** que el turno de P de 11:00 a 11:30 del 2026-11-16 se marcó `atendido` a las 09:30 de ese día
- **WHEN** un paciente consulta la disponibilidad de P para ese día o intenta reservar a las 11:00
- **THEN** el horario de 11:00 a 11:30 no figura como libre y la reserva responde 409 con alternativas

#### Scenario: El horario de un ausente vuelve a estar libre (Error de Negocio)
- **GIVEN** que el turno de P de 12:00 a 12:30 del 2026-11-16 se marcó `ausente` a las 12:10
- **WHEN** a las 12:11 un paciente consulta la disponibilidad de P para ese día con un tratamiento de 15 minutos
- **THEN** el ausente ya no cuenta como ocupación: los inicios futuros dentro de la franja entre 12:11 y 12:30, como 12:15, figuran como libres

#### Scenario: Turno que empieza en el fin de un atendido (Caso de Borde)
- **GIVEN** que el turno de P de 11:00 a 11:30 del 2026-11-16 está `atendido`
- **WHEN** un paciente consulta la disponibilidad de P para ese día con un tratamiento de 30 minutos
- **THEN** el horario de 11:30 a 12:00 figura como libre

### Requirement: Reserva pública de turnos sin registro obligatorio
El sistema SHALL permitir la creación de un turno odontológico mediante la provisión de nombre del paciente, teléfono de contacto en formato E.164, tratamiento, profesional y horario de inicio válido, calculando la hora de fin según la duración del tratamiento. El turno SHALL nacer en `en_espera`, sin bloquear agenda, con un vencimiento y la seña a pagar, salvo un tratamiento exento de seña (C-06).

#### Scenario: Creación exitosa de reserva pública (Happy Path)
- **WHEN** un paciente envía nombre "Carlos Sintético", teléfono "+5491144445555", tratamiento ID 1 (duración 30 min, precio base 10000.00, seña del 30%) e inicio "2026-11-15T10:00:00-03:00" en un slot libre
- **THEN** el sistema registra el turno en estado "en_espera", asigna un sillón disponible de forma tentativa, calcula fin "2026-11-15T10:30:00-03:00", devuelve código HTTP 201 con un código único de gestión y un bloque `sena` con monto "3000.00", `vence_en` y los medios habilitados, y no crea ningún Paciente

#### Scenario: Intento de reserva en horario solapado (Error de Negocio)
- **WHEN** un paciente intenta reservar un slot donde el profesional o el sillón asignado ya tienen un turno bloqueante (`reservado` o `confirmado`) superpuesto (violación RN-TU-03)
- **THEN** el sistema rechaza la transacción con código HTTP 409 Conflict, detalla el motivo del solape, no persiste ningún registro y retorna una lista de franjas horarias alternativas próximas

#### Scenario: Validación de contacto y límites en el borde (Caso de Borde)
- **WHEN** un paciente intenta reservar ingresando un número de teléfono con longitud insuficiente o caracteres inválidos ("1234") en el último slot del horario de atención clínica
- **THEN** el sistema rechaza la solicitud con código HTTP 422 Unprocessable Entity, reporta el error de validación en el campo teléfono y no bloquea el slot ni crea paciente huérfano

#### Scenario: Dos pacientes reservan el mismo horario libre (Caso de Borde)
- **GIVEN** que el horario de 10:00 a 10:30 del profesional P está libre
- **WHEN** dos pacientes envían `POST /api/public/turnos` para ese horario en simultáneo
- **THEN** ambos reciben 201 con turnos `en_espera` distintos, ninguno bloquea la agenda y el primero cuya seña se acredite se queda con el horario

### Requirement: Catálogo público de tratamientos
El sistema SHALL exponer sin autenticación un listado de solo lectura de los tratamientos reservables, con identificador, nombre, duración en minutos y precio base orientativo, ordenado por nombre, para que el paciente elija el tratamiento antes de consultar disponibilidad.

#### Scenario: Listado de tratamientos sin autenticación
- **WHEN** un paciente sin sesión solicita `GET /api/public/tratamientos` y existe el tratamiento "Limpieza" de 30 minutos con precio base 1000.00
- **THEN** el sistema responde HTTP 200 con una lista que incluye `id`, `nombre`, `duracion_minutos` y `precio_base` ("1000.00") de ese tratamiento, sin exigir cabecera de autorización

#### Scenario: Catálogo de tratamientos vacío (Caso de Borde)
- **WHEN** un paciente solicita `GET /api/public/tratamientos` y no hay tratamientos cargados
- **THEN** el sistema responde HTTP 200 con una lista vacía, sin error

### Requirement: Catálogo público de profesionales con agenda vigente
El sistema SHALL exponer sin autenticación un listado de solo lectura de los profesionales que tengan al menos una franja de disponibilidad activa (RN-TU-07), con identificador, nombre y especialidad, sin exponer la matrícula, ordenado por nombre. El paciente SHALL poder elegir el profesional en el paso 1 del flujo de reserva, porque la disponibilidad se consulta por profesional.

#### Scenario: Solo aparecen profesionales con franja vigente
- **WHEN** un paciente solicita `GET /api/public/profesionales` y existen un profesional con una franja activa y otro sin franjas activas
- **THEN** el sistema responde HTTP 200 solo con el profesional que tiene franja activa, con `id`, `nombre` y `especialidad`, y sin el campo de matrícula

#### Scenario: Profesional con varias franjas aparece una sola vez (Caso de Borde)
- **WHEN** un profesional tiene dos franjas activas en distintos días y un paciente solicita `GET /api/public/profesionales`
- **THEN** el sistema devuelve a ese profesional una sola vez en la lista
