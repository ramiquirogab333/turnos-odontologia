# Spec Delta: auth/panel-login

## Purpose
Actualiza la definición del rol `odontologo` en el requisito de RBAC de C-03 para que coincida con las decisiones de C-11: marca `atendido` sus propios turnos (O15) y tiene acceso clínico a sus pacientes, completo dentro de la ventana de 12 meses y de solo lectura fuera de ella (O2–O4, O16).

Las referencias `(Ox)` remiten a las decisiones de C-11 (`design.md`). Todos los datos de ejemplo son sintéticos (R19).

## MODIFIED Requirements

### Requirement: RBAC authorization
El sistema SHALL autorizar operaciones de panel mediante `PermissionContext.require_role()` según la matriz de `03_actores_y_roles.md` (actualizada por C-11). `recepcion` / `admin` = CRUD total. `odontologo` = lectura de su agenda y de sus pacientes, y solo las escrituras del escenario «Alcance del rol odontologo»; nunca escribe datos administrativos, vínculos, presupuestos ni pagos.

#### Scenario: La odontóloga ejerce sus permisos (Happy Path)
- **GIVEN** un usuario `odontologo` asociado a la "Dra. Ana Ficticia", un turno suyo `reservado` de hoy y la paciente "Lucía Ejemplo" atendida por ella hace dos meses
- **WHEN** marca atendido ese turno y edita la ficha de Lucía con la `version` vigente
- **THEN** recibe 200 en ambas operaciones

#### Scenario: require_role('recepcion') permite CRUD; odontólogo denegado en pacientes ajenos (Caso de Borde / Matriz RBAC)
- **GIVEN** que el usuario autenticado tiene rol `recepcion` y otro usuario tiene rol `odontologo`
- **WHEN** `recepcion` ejecuta `POST /api/panel/pacientes` (crear paciente) y `odontologo` ejecuta `PUT /api/panel/pacientes/{id_ajeno}` (editar paciente ajeno)
- **THEN** `recepcion` recibe 201 (CRUD permitido) y `odontologo` recibe 403 (denegado: solo lectura de sus pacientes)

#### Scenario: La odontóloga intenta una escritura administrativa (Error de Negocio)
- **GIVEN** el mismo usuario `odontologo` y su paciente "Lucía Ejemplo"
- **WHEN** intenta cancelar un turno propio, crear un presupuesto para Lucía o registrarle un pago
- **THEN** recibe 403 en los tres casos y no cambia nada

#### Scenario: Alcance del rol odontologo (Matriz RBAC)
- **GIVEN** un usuario `odontologo` asociado a una profesional y una paciente suya (al menos un turno `atendido` con esa profesional, O2)
- **WHEN** se evalúan sus permisos
- **THEN** puede leer su agenda, marcar `atendido` los turnos de su profesional (O15), leer los datos administrativos de sus pacientes sin teléfono ni email, y leer ficha, odontograma y presupuestos
- **AND** solo puede escribir ficha y odontograma con acceso clínico vigente (O3, O4, O16), y nunca datos administrativos, vínculos, presupuestos ni pagos
