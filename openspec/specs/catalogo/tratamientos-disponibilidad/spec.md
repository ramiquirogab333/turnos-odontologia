# catalogo/tratamientos-disponibilidad Specification

## Purpose
Añade CRUD admin para los catálogos `Tratamiento`, `Profesional`, `Sillon` y `Disponibilidad` bajo `/api/admin/`, protegidos por RBAC de C-03, con esquemas Pydantic de entrada/salida (R15), servicios async sobre `BaseRepository[T]` + `UnitOfWork` (R13, R16), migración Alembic 004 reversible con constraints de catálogo (R4, R6, R14) y auditoría en `RegistroAuditoria` (RN-GL-01). No modifica capacidades de C-01/C-02/C-03; los datos son 100% sintéticos (R19).

## Requirements

### Requirement: CRUD admin de Tratamiento
El sistema SHALL permitir a rol `recepcion`/`admin` crear, leer, actualizar y eliminar tratamientos (nombre, `duracion_minutos`, `precio_base`), denegando a otros roles con 403 y rechazando `duracion_minutos <= 0` con 422 (CHECK).

#### Scenario: POST /api/admin/tratamientos con rol recepción → 201 creado (Happy Path)
- **GIVEN** que existe un usuario autenticado con rol `recepcion`
- **WHEN** se envía `POST /api/admin/tratamientos` con body sintético `{ "nombre": "Limpieza Dental", "duracion_minutos": 30, "precio_base": "5000.00" }`
- **THEN** el sistema responde 201 con el tratamiento creado (id, nombre, duracion_minutos=30, precio_base="5000.00") y registra la acción en `RegistroAuditoria` (RN-GL-01)

#### Scenario: duracion_minutos <= 0 → 422 CHECK constraint (Error de Negocio)
- **GIVEN** que existe un usuario autenticado con rol `recepcion`
- **WHEN** se envía `POST /api/admin/tratamientos` con `duracion_minutos` = 0 (o negativo)
- **THEN** el sistema responde 422 por violación del `CHECK duracion_minutos > 0` y no crea el tratamiento

#### Scenario: rol odontólogo intenta POST /api/admin/tratamientos → 403 (Caso de Borde / RBAC)
- **GIVEN** que existe un usuario autenticado con rol `odontologo`
- **WHEN** se envía `POST /api/admin/tratamientos` con body válido
- **THEN** el sistema responde 403 (RBAC denegado: solo recepcion/admin pueden escribir catálogo)

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
