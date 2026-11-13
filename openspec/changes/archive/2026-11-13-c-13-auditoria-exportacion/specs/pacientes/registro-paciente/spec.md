# Spec Delta: pacientes/registro-paciente

## ADDED Requirements

### Requirement: Las lecturas de datos de pacientes quedan auditadas
Cada lectura aceptada del listado de pacientes, de la búsqueda exacta por DNI y de los datos administrativos de un paciente SHALL dejar un registro de auditoría (`lectura_listado_pacientes`, `busqueda_paciente_dni`, `lectura_paciente`) con el usuario, la IP y el instante (RN-GL-01, C-13 O2). El registro no SHALL guardar el texto buscado, el DNI ni datos del paciente; sí la página, el tamaño, los filtros booleanos y la cantidad devuelta.

#### Scenario: Listado con búsqueda auditado (Happy Path)
- **GIVEN** las pacientes "Lucía Ejemplo" (DNI 99000001) y "Mateo Prueba" (DNI 99000002)
- **WHEN** recepción lista con `q=lucia&pagina=1`
- **THEN** recibe 200 con "Lucía Ejemplo" y existe un registro `lectura_listado_pacientes` con su usuario, `pagina: 1`, `con_busqueda: true` y `devueltos: 1`, que no contiene `lucia` en ningún campo

#### Scenario: Lectura rechazada sin rastro (Error de Negocio)
- **WHEN** la odontóloga pide el listado y recibe 403, y recepción busca `dni=12ab` y recibe 422
- **THEN** no queda ningún registro de lectura

#### Scenario: Búsqueda por DNI inexistente (Caso de Borde)
- **WHEN** recepción busca `dni=99000099` (no registrado)
- **THEN** recibe 200 con lista vacía y queda un registro `busqueda_paciente_dni` con `encontrados: 0`, sin el DNI buscado y sin id de entidad

### Requirement: Sin rastro no se entregan datos del paciente
Si el registro de auditoría de una lectura de datos de pacientes no puede guardarse, la lectura SHALL responder con error y sin ningún dato del paciente.

#### Scenario: Lectura normal (Happy Path)
- **WHEN** recepción consulta los datos de la paciente 7
- **THEN** recibe 200 con sus datos y queda un registro `lectura_paciente` con entidad `paciente` e id 7

#### Scenario: Falla al guardar el registro (Error de Negocio)
- **GIVEN** que guardar el registro de auditoría falla
- **WHEN** recepción consulta los datos de la paciente 7
- **THEN** recibe un error 500 y la respuesta no contiene ningún dato de la paciente

#### Scenario: Paciente inexistente (Caso de Borde)
- **WHEN** recepción consulta la paciente 999 (no existe)
- **THEN** recibe 404 y no queda ningún registro de lectura
