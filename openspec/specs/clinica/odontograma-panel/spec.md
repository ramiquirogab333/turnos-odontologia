# clinica/odontograma-panel Specification

## Purpose
Pantalla del panel para ver el estado vigente del odontograma FDI de un paciente, registrar hallazgos en lote (solo alta) y consultar su historial, usable a 360 px por recepción, admin y la odontóloga sobre sus pacientes.

## Requirements

### Requirement: Estado vigente por pieza y cara
La pestaña Odontograma SHALL mostrar las piezas FDI agrupadas por cuadrante (permanentes 11–48; temporales 51–85 al elegir "Temporales"), cada una con su número y su estado vigente como texto (estado de pieza y caras con hallazgo), no solo con color. Una pieza sin hallazgos SHALL leerse como "Sin hallazgos".

#### Scenario: Odontograma con hallazgos (Happy Path)
- **GIVEN** la pieza 16 con caries en la cara O y la 36 con estado `endodoncia`
- **WHEN** recepción abre la pestaña Odontograma
- **THEN** la pieza 16 dice "Caries: oclusal", la 36 dice "Endodoncia" y las demás "Sin hallazgos"

#### Scenario: Paciente ajena (Error de Negocio)
- **GIVEN** la odontóloga sin `atendido` con la paciente
- **WHEN** abre `#/pacientes/{id}?pestana=odontograma` y el servidor responde 403 `paciente_ajeno`
- **THEN** ve el mensaje de falta de acceso y ninguna pieza

#### Scenario: Pieza devuelta a sano (Caso de Borde)
- **GIVEN** la pieza 16 con caries O registrada y después `sano` sin cara
- **WHEN** se abre la pestaña
- **THEN** la pieza 16 dice "Sin hallazgos"

### Requirement: Registro de hallazgos en lote
Quien puede escribir (recepción, admin, la odontóloga con acceso completo) SHALL poder armar un lote eligiendo pieza, cara opcional, estado y nota opcional (≤ 500), revisarlo, quitar ítems y registrarlo con un solo envío de 1 a 64 hallazgos. El formulario SHALL ofrecer solo combinaciones válidas: caries y obturado exigen cara; ausente, extracción indicada, corona, endodoncia e implante no llevan cara; sano admite ambas.

#### Scenario: La odontóloga registra un lote (Happy Path)
- **GIVEN** la Dra. Ana Ficticia con acceso completo sobre Lucía
- **WHEN** agrega "16 · O · Caries" y "36 · Endodoncia" al lote y elige "Registrar 2 hallazgos"
- **THEN** ve "Registramos 2 hallazgos", el lote queda vacío y el estado vigente muestra ambos

#### Scenario: Combinación inválida (Error de Negocio)
- **WHEN** quien registra elige el estado "Caries" sin cara, o "Corona" e intenta elegir una cara
- **THEN** "Agregar al lote" queda deshabilitado con "Elegí la cara afectada" en el primer caso, y en el segundo el selector de cara no se ofrece; nada se envía

#### Scenario: Lote en el tope (Caso de Borde)
- **GIVEN** un lote con 64 hallazgos
- **WHEN** quien registra intenta agregar uno más
- **THEN** ve "Un lote admite hasta 64 hallazgos: registrá estos primero" y el lote no crece; "Registrar 64 hallazgos" envía todos en un solo pedido

### Requirement: El registro es solo de alta
La pantalla no SHALL ofrecer editar ni borrar un hallazgo registrado (RN-CL-01): para corregir SHALL indicar que se registre un hallazgo nuevo. Si el registro del lote falla, ningún hallazgo SHALL quedar registrado y el lote SHALL conservarse para reintentar.

#### Scenario: Corregir un hallazgo (Happy Path)
- **GIVEN** la pieza 16 con caries O registrada por error
- **WHEN** quien escribe registra "16 · O · Sano"
- **THEN** la pieza 16 dice "Sin hallazgos" y el historial muestra los dos registros

