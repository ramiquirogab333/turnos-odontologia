# Spec Delta

## Purpose

Pantallas del panel de la clínica para que recepción y admin administren tratamientos (duración y precio), profesionales, sillones y horarios de atención sin tocar código (US-008), respetando los turnos ya tomados y funcionando a 360 px.

## ADDED Requirements

### Requirement: Sección Catálogo solo para recepción y admin
El panel SHALL ofrecer la sección "Catálogo" (`#/catalogo`) con las pestañas Tratamientos, Profesionales, Sillones y Horarios solo a usuarios con rol `recepcion` o `admin`. A un usuario solo `odontologo` la sección SHALL no aparecerle en la navegación y un enlace directo SHALL llevarlo a la agenda.

#### Scenario: Recepción abre el catálogo (Happy Path)
- **GIVEN** `recepcion@turnos.test` con sesión iniciada
- **WHEN** elige "Catálogo" en la navegación
- **THEN** ve la sección con las pestañas Tratamientos, Profesionales, Sillones y Horarios, y la pestaña Tratamientos abierta

#### Scenario: La odontóloga entra por enlace directo (Error de Negocio)
- **GIVEN** `dra.ficticia@turnos.test` con solo el rol `odontologo`
- **WHEN** abre `#/catalogo?pestana=horarios`
- **THEN** ve la agenda, la navegación no muestra "Catálogo" y no se pide ningún recurso de `/api/admin/*`

#### Scenario: Pestaña inválida en el hash (Caso de Borde)
- **GIVEN** recepción con sesión iniciada
- **WHEN** abre `#/catalogo?pestana=precios`
- **THEN** se abre la pestaña Tratamientos sin error

### Requirement: El catálogo se carga en paralelo
Al abrir la sección, el panel SHALL pedir tratamientos, profesionales, sillones y franjas al mismo tiempo, no uno detrás de otro (R2). Si alguno falla, SHALL mostrar que no se pudo cargar el catálogo y ofrecer reintentar, sin mostrar listas vacías como si no hubiera datos.

#### Scenario: Carga en paralelo (Happy Path)
- **GIVEN** recepción con sesión iniciada y un catálogo con datos sintéticos
- **WHEN** abre la sección Catálogo
- **THEN** los cuatro pedidos salen antes de que termine el primero y la pestaña muestra los datos

#### Scenario: Falla una de las cuatro listas (Error de Negocio)
- **GIVEN** que `GET /api/admin/sillones` responde 500
- **WHEN** recepción abre la sección
- **THEN** la pantalla dice "No pudimos cargar el catálogo" con el botón "Reintentar" y no muestra ninguna lista

#### Scenario: Catálogo vacío (Caso de Borde)
- **GIVEN** que no hay tratamientos cargados
- **WHEN** recepción abre la pestaña Tratamientos
- **THEN** ve el texto que invita a cargar el primero y el botón "Agregar tratamiento"

### Requirement: Pantalla de tratamientos
La pestaña Tratamientos SHALL listar cada tratamiento con nombre, duración en minutos, precio base y estado como texto ("Activo" / "Inactivo"); los inactivos atenuados con "No se ofrece para reservar" y los de precio 0 con "Sin seña". SHALL permitir agregar y editar nombre, duración y precio, avisando que la duración y el precio nuevos solo valen para turnos nuevos.

#### Scenario: Cambiar la duración de un tratamiento (Happy Path)
- **GIVEN** "Limpieza dental" de 45 minutos
- **WHEN** recepción la edita a 60 minutos y elige "Guardar cambios"
- **THEN** la lista muestra 60 min y la pantalla confirma "Guardamos los cambios"; los turnos ya tomados conservan su horario

#### Scenario: Duración fuera de rango (Error de Negocio)
- **WHEN** recepción guarda una duración de 7 minutos
- **THEN** el formulario muestra junto al campo "La duración va de 5 a 480 minutos, en múltiplos de 5", conserva lo escrito y el tratamiento no cambia

#### Scenario: Precio 0 (Caso de Borde)
- **WHEN** recepción guarda "Control de prueba" con precio 0
- **THEN** la fila muestra "Sin seña" y antes de guardar el formulario avisa que los turnos de ese tratamiento no pedirán seña (RN-SN-06)

### Requirement: Pantallas de profesionales y sillones
La pestaña Profesionales SHALL listar nombre, especialidad, matrícula y estado, y permitir agregar, editar, desactivar y reactivar. La pestaña Sillones SHALL listar nombre y estado ("Disponible", "En mantenimiento", "Fuera de uso") y permitir agregar, renombrar y cambiar el estado. Un nombre o matrícula repetidos SHALL mostrarse como error del campo.

#### Scenario: Poner un sillón en mantenimiento (Happy Path)
- **GIVEN** "Sillón 2" disponible
- **WHEN** recepción cambia su estado a "En mantenimiento" y confirma
- **THEN** la lista muestra "En mantenimiento" y el sillón deja de ofrecerse para turnos nuevos

