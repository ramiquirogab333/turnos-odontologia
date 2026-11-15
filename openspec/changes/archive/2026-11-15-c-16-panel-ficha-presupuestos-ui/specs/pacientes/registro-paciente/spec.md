# Spec Delta

## ADDED Requirements

### Requirement: La consulta del paciente informa el acceso clínico
`GET /api/panel/pacientes/{id}` SHALL traer `acceso_clinico` con `nivel` (`total`, `clinico_completo` o `clinico_lectura`) y `puede_escribir` (si quien consulta puede escribir ficha y odontograma), calculados con las mismas reglas que deciden las escrituras (RN-CL-02, RN-CL-04). Valen para las dos vistas (completa y clínica); el campo no SHALL decir por qué venció el acceso ni fechas de turnos.

#### Scenario: Recepción y odontóloga con acceso completo (Happy Path)
- **GIVEN** la paciente 7 con un `atendido` con la Dra. Ana Ficticia hace 2 meses
- **WHEN** recepción y la odontóloga consultan la paciente 7
- **THEN** recepción recibe `acceso_clinico: {nivel: "total", puede_escribir: true}` y la odontóloga `{nivel: "clinico_completo", puede_escribir: true}`, sin teléfono ni email

#### Scenario: Paciente ajena (Error de Negocio)
- **GIVEN** la odontóloga sin `atendido` con la paciente 7
- **WHEN** la consulta
- **THEN** recibe 403 `paciente_ajeno` sin `acceso_clinico` ni ningún otro dato, y no queda registro de lectura

#### Scenario: Límite de la ventana (Caso de Borde)
- **GIVEN** que el único `atendido` con la odontóloga empezó hace exactamente 365 días, y otro paciente cuyo único `atendido` empezó hace 365 días y 1 segundo, ambos sin turno pendiente
- **WHEN** la odontóloga consulta a cada uno
- **THEN** el primero trae `{nivel: "clinico_completo", puede_escribir: true}` y el segundo `{nivel: "clinico_lectura", puede_escribir: false}`, y un `PUT …/ficha` sobre el segundo responde 403 `acceso_clinico_vencido`

### Requirement: Obras sociales activas para el panel
`GET /api/panel/obras-sociales` SHALL devolver a recepción y admin las obras sociales activas (id y nombre) ordenadas por nombre, para elegirlas en el alta, la edición del paciente y el presupuesto. La odontóloga SHALL recibir 403. La ruta SHALL figurar en la política de auditoría como exenta con motivo (catálogo sin datos de pacientes).

#### Scenario: Recepción lista las obras sociales (Happy Path)
- **GIVEN** el seed con obras sociales activas y una desactivada
- **WHEN** recepción pide `GET /api/panel/obras-sociales`
- **THEN** recibe 200 con las activas ordenadas por nombre, cada una con `id` y `nombre` solamente, y sin la desactivada

#### Scenario: La odontóloga pide la lista (Error de Negocio)
- **WHEN** `dra.ficticia@turnos.test` (solo `odontologo`) pide la lista
- **THEN** recibe 403 y sin token recibe 401

#### Scenario: Ninguna obra social activa (Caso de Borde)
- **GIVEN** todas las obras sociales desactivadas
- **WHEN** recepción pide la lista
- **THEN** recibe 200 con una lista vacía, y el alta de paciente sigue ofreciendo "Sin obra social"
