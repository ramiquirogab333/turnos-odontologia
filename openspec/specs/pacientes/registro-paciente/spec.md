# pacientes/registro-paciente Specification

## Purpose
Permite que recepción y admin den de alta, consulten y editen pacientes desde el panel y vinculen cada turno (web o manual) con su `Paciente`, para que la ficha clínica, el odontograma y los presupuestos tengan a quién pertenecer.

Las referencias `(Ox)` remiten a las decisiones de `design.md` (aprobadas el 2026-11-10). Todos los datos de ejemplo son sintéticos (R19).

## Requirements

### Requirement: Alta de paciente desde el panel
`POST /api/panel/pacientes` SHALL crear un paciente con nombre, apellido, DNI (7 u 8 dígitos), teléfono E.164 y, opcionalmente, email, obra social activa y número de afiliado. Solo recepción y admin SHALL poder hacerlo (O1). Un DNI ya registrado SHALL responder 409 `dni_duplicado` sin crear nada. El alta SHALL quedar auditada sin datos personales (RN-GL-01, R19).

#### Scenario: Alta con datos válidos (Happy Path)
- **GIVEN** recepción autenticada y la obra social "Swiss Medical" activa
- **WHEN** envía nombre "Lucía", apellido "Ejemplo", DNI "99000001", teléfono "+5491100000001" y esa obra social
- **THEN** recibe 201 con el id del paciente, y existe un registro de auditoría `alta_paciente` con su usuario y el id, sin nombre, DNI ni teléfono

#### Scenario: DNI repetido o rol sin permiso (Error de Negocio)
- **GIVEN** un paciente con DNI "99000001"
- **WHEN** recepción intenta otra alta con ese DNI, o una odontóloga intenta cualquier alta
- **THEN** recibe 409 `dni_duplicado` o 403 respectivamente, y no se crea ningún paciente ni registro de auditoría

#### Scenario: DNI de 7 dígitos y obra social inactiva (Caso de Borde)
- **WHEN** recepción envía el DNI "9900001" (7 dígitos) con una obra social activa, y luego otra alta con una obra social inactiva
- **THEN** la primera responde 201 y la segunda 422 `obra_social_inactiva`

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

### Requirement: Consulta y edición de datos administrativos del paciente
`GET /api/panel/pacientes/{id}` SHALL devolver los datos del paciente; `PUT` SHALL editarlos y solo recepción y admin SHALL poder hacerlo (O4). La odontóloga SHALL consultar solo a sus pacientes (O2) con un esquema de salida propio: nombre, apellido, DNI, obra social y número de afiliado, nunca teléfono ni email (O3, R15).

#### Scenario: Recepción edita el teléfono (Happy Path)
- **WHEN** recepción cambia el teléfono de "Lucía Ejemplo" a "+5491100000002"
- **THEN** recibe 200 con el dato nuevo y queda auditoría `edicion_paciente` con los nombres de los campos cambiados, sin sus valores

#### Scenario: Odontóloga intenta editar o leer a un paciente ajeno (Error de Negocio)
- **GIVEN** una odontóloga cuyo único turno con "Lucía Ejemplo" está `confirmado` (nunca `atendido`)
- **WHEN** hace `GET /api/panel/pacientes/{id}` sobre ella, o hace `PUT /api/panel/pacientes/{id}` sobre cualquier paciente, incluida una propia
- **THEN** recibe 403 (`paciente_ajeno` en la lectura) y el paciente no cambia

#### Scenario: Odontóloga lee a su paciente (Caso de Borde)
- **GIVEN** un turno `atendido` de "Lucía Ejemplo" (DNI "99000001", afiliado "SM-SINT-0001") con esa odontóloga
- **WHEN** la odontóloga consulta a la paciente
- **THEN** recibe 200 con nombre, apellido, DNI "99000001", obra social y número de afiliado "SM-SINT-0001", y las claves `telefono` y `email` no existen en la respuesta

### Requirement: Vínculo de un turno con su paciente
`PUT /api/panel/turnos/{turno_id}/paciente` SHALL asociar un turno existente a un paciente existente, o reemplazar el vínculo anterior, sin alterar estado, horario, seña ni contacto del turno (O1). Solo recepción y admin SHALL poder hacerlo. El cambio SHALL quedar auditado con el id anterior y el nuevo.

#### Scenario: Vincular un turno manual (Happy Path)
- **GIVEN** un turno manual de "Lucía Ejemplo" sin paciente y la paciente registrada
- **WHEN** recepción lo vincula con ella
- **THEN** recibe 200, el turno queda con ese `paciente_id`, su estado y su contacto no cambian, y queda auditoría `vinculo_turno_paciente`

#### Scenario: Turno o paciente inexistentes, o rol sin permiso (Error de Negocio)
- **WHEN** recepción vincula un turno inexistente o con un paciente inexistente, o una odontóloga intenta vincular
- **THEN** recibe 404 o 403 respectivamente y ningún turno cambia

#### Scenario: Corregir un vínculo equivocado (Caso de Borde)
- **GIVEN** un turno vinculado por error con "Mateo Prueba"
- **WHEN** recepción lo vincula con "Lucía Ejemplo"
- **THEN** el turno queda con la paciente correcta, la auditoría registra ambos ids, y la historia de turnos de "Mateo Prueba" ya no lo muestra

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
