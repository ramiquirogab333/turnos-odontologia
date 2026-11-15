# pacientes/ficha-panel Specification

## Purpose
Pantalla del panel para leer y editar la ficha clínica de un paciente (antecedentes con control de versión e historia de turnos), respetando quién puede escribir según el rol y la ventana de acceso clínico de la odontóloga.

## Requirements

### Requirement: Lectura de la ficha
La pestaña Ficha SHALL mostrar alergias, medicación, antecedentes médicos y observaciones, y la historia de turnos del paciente (fecha y hora de la clínica, estado, profesional y tratamiento), del más reciente al más antiguo, sin datos de contacto. Una ficha nunca editada SHALL mostrarse vacía con una invitación a completarla para quien puede escribir.

#### Scenario: Ficha con antecedentes (Happy Path)
- **GIVEN** "Lucía Ejemplo" con alergias "Penicilina (sintético)" y dos turnos `atendido`, uno con la Dra. Ana Ficticia y otro con el Dr. Juan Ejemplo
- **WHEN** recepción abre la pestaña Ficha
- **THEN** ve los cuatro campos y la historia con los dos turnos, en hora de la clínica aunque el navegador esté en otra zona horaria

#### Scenario: Paciente ajena (Error de Negocio)
- **GIVEN** la Dra. Ana Ficticia sin ningún `atendido` con la paciente
- **WHEN** abre la pestaña Ficha por enlace directo y el servidor responde 403 `paciente_ajeno`
- **THEN** ve el mensaje de falta de acceso y ningún antecedente

#### Scenario: Ficha nunca editada (Caso de Borde)
- **GIVEN** un paciente sin ficha (versión 0) y sin turnos
- **WHEN** recepción abre la pestaña
- **THEN** ve "Todavía no hay antecedentes cargados" con "Completar ficha", y "Sin turnos registrados" en la historia

### Requirement: Edición de antecedentes con control de versión
Recepción, admin y la odontóloga con acceso completo SHALL poder editar los cuatro antecedentes (hasta 2000 caracteres cada uno) y guardarlos con la versión leída. Si otra persona guardó antes (409 `version_desactualizada`), el panel SHALL mostrar la versión vigente sin perder lo escrito, para que la persona decida qué conservar; nunca SHALL reintentar solo ni pisar la otra versión.

#### Scenario: La odontóloga guarda la ficha (Happy Path)
- **GIVEN** la Dra. Ana Ficticia con un `atendido` de Lucía hace 3 meses y la ficha en versión 2
- **WHEN** agrega "Ibuprofeno 400 mg (sintético)" en medicación y elige "Guardar ficha"
- **THEN** ve "Ficha guardada", la versión pasa a 3 y la lectura siguiente muestra el texto nuevo

#### Scenario: Otra persona guardó antes (Error de Negocio)
- **GIVEN** recepción y la odontóloga con la ficha abierta en versión 3, y recepción ya guardó (versión 4)
- **WHEN** la odontóloga elige "Guardar ficha"
- **THEN** ve "Alguien guardó la ficha mientras la editabas", la versión 4 en los campos y su propio texto en un bloque aparte "Lo que escribiste" para copiarlo; la ficha queda en versión 4 sin cambios suyos

#### Scenario: Límite de 2000 caracteres (Caso de Borde)
- **WHEN** quien edita escribe 2000 caracteres en observaciones y luego intenta uno más
- **THEN** el campo acepta 2000, muestra "2000/2000" y no deja escribir el siguiente; se guarda sin error

### Requirement: Ficha de solo lectura con acceso vencido
Con acceso clínico de solo lectura (RN-CL-04), la ficha SHALL mostrarse sin controles de edición. Si el acceso vence mientras la ficha está abierta y el guardado responde 403 `acceso_clinico_vencido`, el panel SHALL explicarlo, conservar lo escrito para copiarlo y pasar la pestaña a solo lectura.

#### Scenario: Acceso vigente por un turno pendiente (Happy Path)
- **GIVEN** que la última atención de Lucía con la odontóloga fue hace 13 meses y tiene un turno `confirmado` con ella mañana
- **WHEN** la odontóloga abre la ficha
- **THEN** la ficha es editable

#### Scenario: Acceso vencido (Error de Negocio)
- **GIVEN** que la última atención fue hace 13 meses y no hay turno pendiente
- **WHEN** la odontóloga abre la ficha
- **THEN** ve los antecedentes sin "Editar ficha" y no puede enviar ningún cambio

#### Scenario: El acceso vence durante la edición (Caso de Borde)
- **GIVEN** la ficha abierta en edición cuando el último `atendido` cumplía exactamente 365 días
- **WHEN** la odontóloga guarda un segundo después y el servidor responde 403 `acceso_clinico_vencido`
- **THEN** ve "Tu acceso para editar venció. Para editar, pedí un turno a recepción", su texto queda en "Lo que escribiste" y la pestaña pasa a solo lectura

### Requirement: Guardado sin envíos duplicados
Mientras se guarda la ficha, el botón SHALL quedar deshabilitado con "Guardando…" y un segundo toque no SHALL enviar otro pedido. Salir de la pestaña con cambios sin guardar SHALL pedir confirmación.

#### Scenario: Doble toque (Happy Path)
- **WHEN** quien edita toca "Guardar ficha" dos veces seguidas
- **THEN** sale un solo pedido y la ficha queda en la versión siguiente

#### Scenario: Error de red al guardar (Error de Negocio)
- **GIVEN** que el guardado falla por red
- **WHEN** quien edita elige "Guardar ficha"
- **THEN** ve "No pudimos guardar la ficha. Revisá tu conexión e intentá de nuevo", lo escrito se conserva y puede reintentar con la misma versión

#### Scenario: Salir con cambios sin guardar (Caso de Borde)
- **GIVEN** cambios escritos y sin guardar en la ficha
- **WHEN** quien edita toca la pestaña Odontograma
- **THEN** ve "Tenés cambios sin guardar en la ficha" con "Seguir editando" y "Descartar cambios"; sin elegir, nada se pierde