#### Scenario: Matrícula repetida (Error de Negocio)
- **GIVEN** "Dra. Ana Ficticia" con matrícula `MP-99001`
- **WHEN** recepción carga "Dr. Juan Ejemplo" con la matrícula `mp-99001`
- **THEN** el campo matrícula muestra "Ya hay una profesional con esa matrícula" y no se crea nadie

#### Scenario: Profesional sin especialidad (Caso de Borde)
- **WHEN** recepción carga "Dr. Juan Ejemplo" con matrícula `MP-99002` y sin especialidad
- **THEN** se crea y la lista muestra "Sin especialidad" en lugar de un espacio vacío

### Requirement: Editor de horarios de atención
La pestaña Horarios SHALL mostrar, para la profesional elegida, un bloque por día de lunes a domingo con sus franjas (inicio, fin, sillón preferido, estado "Activa"/"Pausada") o "Sin atención este día", y permitir agregar, editar, pausar, reactivar y quitar franjas. Las horas SHALL leerse en la hora de la clínica.

#### Scenario: Agregar una franja (Happy Path)
- **GIVEN** "Dra. Ana Ficticia" sin franjas los martes
- **WHEN** recepción agrega una franja el martes de 09:00 a 13:00 con "Sillón 1"
- **THEN** el bloque del martes la muestra como "Activa" y los horarios libres públicos de ese martes la incluyen

#### Scenario: Franja que se pisa con otra (Error de Negocio)
- **GIVEN** una franja activa del lunes de 09:00 a 13:00
- **WHEN** recepción agrega otra el lunes de 12:00 a 15:00
- **THEN** el formulario dice "Se superpone con la franja de 09:00 a 13:00 del lunes", conserva lo escrito y no se crea nada

#### Scenario: Franjas contiguas (Caso de Borde)
- **GIVEN** una franja activa del lunes de 09:00 a 13:00
- **WHEN** recepción agrega otra el lunes de 13:00 a 17:00
- **THEN** se crea y el lunes muestra las dos franjas en orden

### Requirement: Confirmación con impacto en turnos tomados
Antes de desactivar o borrar un tratamiento, profesional, sillón o franja, o de pausar o cambiar el horario de una franja, el panel SHALL mostrar cuántos turnos futuros vigentes la alcanzan y aclarar que no se cancelan. Sin turnos alcanzados SHALL decirlo. Si no puede consultar el impacto, SHALL decirlo y permitir seguir.

#### Scenario: Quitar una franja con turnos (Happy Path)
- **GIVEN** una franja del lunes de 14:00 a 18:00 con 3 turnos futuros
- **WHEN** recepción elige "Quitar franja"
- **THEN** el diálogo dice que hay 3 turnos tomados en esa franja, que no se cancelan y siguen en la agenda, y que los pacientes nuevos ya no podrán reservar en ese horario; al confirmar la franja desaparece y los 3 turnos siguen en la agenda

#### Scenario: Borrar un tratamiento usado (Error de Negocio)
- **GIVEN** "Consulta odontológica" con turnos pasados
- **WHEN** recepción confirma "Borrar"
- **THEN** la pantalla explica que no se puede borrar porque tiene turnos registrados y ofrece "Desactivar"; el tratamiento sigue en la lista

#### Scenario: No se pudo consultar el impacto (Caso de Borde)
- **GIVEN** que la consulta de impacto falla por red
- **WHEN** recepción elige "Desactivar" en un profesional
- **THEN** el diálogo dice "No pudimos revisar los turnos tomados; los turnos existentes no se cancelan igual" y permite confirmar o volver

### Requirement: Pantallas del catálogo a 360 px
Todas las pestañas del catálogo SHALL funcionar a 360 px sin scroll horizontal de la página, con objetivos táctiles de al menos 48 px, estados legibles como texto, foco visible con teclado y textos en sentence case. Un error del servidor SHALL explicar qué pasó y cómo seguir, sin perder lo escrito.

#### Scenario: Editor de horarios a 360 px (Happy Path)
- **GIVEN** recepción en un dispositivo de 360x800
- **WHEN** abre la pestaña Horarios con una profesional de cinco franjas
- **THEN** el ancho del documento no supera el de la ventana y cada botón mide al menos 48 px de alto

#### Scenario: Sesión vencida al guardar (Error de Negocio)
- **GIVEN** recepción editando un tratamiento y su sesión vencida sin poder renovarse
- **WHEN** elige "Guardar cambios"
- **THEN** el panel vuelve a la pantalla de ingreso con el aviso de sesión vencida y no muestra datos del catálogo

#### Scenario: Doble toque en guardar (Caso de Borde)
- **GIVEN** recepción con el formulario de una franja nueva completo
- **WHEN** toca "Guardar" dos veces seguidas
- **THEN** sale un solo pedido de alta, el botón queda deshabilitado mientras espera y se crea una sola franja
