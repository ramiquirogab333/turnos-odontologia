# Spec Delta

## ADDED Requirements

### Requirement: Cada turno informa su paciente vinculado
Cada turno de `GET /api/panel/agenda` SHALL traer `paciente_id` con el id del `Paciente` vinculado, o `null` si no tiene vínculo, para todos los roles del panel. El campo no SHALL agregar ningún otro dato del paciente: el nombre sigue siendo el de contacto del turno y el teléfono sigue las reglas de "Datos de contacto según el rol". Un cambio de vínculo SHALL verse en la consulta siguiente.

#### Scenario: Turno vinculado (Happy Path)
- **GIVEN** un turno `reservado` de la Dra. Ana Ficticia vinculado con la paciente 7 ("Lucía Ejemplo")
- **WHEN** recepción y la odontóloga consultan la agenda de ese día
- **THEN** las dos respuestas traen el turno con `paciente_id: 7`, y la de la odontóloga sigue sin `paciente_telefono`

#### Scenario: El campo no expone datos de otros profesionales (Error de Negocio)
- **GIVEN** un turno del Dr. Juan Ejemplo vinculado con la paciente 7
- **WHEN** la Dra. Ana Ficticia consulta su agenda
- **THEN** ese turno no aparece y la respuesta no contiene `paciente_id: 7` en ningún turno ajeno (el aislamiento por rol no cambia)

#### Scenario: Turno sin vínculo y vínculo corregido (Caso de Borde)
- **GIVEN** un turno manual con contacto "Carlos Sintético" sin paciente
- **WHEN** recepción consulta la agenda, vincula el turno con la paciente 8 y vuelve a consultar
- **THEN** la primera respuesta trae `paciente_id: null` y la segunda `paciente_id: 8`, con el mismo `paciente_nombre` de contacto
