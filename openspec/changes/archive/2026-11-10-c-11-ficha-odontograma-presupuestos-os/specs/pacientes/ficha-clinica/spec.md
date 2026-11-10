# Spec Delta: pacientes/ficha-clinica

## Purpose
Registra los antecedentes clínicos mínimos de cada paciente y su historia de turnos, y define quién puede leer o escribir datos de salud y cómo queda auditado cada acceso (Ley 25.326, RN-GL-01).

Las referencias `(Ox)` remiten a las decisiones de `design.md` (aprobadas el 2026-11-10). Todos los datos de ejemplo son sintéticos (R19).

## ADDED Requirements

### Requirement: Alcance de "sus pacientes" para la odontóloga
Una odontóloga SHALL acceder solo a pacientes con al menos un turno vinculado con su profesional en estado `atendido`, de cualquier fecha (O2); ningún otro estado, ni un `atendido` con otra profesional, SHALL otorgar acceso, y fuera de él SHALL responder 403 `paciente_ajeno`. Recepción y admin SHALL acceder a todos. El alcance SHALL regir ficha, odontograma, presupuestos y datos del paciente (O4). En una primera visita SHALL empezar al marcarse `atendido` el turno vinculado (RN-TU-12, O15).

#### Scenario: Paciente atendido hace dos años (Happy Path)
- **GIVEN** que "Mateo Prueba" tiene un único turno con la "Dra. Ana Ficticia", `atendido` hace dos años, y ninguno posterior
- **WHEN** la Dra. Ana Ficticia lee la ficha de Mateo
- **THEN** recibe 200 (acceso de solo lectura, O16)

#### Scenario: Solo turnos sin atender o atendido por otra profesional (Error de Negocio)
- **GIVEN** que "Mateo Prueba" tiene con la Dra. Ana Ficticia un turno `confirmado` para mañana y otro `ausente` del mes pasado, y un turno `atendido` con el "Dr. Bruno Ficticio"
- **WHEN** la Dra. Ana Ficticia lee su ficha, su odontograma o sus presupuestos
- **THEN** recibe 403 `paciente_ajeno` en los tres casos y no se devuelve ningún dato clínico

#### Scenario: Primera visita antes y después de marcar atendido (Caso de Borde)
- **GIVEN** que el único turno de "Mateo Prueba" con la Dra. Ana Ficticia es hoy, está `reservado` y vinculado con Mateo
- **WHEN** ella lee su ficha, luego ella misma marca el turno `atendido` y vuelve a leerla y a editarla
- **THEN** la primera lectura recibe 403 `paciente_ajeno`, y la segunda lectura y la edición 200

#### Scenario: Atendido sin paciente vinculado (Caso de Borde)
- **GIVEN** un turno manual de hoy de la Dra. Ana Ficticia, ya `atendido`, con solo nombre y teléfono, y el paciente "Mateo Prueba" registrado sin turnos vinculados
- **WHEN** ella lee la ficha de Mateo, recepción vincula ese turno con Mateo y ella vuelve a leerla
- **THEN** la primera lectura recibe 403 `paciente_ajeno` y la segunda 200

### Requirement: Ventana de acceso clínico de la odontóloga
Sobre sus pacientes, la odontóloga SHALL tener acceso clínico completo (lectura y escritura) mientras tenga con esa persona un turno `atendido` con inicio dentro de `VENTANA_ACCESO_CLINICO` (365 días exactos hacia atrás desde el reloj del servidor en UTC, R4) o un turno `reservado`/`confirmado` con ella con `fin` posterior a ahora. Si no, el acceso SHALL ser de solo lectura y toda escritura clínica SHALL responder 403 `acceso_clinico_vencido` sin cambios ni auditoría (O16).

#### Scenario: Atendido hace 11 meses o turno futuro tras una atención vieja (Happy Path)
- **GIVEN** que "Lucía Ejemplo" fue atendida por la Dra. Ana Ficticia hace 11 meses, y que "Mateo Prueba" fue atendido por ella hace 13 meses y tiene con ella un turno `confirmado` para la semana próxima
- **WHEN** la Dra. Ana Ficticia edita la ficha de cada uno con la `version` vigente y registra un hallazgo en el odontograma de Mateo
- **THEN** las tres escrituras se aceptan (200, 200 y 201)

#### Scenario: Atendido hace 13 meses sin turno pendiente (Error de Negocio)
- **GIVEN** que el único turno de "Mateo Prueba" con la Dra. Ana Ficticia está `atendido` hace 13 meses y no tiene ningún turno `reservado` ni `confirmado` con ella
- **WHEN** ella lee su ficha, su odontograma y sus presupuestos, y después intenta editar la ficha y registrar un hallazgo en el odontograma
- **THEN** las lecturas responden 200 con los campos de O3 y quedan auditadas; las dos escrituras responden 403 `acceso_clinico_vencido`, la ficha y el odontograma no cambian y no queda auditoría de escritura

#### Scenario: Atendido sin paciente vinculado no cuenta (Caso de Borde)
- **GIVEN** que "Lucía Ejemplo" fue atendida por la Dra. Ana Ficticia hace 13 meses, y que hoy la odontóloga marcó `atendido` un turno manual con solo nombre y teléfono, sin vincular con Lucía
- **WHEN** ella intenta editar la ficha de Lucía
- **THEN** recibe 403 `acceso_clinico_vencido`, y tras vincular recepción el turno con Lucía la misma edición responde 200

