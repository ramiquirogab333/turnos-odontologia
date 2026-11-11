# Spec Delta: pacientes/registro-paciente

## MODIFIED Requirements

### Requirement: Búsqueda exacta de paciente por DNI
`GET /api/panel/pacientes?dni=<dni>` SHALL devolver la lista (cero o un elemento) de pacientes con ese DNI exacto, para evitar duplicados antes de un alta. Solo recepción y admin SHALL poder buscar (O1). La búsqueda libre por nombre SHALL hacerse con el listado de pacientes (`GET /api/panel/pacientes/listado`, C-12 O13).

#### Scenario: DNI existente (Happy Path)
- **GIVEN** un paciente con DNI "99000001"
- **WHEN** recepción busca `dni=99000001`
- **THEN** recibe 200 con una lista de un elemento con ese paciente

#### Scenario: Odontóloga busca por DNI (Error de Negocio)
- **WHEN** una odontóloga busca `dni=99000001`
- **THEN** recibe 403 y no se devuelve ningún dato

#### Scenario: DNI inexistente o mal formado (Caso de Borde)
- **WHEN** recepción busca `dni=99000099` (no registrado) y luego `dni=12ab`
- **THEN** la primera responde 200 con lista vacía y la segunda 422

## ADDED Requirements

### Requirement: Listado de pacientes con búsqueda libre
`GET /api/panel/pacientes/listado` SHALL devolver los pacientes por páginas (`pagina` desde 1, `por_pagina` de 1 a 50, 20 por defecto) con el total, ordenados por apellido y nombre. `q` opcional, de 2 a 60 caracteres, SHALL filtrar por nombre, apellido o comienzo del DNI, sin distinguir mayúsculas ni acentos (C-12 O13). Solo recepción y admin SHALL poder listar.

#### Scenario: Búsqueda por nombre sin acento (Happy Path)
- **GIVEN** las pacientes "Lucía Ejemplo" (DNI "99000001") y "Mateo Prueba" (DNI "99000002")
- **WHEN** recepción lista con `q=lucia`
- **THEN** recibe 200 con total 1 y a "Lucía Ejemplo" con su id, nombre, apellido, DNI, teléfono y obra social

#### Scenario: Odontóloga lista, o búsqueda demasiado corta (Error de Negocio)
- **WHEN** un usuario con solo el rol `odontologo` pide el listado, y luego recepción envía `q=l`
- **THEN** recibe 403 y 422 respectivamente, sin ningún dato de pacientes

#### Scenario: Comienzo del DNI, apellido y nombre, y página fuera de rango (Caso de Borde)
- **GIVEN** esas dos pacientes
- **WHEN** recepción lista con `q=9900000`, luego con `q=ejemplo lu` y luego con `pagina=5`
- **THEN** la primera trae a las dos, la segunda solo a "Lucía Ejemplo" y la tercera una lista vacía con total 2

### Requirement: Ausentismo por paciente en el listado
Cada paciente del listado SHALL traer la cantidad de turnos `atendido` y `ausente` vinculados con esa persona y la fecha de su último turno. `con_ausencias=true` SHALL dejar solo a quienes tienen al menos un `ausente`, y `orden=ausencias` SHALL ordenar de más a menos ausencias. Un turno sin paciente vinculado no SHALL contar para nadie.

#### Scenario: Paciente con una ausencia (Happy Path)
- **GIVEN** "Mateo Prueba" con dos turnos vinculados `atendido` y uno `ausente`
- **WHEN** recepción lista con `con_ausencias=true`
- **THEN** recibe a "Mateo Prueba" con 2 atendidos, 1 ausente y la fecha de su último turno

#### Scenario: Valor de orden inválido (Error de Negocio)
- **WHEN** recepción lista con `orden=telefono`
- **THEN** recibe 422

#### Scenario: Turno ausente sin vincular y pre-reservas (Caso de Borde)
- **GIVEN** "Lucía Ejemplo" con un turno vinculado `en_espera` y otro `cancelado`, y un turno `ausente` a su nombre que nadie vinculó
- **WHEN** recepción lista sin filtros
- **THEN** "Lucía Ejemplo" figura con 0 atendidos y 0 ausentes, y no aparece al filtrar `con_ausencias=true`

### Requirement: Pantalla de pacientes
El panel SHALL ofrecer a recepción y admin una pantalla de pacientes con un buscador, la lista con las ausencias de cada persona, el filtro «Con ausencias» y la paginación. La búsqueda SHALL esperar a que la persona deje de escribir antes de consultar. SHALL funcionar a 360 px sin desplazamiento horizontal (R3).

#### Scenario: Búsqueda a 360 px (Happy Path)
- **GIVEN** recepción en un viewport de 360 px
- **WHEN** abre Pacientes y escribe "lucia"
- **THEN** ve a "Lucía Ejemplo" con su DNI y sus ausencias, sin desplazamiento horizontal

#### Scenario: La odontóloga no tiene la sección (Error de Negocio)
- **WHEN** la Dra. Ana Ficticia inicia sesión con solo el rol `odontologo`
- **THEN** no ve la sección Pacientes ni las de Indicadores y Caja, solo la Agenda

#### Scenario: Sin resultados (Caso de Borde)
- **WHEN** recepción busca "zzz"
- **THEN** ve "No encontramos pacientes con «zzz»" y la sugerencia de buscar por DNI
