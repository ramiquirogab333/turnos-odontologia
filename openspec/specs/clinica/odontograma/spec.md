# clinica/odontograma Specification

## Purpose
Registra el odontograma FDI básico de cada paciente como una historia que solo crece: cada hallazgo o corrección es un registro nuevo, y el estado vigente de cada pieza y cara se deriva de esa historia (US-009 CA-1).

Las referencias `(Ox)` remiten a las decisiones de `design.md` (aprobadas el 2026-11-10). Todos los datos de ejemplo son sintéticos (R19).

## Requirements

### Requirement: Piezas, caras y estados válidos
Cada registro SHALL indicar una pieza FDI válida: permanentes 11–18, 21–28, 31–38, 41–48 o temporales 51–55, 61–65, 71–75, 81–85 (O8). La cara, si se indica, SHALL ser `O`, `M`, `D`, `V` o `L`. Los estados `caries` y `obturado` SHALL exigir cara; `ausente`, `extraccion_indicada`, `corona`, `endodoncia` e `implante` SHALL rechazarla; `sano` SHALL aceptar ambas formas. Cualquier otro valor SHALL responder 422.

#### Scenario: Registro de caries en una cara (Happy Path)
- **WHEN** recepción registra en la pieza 16 la cara `O` con estado `caries`
- **THEN** recibe 201 y el registro queda guardado

#### Scenario: Pieza inexistente o combinación inválida (Error de Negocio)
- **WHEN** recepción registra la pieza 19, o la pieza 16 con estado `caries` sin cara, o la pieza 16 cara `O` con estado `corona`
- **THEN** recibe 422 y no se guarda ningún registro

#### Scenario: Límites de dentición temporal (Caso de Borde)
- **WHEN** recepción registra la pieza 55 y luego la pieza 56
- **THEN** la 55 se acepta y la 56 responde 422

### Requirement: Registro en lote solo de alta
`POST /api/panel/pacientes/{id}/odontograma` SHALL aceptar entre 1 y 64 registros y guardarlos todos o ninguno, con el usuario que registró (`registrado_por`) y la fecha de registro (O7). Ningún registro SHALL modificarse ni borrarse por la API, tampoco por la odontóloga; una corrección SHALL ser un registro nuevo. Recepción y admin SHALL registrar sobre cualquier paciente, y la odontóloga solo sobre sus pacientes con acceso clínico completo (O2, O4, O16).

#### Scenario: Lote de tres hallazgos cargado por la odontóloga (Happy Path)
- **GIVEN** "Lucía Ejemplo" con un turno `atendido` con la "Dra. Ana Ficticia"
- **WHEN** la Dra. Ana Ficticia envía caries en 16-O, `ausente` en 36 y `obturado` en 46-M
- **THEN** recibe 201 con los tres registros, cada uno con `registrado_por` igual a su usuario, y queda un registro de auditoría `registro_odontograma` con su `usuario_id` y la cantidad, sin los estados

#### Scenario: Un registro inválido en el lote o paciente ajeno (Error de Negocio)
- **WHEN** recepción envía un lote con dos registros válidos y uno con la pieza 99, o la Dra. Ana Ficticia envía un lote válido sobre "Mateo Prueba", cuyo único turno con ella está `confirmado`
- **THEN** recibe 422 o 403 `paciente_ajeno` respectivamente, no se guarda ninguno de los registros y no queda auditoría

#### Scenario: Tamaño del lote en el límite (Caso de Borde)
- **WHEN** recepción envía un lote de 64 registros y luego otro de 65, y después uno vacío
- **THEN** el de 64 responde 201 y los otros dos 422

### Requirement: Estado vigente del odontograma
`GET /api/panel/pacientes/{id}/odontograma` SHALL devolver, por pieza, el último estado de pieza y el último estado de cada cara. Un registro `sano` sin cara SHALL dejar sin hallazgos vigentes a la pieza y a todas sus caras registradas antes; uno `sano` con cara SHALL limpiar solo esa cara. Ante igual fecha SHALL ganar el registro de mayor id.

#### Scenario: Caries luego obturada (Happy Path)
- **GIVEN** la pieza 16 con caries en la cara `O` registrada el lunes y `obturado` en la misma cara el martes
- **WHEN** la odontóloga de la paciente consulta el odontograma
- **THEN** la pieza 16 muestra la cara `O` como `obturado` y ningún otro hallazgo

#### Scenario: Paciente ajeno (Error de Negocio)
- **WHEN** una odontóloga consulta el odontograma de un paciente que no es suyo
- **THEN** recibe 403 `paciente_ajeno`

#### Scenario: Pieza vuelta a sana (Caso de Borde)
- **GIVEN** la pieza 26 con `endodoncia` y caries en la cara `M`, y después un registro `sano` sin cara para la 26
- **WHEN** recepción consulta el odontograma
- **THEN** la pieza 26 no muestra hallazgos vigentes, y el historial conserva los tres registros

### Requirement: Historial del odontograma
`GET /api/panel/pacientes/{id}/odontograma/historial` SHALL devolver todos los registros del paciente del más reciente al más antiguo, paginados (máximo 200 por página), con pieza, cara, estado, nota, fecha y el usuario que registró. La lectura SHALL respetar el alcance de "sus pacientes" y quedar auditada.

#### Scenario: Historial completo (Happy Path)
- **GIVEN** cinco registros de la paciente
- **WHEN** recepción pide el historial
- **THEN** recibe los cinco, del más reciente al más antiguo, y queda un registro `lectura_odontograma`

#### Scenario: Página fuera de rango (Error de Negocio)
- **WHEN** recepción pide `limite=500`
- **THEN** recibe 422

#### Scenario: Paciente sin registros (Caso de Borde)
- **WHEN** recepción pide el historial de un paciente sin odontograma
- **THEN** recibe 200 con lista vacía
