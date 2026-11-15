# Spec Delta

## Purpose

Pantallas del panel para abrir el detalle de un paciente según el rol, dar de alta y editar sus datos administrativos y vincular cada turno con su paciente desde la agenda, de modo que la ficha, el ausentismo y el acceso clínico de la odontóloga funcionen sin usar la API a mano.

## ADDED Requirements

### Requirement: Detalle del paciente por ruta según el rol
El panel SHALL ofrecer el detalle de un paciente en `#/pacientes/{id}` con las pestañas Ficha, Odontograma y Presupuestos, más Datos solo para recepción y admin; la pestaña sale de `?pestana=` y un valor inválido abre Ficha. Recepción y admin SHALL poder abrir cualquier paciente; la odontóloga SHALL poder abrir solo a sus pacientes (RN-CL-02) aunque no tenga la sección Pacientes en la navegación.

#### Scenario: Recepción abre el detalle desde el listado (Happy Path)
- **GIVEN** `recepcion@turnos.test` con sesión iniciada y la paciente sintética "Lucía Ejemplo" (DNI 99000001)
- **WHEN** toca su fila en la sección Pacientes
- **THEN** la URL pasa a `#/pacientes/{id}`, ve la cabecera con su nombre y las pestañas Ficha, Odontograma, Presupuestos y Datos, con Ficha abierta

#### Scenario: La odontóloga abre una paciente ajena (Error de Negocio)
- **GIVEN** `dra.ficticia@turnos.test` (solo `odontologo`) sin ningún turno `atendido` con "Lucía Ejemplo"
- **WHEN** abre `#/pacientes/{id}` de Lucía
- **THEN** ve "No tenés acceso a esta paciente: el acceso empieza cuando un turno con vos se marca atendido" y ningún dato de la paciente, con un enlace para volver a la agenda

#### Scenario: Pestaña o paciente inválidos en el hash (Caso de Borde)
- **WHEN** recepción abre `#/pacientes/{id}?pestana=radiografias` y luego `#/pacientes/999999` (inexistente)
- **THEN** en el primer caso se abre la pestaña Ficha sin error; en el segundo ve "No encontramos ese paciente" con el enlace a Pacientes, sin pantalla en blanco

### Requirement: Cabecera del paciente según el rol
La cabecera del detalle SHALL mostrar nombre, apellido, DNI, obra social y número de afiliado; teléfono y email SHALL mostrarse solo a recepción y admin (O3 de C-11). Si el acceso clínico de la odontóloga es de solo lectura (RN-CL-04), la cabecera SHALL decirlo y explicar cómo recuperar la escritura.

#### Scenario: Cabecera completa para recepción (Happy Path)
- **GIVEN** "Lucía Ejemplo", DNI 99000001, Swiss Medical, afiliado "SM-0001", teléfono `+5491100000001`
- **WHEN** recepción abre su detalle
- **THEN** la cabecera muestra los cinco datos y el teléfono

#### Scenario: La odontóloga no ve contacto (Error de Negocio)
- **GIVEN** la Dra. Ana Ficticia con un turno `atendido` de Lucía hace 2 meses
- **WHEN** abre el detalle
- **THEN** la cabecera muestra nombre, DNI, obra social y afiliado y no muestra teléfono ni email en ningún lugar de la página

#### Scenario: Acceso de solo lectura (Caso de Borde)
- **GIVEN** que la única atención de Lucía con la Dra. Ana Ficticia fue hace 366 días y no hay turno pendiente
- **WHEN** la odontóloga abre el detalle
- **THEN** la cabecera dice "Solo lectura: tu última atención con esta paciente fue hace más de 12 meses. Para editar, pedí un turno a recepción" y no aparece ningún botón de edición en Ficha ni en Odontograma

### Requirement: Carga del detalle sin cascadas
Al abrir el detalle, el panel SHALL pedir los datos del paciente y los de la pestaña activa al mismo tiempo (R2), y las demás pestañas SHALL cargarse recién al abrirlas. Si una carga falla, SHALL mostrar qué no se pudo cargar con "Reintentar", sin mostrar la sección vacía como si no hubiera datos.

#### Scenario: Pedidos en paralelo (Happy Path)
- **GIVEN** recepción con sesión iniciada
- **WHEN** abre `#/pacientes/{id}?pestana=odontograma`
- **THEN** los pedidos del paciente y del odontograma vigente salen antes de que termine el primero, y no se pide la ficha ni los presupuestos