#### Scenario: Acceso vencido al registrar (Error de Negocio)
- **GIVEN** la odontóloga con un lote de 3 hallazgos y el servidor responde 403 `acceso_clinico_vencido`
- **WHEN** elige "Registrar 3 hallazgos"
- **THEN** ve "Tu acceso para editar venció. Para editar, pedí un turno a recepción", el lote se conserva visible para anotarlo, y el estado vigente no cambia

#### Scenario: Salir con un lote sin registrar (Caso de Borde)
- **GIVEN** un lote de 2 hallazgos sin registrar
- **WHEN** quien escribe cambia de pestaña o sale del detalle
- **THEN** ve "Tenés 2 hallazgos sin registrar" con "Seguir" y "Descartar"; el lote nunca se guarda en el navegador

### Requirement: Odontograma de solo lectura
Con acceso clínico de solo lectura, la pestaña SHALL mostrar el estado vigente y el historial sin el formulario de registro.

#### Scenario: Lectura con acceso completo de recepción (Happy Path)
- **WHEN** recepción abre la pestaña
- **THEN** ve el estado vigente y el formulario de registro

#### Scenario: Acceso de solo lectura (Error de Negocio)
- **GIVEN** la odontóloga con su última atención hace 13 meses y sin turno pendiente
- **WHEN** abre la pestaña
- **THEN** ve el estado vigente y el historial, y no aparece "Agregar al lote" ni "Registrar"

#### Scenario: Límite exacto de la ventana (Caso de Borde)
- **GIVEN** que el último `atendido` empezó hace exactamente 365 días
- **WHEN** la odontóloga abre la pestaña
- **THEN** ve el formulario de registro (el límite es inclusivo, RN-CL-04)

### Requirement: Historial del odontograma
La pestaña SHALL ofrecer "Ver historial" con los registros del más reciente al más antiguo (fecha y hora de la clínica, pieza, cara, estado, nota) en páginas de 50 y "Cargar más" mientras haya registros anteriores.

#### Scenario: Historial con más de una página (Happy Path)
- **GIVEN** 60 registros sintéticos
- **WHEN** quien consulta abre el historial y elige "Cargar más"
- **THEN** ve primero 50 y luego los 60, sin repetidos y en orden

#### Scenario: Falla al cargar más (Error de Negocio)
- **GIVEN** que la segunda página responde error de red
- **WHEN** elige "Cargar más"
- **THEN** los 50 ya cargados siguen visibles y aparece "No pudimos cargar más registros" con "Reintentar"

#### Scenario: Historial vacío (Caso de Borde)
- **GIVEN** un paciente sin registros
- **WHEN** abre el historial
- **THEN** ve "Todavía no hay hallazgos registrados" y no aparece "Cargar más"

### Requirement: Odontograma a 360 px
La grilla de piezas, el formulario del lote y el historial SHALL funcionar a 360 px sin desplazamiento horizontal, con cada pieza y cada acción tocable de al menos 44 × 44 px y navegables con teclado con foco visible (R3).

#### Scenario: Registrar a 360 px (Happy Path)
- **GIVEN** un viewport de 360 × 800
- **WHEN** quien escribe agrega "11 · V · Obturado" y registra
- **THEN** el ancho del documento no supera la ventana y cada pieza mide al menos 44 × 44 px

#### Scenario: Mensaje de rechazo a 360 px (Error de Negocio)
- **GIVEN** un viewport de 360 × 800
- **WHEN** el registro responde 403 `acceso_clinico_vencido`
- **THEN** el mensaje y el lote se leen completos sin desplazamiento horizontal

#### Scenario: Solo teclado (Caso de Borde)
- **WHEN** quien escribe usa solo Tab, flechas y Enter
- **THEN** puede elegir la pieza 48, su estado y registrar el lote con el foco siempre visible
