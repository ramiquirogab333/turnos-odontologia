# Spec Delta

## MODIFIED Requirements

### Requirement: Catálogo público de tratamientos
El sistema SHALL exponer sin autenticación un listado de solo lectura de los tratamientos reservables, con identificador, nombre, duración en minutos y precio base orientativo, ordenado por nombre, para que el paciente elija el tratamiento antes de consultar disponibilidad. Un tratamiento inactivo (C-14) SHALL no figurar en el listado.

#### Scenario: Listado de tratamientos sin autenticación
- **WHEN** un paciente sin sesión solicita `GET /api/public/tratamientos` y existe el tratamiento "Limpieza" de 30 minutos con precio base 1000.00
- **THEN** el sistema responde HTTP 200 con una lista que incluye `id`, `nombre`, `duracion_minutos` y `precio_base` ("1000.00") de ese tratamiento, sin exigir cabecera de autorización

#### Scenario: Catálogo de tratamientos vacío (Caso de Borde)
- **WHEN** un paciente solicita `GET /api/public/tratamientos` y no hay tratamientos cargados
- **THEN** el sistema responde HTTP 200 con una lista vacía, sin error

#### Scenario: Un tratamiento inactivo no se lista (Error de Negocio)
- **GIVEN** "Limpieza" activo y "Ortodoncia demo" inactivo
- **WHEN** un paciente solicita `GET /api/public/tratamientos`
- **THEN** la lista incluye "Limpieza" y no incluye "Ortodoncia demo", sin exponer el campo `activo`

### Requirement: Catálogo público de profesionales con agenda vigente
El sistema SHALL exponer sin autenticación un listado de solo lectura de los profesionales activos (C-14) que tengan al menos una franja de disponibilidad activa (RN-TU-07), con identificador, nombre y especialidad, sin exponer la matrícula, ordenado por nombre. El paciente SHALL poder elegir el profesional en el paso 1 del flujo de reserva, porque la disponibilidad se consulta por profesional.

#### Scenario: Solo aparecen profesionales con franja vigente
- **WHEN** un paciente solicita `GET /api/public/profesionales` y existen un profesional con una franja activa y otro sin franjas activas
- **THEN** el sistema responde HTTP 200 solo con el profesional que tiene franja activa, con `id`, `nombre` y `especialidad`, y sin el campo de matrícula

#### Scenario: Profesional con varias franjas aparece una sola vez (Caso de Borde)
- **WHEN** un profesional tiene dos franjas activas en distintos días y un paciente solicita `GET /api/public/profesionales`
- **THEN** el sistema devuelve a ese profesional una sola vez en la lista

#### Scenario: Un profesional inactivo no aparece aunque tenga franjas (Error de Negocio)
- **GIVEN** "Dr. Juan Ejemplo" inactivo con una franja activa
- **WHEN** un paciente solicita `GET /api/public/profesionales`
- **THEN** "Dr. Juan Ejemplo" no figura en la lista

## ADDED Requirements

### Requirement: Lo inactivo no ofrece horarios ni se reserva
La consulta pública de disponibilidad y la reserva pública SHALL responder 422 con `motivo: "no_reservable"` y el campo (`tratamiento_id` o `profesional_id`) cuando el tratamiento o el profesional están inactivos, sin crear nada. Un sillón que no está `activo` SHALL no asignarse a turnos nuevos. Reactivar el ítem SHALL volver a ofrecer sus horarios sin otro paso (US-008 CA-2).

#### Scenario: Reservable de nuevo tras reactivar (Happy Path)
- **GIVEN** "Limpieza" inactivo y luego reactivado por recepción
- **WHEN** un paciente consulta la disponibilidad de "Dra. Ana Ficticia" para "Limpieza" en un día con franja activa
- **THEN** responde 200 con horarios libres

#### Scenario: Reserva con un tratamiento desactivado mientras el paciente elegía (Error de Negocio)
- **GIVEN** que "Limpieza" se desactivó después de que el paciente cargó la lista
- **WHEN** el paciente envía `POST /api/public/turnos` con ese tratamiento
- **THEN** responde 422 `no_reservable` con campo `tratamiento_id`, no se crea turno ni pago y la pantalla le pide elegir otro tratamiento

#### Scenario: Único sillón disponible en mantenimiento (Caso de Borde)
- **GIVEN** que el único sillón `activo` pasó a `mantenimiento`
- **WHEN** un paciente consulta la disponibilidad de cualquier profesional
- **THEN** responde 200 con una lista vacía de horarios, sin error