#### Scenario: Falla la carga de la pestaña (Error de Negocio)
- **GIVEN** que `GET …/presupuestos` responde 500
- **WHEN** recepción abre la pestaña Presupuestos
- **THEN** la cabecera sigue visible y la pestaña dice "No pudimos cargar los presupuestos" con "Reintentar", sin el texto de lista vacía

#### Scenario: Volver a una pestaña ya abierta (Caso de Borde)
- **GIVEN** recepción que abrió Ficha y después Odontograma
- **WHEN** vuelve a Ficha sin haber guardado nada
- **THEN** ve la ficha que ya tenía cargada sin un pedido nuevo, y con "Actualizar" puede pedirla otra vez

### Requirement: Alta de paciente desde el panel
La sección Pacientes SHALL ofrecer a recepción y admin "Nuevo paciente" con nombre, apellido, DNI (7 u 8 dígitos), teléfono (E.164), email opcional, obra social activa o "Sin obra social" y número de afiliado opcional. Al guardar SHALL abrir el detalle del paciente creado. Un DNI ya registrado SHALL informarse con un enlace al paciente existente.

#### Scenario: Alta correcta (Happy Path)
- **GIVEN** recepción en Pacientes
- **WHEN** carga "Mateo", "Prueba", DNI 99000002, teléfono `+5491100000002`, "Sin obra social" y elige "Guardar paciente"
- **THEN** se crea el paciente, se abre su detalle y el listado lo muestra al volver

#### Scenario: DNI ya registrado (Error de Negocio)
- **GIVEN** "Lucía Ejemplo" con DNI 99000001
- **WHEN** recepción intenta dar de alta otra persona con DNI 99000001
- **THEN** ve "Ya hay un paciente con ese DNI" con el enlace "Ver a Lucía Ejemplo", no se crea nada y lo escrito se conserva

#### Scenario: Datos con formato inválido (Caso de Borde)
- **WHEN** recepción escribe DNI "9900001a" y teléfono "1100000002" y elige "Guardar paciente"
- **THEN** ve un error junto a cada campo ("El DNI tiene 7 u 8 números, sin puntos"; "Escribí el teléfono con código de país, por ejemplo +5491100000002") sin enviar el pedido

### Requirement: Edición de datos administrativos
La pestaña Datos SHALL permitir a recepción y admin editar los datos administrativos del paciente con el mismo formulario del alta, precargado. La odontóloga no SHALL ver la pestaña ni ningún control de edición de esos datos.

#### Scenario: Cambio de obra social (Happy Path)
- **GIVEN** "Lucía Ejemplo" sin obra social
- **WHEN** recepción elige "Swiss Medical", afiliado "SM-0001" y "Guardar cambios"
- **THEN** la cabecera muestra "Swiss Medical · SM-0001" y aparece "Cambios guardados"

#### Scenario: Obra social desactivada mientras se edita (Error de Negocio)
- **GIVEN** que la obra social elegida se desactivó después de abrir el formulario
- **WHEN** recepción guarda
- **THEN** ve "Esa obra social ya no está activa. Elegí otra o «Sin obra social»", la lista de obras sociales se actualiza y los datos del paciente no cambian

#### Scenario: La odontóloga con enlace directo a Datos (Caso de Borde)
- **WHEN** la Dra. Ana Ficticia abre `#/pacientes/{id}?pestana=datos` de una paciente suya
- **THEN** se abre la pestaña Ficha y no se muestra la pestaña Datos

### Requirement: Vínculo de un turno con su paciente desde la agenda
En la agenda, recepción y admin SHALL ver "Vincular paciente" en los turnos sin paciente vinculado. El diálogo SHALL buscar por DNI exacto; si la persona existe SHALL ofrecer vincularla, y si no SHALL ofrecer el alta precargada con el teléfono y el nombre de contacto del turno, y vincular al guardar. La odontóloga no SHALL ver la acción.

#### Scenario: Vincular un turno con una paciente existente (Happy Path)
- **GIVEN** un turno `reservado` de hoy con contacto "Lucía Ejemplo" sin paciente vinculado, y la paciente con DNI 99000001
- **WHEN** recepción elige "Vincular paciente", busca 99000001 y confirma "Vincular a Lucía Ejemplo"
- **THEN** el turno queda vinculado, la tarjeta muestra "Ver ficha" en lugar de "Vincular paciente" y no cambian su estado, horario ni seña

