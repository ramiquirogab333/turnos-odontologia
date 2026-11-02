# Spec Delta: turnos/reserva-publica

## Purpose
Provee la capacidad para que pacientes no autenticados consulten disponibilidad horaria en tiempo real y reserven turnos odontológicos ingresando únicamente nombre y teléfono, calculando automáticamente la duración del tratamiento y garantizando la ausencia de solapamiento por profesional y sillón.

## ADDED Requirements

### Requirement: Consulta de disponibilidad de turnos libres
El sistema SHALL permitir la consulta pública de franjas horarias disponibles para una fecha o rango de fechas, profesional y tratamiento determinado, considerando la duración del tratamiento y los turnos existentes.

#### Scenario: Consulta de disponibilidad con horarios libres
- **WHEN** un paciente solicita disponibilidad para un profesional y un tratamiento de 30 minutos en una fecha laboral
- **THEN** el sistema devuelve una lista de intervalos de inicio y fin donde tanto el profesional como al menos un sillón físico están desocupados con código HTTP 200

### Requirement: Reserva pública de turnos sin registro obligatorio
El sistema SHALL permitir la creación de un turno odontológico mediante la provisión de nombre del paciente, teléfono de contacto en formato E.164, tratamiento, profesional y horario de inicio válido, calculando la hora de fin según la duración del tratamiento.

#### Scenario: Creación exitosa de reserva pública (Happy Path)
- **WHEN** un paciente envía nombre "Carlos Sintético", teléfono "+5491144445555", tratamiento ID 1 (duración 30 min) e inicio "2026-11-15T10:00:00-03:00" en un slot libre
- **THEN** el sistema registra el turno en estado "reservado", asigna sillón disponible, calcula fin "2026-11-15T10:30:00-03:00", devuelve código HTTP 201 y genera un código único de gestión

#### Scenario: Intento de reserva en horario solapado (Error de Negocio)
- **WHEN** un paciente intenta reservar un slot donde el profesional o el sillón asignado ya tienen un turno confirmado superpuesto (violación RN-TU-03)
- **THEN** el sistema rechaza la transacción con código HTTP 409 Conflict, detalla el motivo del solape, no persiste ningún registro y retorna una lista de franjas horarias alternativas próximas

#### Scenario: Validación de contacto y límites en el borde (Caso de Borde)
- **WHEN** un paciente intenta reservar ingresando un número de teléfono con longitud insuficiente o caracteres inválidos ("1234") en el último slot del horario de atención clínica
- **THEN** el sistema rechaza la solicitud con código HTTP 422 Unprocessable Entity, reporta el error de validación en el campo teléfono y no bloquea el slot ni crea paciente huérfano