#### Scenario: Límite exacto de la ventana y turno futuro sin atención previa (Caso de Borde)
- **GIVEN** con el reloj del servidor fijo en 2026-11-10T12:00:00Z: "Lucía Ejemplo" con un único turno `atendido` con la Dra. Ana Ficticia que empezó el 2025-11-10T12:00:00Z (365 días exactos), "Mateo Prueba" con uno que empezó el 2025-11-10T11:59:59Z (365 días y 1 segundo), y "Carlos Sintético" (paciente registrado) con solo un turno `confirmado` con ella para mañana y ninguno `atendido`
- **WHEN** ella edita la ficha de cada uno
- **THEN** Lucía responde 200, Mateo 403 `acceso_clinico_vencido` y Carlos 403 `paciente_ajeno`

### Requirement: Consulta de la ficha clínica
`GET /api/panel/pacientes/{id}/ficha` SHALL devolver los antecedentes (alergias, medicación, antecedentes médicos, observaciones), su `version` y la historia de turnos vinculados (fecha, estado, profesional, tratamiento), sin datos de contacto. Si nunca se cargaron antecedentes, SHALL devolverlos vacíos con `version` 0. La historia SHALL incluir turnos de todas las profesionales (O14) y excluir pre-reservas `en_espera` vencidas.

#### Scenario: Ficha con antecedentes e historia (Happy Path)
- **GIVEN** "Lucía Ejemplo" con alergia "penicilina (dato sintético)" cargada y dos turnos vinculados, uno `atendido` y otro `reservado`
- **WHEN** recepción lee su ficha
- **THEN** recibe 200 con los antecedentes, su versión y los dos turnos ordenados del más reciente al más antiguo, sin teléfono ni email

#### Scenario: Paciente inexistente (Error de Negocio)
- **WHEN** recepción lee la ficha de un id inexistente
- **THEN** recibe 404 y no se audita ninguna lectura

#### Scenario: Paciente sin ficha cargada (Caso de Borde)
- **GIVEN** un paciente recién dado de alta, sin antecedentes ni turnos
- **WHEN** recepción lee su ficha
- **THEN** recibe 200 con antecedentes vacíos, `version` 0 e historia vacía

### Requirement: Edición de antecedentes con control de versión
`PUT /api/panel/pacientes/{id}/ficha` SHALL reemplazar los antecedentes enviando la `version` leída. Recepción y admin SHALL poder hacerlo sobre cualquier paciente, y la odontóloga solo sobre sus pacientes con acceso clínico completo (O2, O4, O16). Si la `version` no es la vigente SHALL responder 409 `version_desactualizada` sin cambiar nada (O6). La ficha SHALL guardar quién hizo la última edición (`actualizado_por`). Cada campo SHALL tener como máximo 2000 caracteres.

#### Scenario: Primera carga por recepción y corrección por la odontóloga (Happy Path)
- **GIVEN** una ficha en `version` 0 de "Lucía Ejemplo", con un turno `atendido` con la Dra. Ana Ficticia
- **WHEN** recepción envía antecedentes con `version` 0 y después la Dra. Ana Ficticia envía una corrección con `version` 1
- **THEN** ambas responden 200, la ficha queda en `version` 2 con la corrección y `actualizado_por` es el usuario de la Dra. Ana Ficticia

#### Scenario: Versión vieja o paciente ajeno (Error de Negocio)
- **GIVEN** una ficha en `version` 3 de "Mateo Prueba", que solo tiene un turno `confirmado` con la Dra. Ana Ficticia
- **WHEN** recepción envía cambios con `version` 2, o la Dra. Ana Ficticia envía cambios con `version` 3
- **THEN** recibe 409 `version_desactualizada` o 403 `paciente_ajeno` respectivamente, y la ficha sigue en `version` 3 sin cambios

#### Scenario: Límite de longitud y edición simultánea entre roles (Caso de Borde)
- **WHEN** recepción envía observaciones de exactamente 2000 caracteres y luego de 2001; y después recepción y la odontóloga de la paciente envían a la vez cambios con la misma `version`
- **THEN** la primera responde 200 y la segunda 422 sin cambiar la ficha; de los envíos simultáneos exactamente uno responde 200 y el otro 409 `version_desactualizada`, nunca 500

### Requirement: Auditoría de accesos a datos de salud
Cada lectura y cada escritura aceptada de ficha, odontograma, presupuestos o pagos de presupuesto SHALL dejar, en la misma transacción, un registro con el usuario que actuó (sea recepción, admin u odontóloga), acción, entidad e id del paciente (O5). El registro no SHALL contener contenido clínico (antecedentes, estados del odontograma, notas), nombre, DNI, número de afiliado ni teléfono (R19). Una operación rechazada no SHALL dejar registro.

#### Scenario: Lectura y escritura de la odontóloga auditadas (Happy Path)
- **WHEN** la Dra. Ana Ficticia lee la ficha de su paciente y después la edita
- **THEN** existen un registro `lectura_ficha` y otro `edicion_ficha`, ambos con su `usuario_id`, entidad `ficha` y el id del paciente

#### Scenario: Acceso denegado (Error de Negocio)
- **WHEN** una odontóloga recibe 403 `paciente_ajeno` al leer o editar una ficha
- **THEN** no queda ningún registro `lectura_ficha` ni `edicion_ficha` de ese intento

#### Scenario: Sin contenido clínico en la auditoría (Caso de Borde)
- **GIVEN** que la odontóloga de la paciente guarda la alergia "látex (dato sintético)"
- **WHEN** se inspecciona el registro `edicion_ficha`
- **THEN** contiene solo los nombres de los campos cambiados y la versión nueva, nunca "látex"