#### Scenario: DNI no registrado (Error de Negocio)
- **GIVEN** un turno con contacto "Carlos Sintético", `+5491100000003`, sin paciente
- **WHEN** recepción busca el DNI 99000003, que no existe
- **THEN** ve "No hay ningún paciente con ese DNI" y "Dar de alta y vincular", con el formulario precargado con DNI 99000003, teléfono `+5491100000003` y "Carlos Sintético" para separar en nombre y apellido; al guardar se crea el paciente y queda vinculado

#### Scenario: El alta se crea pero el vínculo falla (Caso de Borde)
- **GIVEN** que el alta del paciente responde 201 y el vínculo responde error de red
- **WHEN** recepción elige "Dar de alta y vincular"
- **THEN** ve "Creamos el paciente pero no pudimos vincular el turno" con "Reintentar vínculo", que vincula sin crear un segundo paciente

### Requirement: Corrección de un vínculo existente
En un turno ya vinculado, recepción y admin SHALL poder "Cambiar paciente". Antes de enviar, el panel SHALL pedir confirmación avisando que la profesional del turno puede ganar o perder acceso clínico a cada paciente (C-12 O9).

#### Scenario: Corregir un vínculo equivocado (Happy Path)
- **GIVEN** un turno `atendido` vinculado por error con "Mateo Prueba"
- **WHEN** recepción elige "Cambiar paciente", busca el DNI de "Lucía Ejemplo" y confirma el aviso
- **THEN** el turno queda vinculado con Lucía y la tarjeta enlaza a su ficha

#### Scenario: Elegir el mismo paciente (Error de Negocio)
- **GIVEN** un turno vinculado con "Lucía Ejemplo"
- **WHEN** recepción elige "Cambiar paciente" y busca el DNI de Lucía
- **THEN** ve "El turno ya está vinculado con esta paciente" y no se envía ningún pedido

#### Scenario: Cancelar la confirmación (Caso de Borde)
- **WHEN** recepción ve el aviso de acceso clínico y elige "Volver"
- **THEN** el diálogo vuelve a la búsqueda y el vínculo no cambia

### Requirement: Acceso a la ficha desde la agenda
Cada turno vinculado SHALL mostrar "Ver ficha", que abre `#/pacientes/{id}` del paciente del turno, a recepción, admin y la odontóloga. Un turno sin vínculo no SHALL mostrarlo.

#### Scenario: La odontóloga abre la ficha de su turno (Happy Path)
- **GIVEN** un turno `atendido` de hoy de la Dra. Ana Ficticia vinculado con "Lucía Ejemplo"
- **WHEN** la odontóloga elige "Ver ficha" en la tarjeta
- **THEN** se abre el detalle de Lucía con la ficha editable

#### Scenario: Primera visita todavía sin atender (Error de Negocio)
- **GIVEN** un turno `confirmado` de hoy de la odontóloga vinculado con una paciente que nunca atendió
- **WHEN** elige "Ver ficha"
- **THEN** ve "Vas a poder ver la ficha cuando marques el turno como atendido" y ningún dato clínico

#### Scenario: Turno sin vínculo (Caso de Borde)
- **GIVEN** un turno de la odontóloga sin paciente vinculado
- **WHEN** consulta su agenda
- **THEN** la tarjeta no muestra "Ver ficha" ni "Vincular paciente"

### Requirement: Pantallas de pacientes a 360 px
El detalle, el alta, la edición y el diálogo de vínculo SHALL funcionar a 360 px sin desplazamiento horizontal, con acciones de al menos 48 px de alto y las pestañas del detalle en una o dos filas (R3).

#### Scenario: Detalle a 360 px (Happy Path)
- **GIVEN** un viewport de 360 × 800
- **WHEN** recepción abre cada pestaña del detalle de "Lucía Ejemplo"
- **THEN** el ancho del documento no supera el de la ventana y cada botón mide al menos 48 px de alto

#### Scenario: Rechazo visible a 360 px (Error de Negocio)
- **GIVEN** un viewport de 360 × 800
- **WHEN** recepción intenta dar de alta un DNI ya registrado
- **THEN** el mensaje "Ya hay un paciente con ese DNI" y su enlace se leen completos sin desplazamiento horizontal

#### Scenario: Nombre de 100 caracteres (Caso de Borde)
- **GIVEN** un paciente sintético de nombre y apellido de 100 caracteres cada uno
- **WHEN** se abre su detalle a 360 px
- **THEN** el nombre se corta en varias líneas sin desbordar la pantalla
