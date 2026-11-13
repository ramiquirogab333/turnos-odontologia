# plataforma/exportacion-datos Specification

## Purpose
Permite a recepción y admin sacar del sistema, de forma masiva y tabular, los turnos, los pacientes y los cierres de caja para respaldarlos o migrarlos (RN-GL-02, US-012), minimizando datos de salud, protegiendo la planilla de fórmulas maliciosas y dejando rastro de cada exportación (C-13, decisiones O7, O8, O11–O15, PENDIENTES de aprobación).

## Requirements

### Requirement: Exportación de turnos en CSV
`GET /api/panel/export?entidad=turnos&formato=csv` SHALL devolver un archivo CSV descargable con una fila por turno y las columnas id, inicio, fin, estado, origen, profesional, sillón, tratamiento, id de paciente, nombre y teléfono de contacto, filtrable por rango de fechas de inicio (`desde`/`hasta`, ambos opcionales). Nunca SHALL incluir el código de gestión ni identificadores de la pasarela.

#### Scenario: Turnos de una semana (Happy Path)
- **GIVEN** 3 turnos que empiezan entre el 2026-11-16 y el 2026-11-20 y 1 el 2026-11-25, uno de ellos de "Lucía Ejemplo" (+5491100000001)
- **WHEN** recepción exporta con `desde=2026-11-16&hasta=2026-11-20`
- **THEN** recibe 200 con un CSV de encabezado más 3 filas, con los instantes en ISO-8601 con el desfase de la clínica (`-03:00`) y sin ninguna columna de código de gestión

#### Scenario: Entidad o formato no soportados (Error de Negocio)
- **WHEN** recepción pide `entidad=fichas` o `formato=xlsx`
- **THEN** recibe 422 con los valores válidos y ningún archivo

#### Scenario: Rango sin turnos (Caso de Borde)
- **WHEN** recepción exporta un rango sin turnos
- **THEN** recibe 200 con un CSV que solo tiene el encabezado

### Requirement: Exportación de pacientes en CSV
`entidad=pacientes` SHALL devolver una fila por paciente con id, nombre, apellido, DNI, teléfono, email, obra social, número de afiliado, activo y fecha de alta. Nunca SHALL incluir ficha, odontograma, presupuestos ni pagos (datos clínicos fuera de alcance). Por defecto incluye solo pacientes activos; `incluir_inactivos=true` suma los inactivos.

#### Scenario: Pacientes activos (Happy Path)
- **GIVEN** "Lucía Ejemplo" (DNI 99000001, activa) y "Mateo Prueba" (DNI 99000002, inactivo)
- **WHEN** el admin exporta pacientes
- **THEN** recibe un CSV con una fila, la de "Lucía Ejemplo", sin columnas de alergias, medicación ni antecedentes

#### Scenario: Sin permiso para pacientes (Error de Negocio)
- **WHEN** `recepcion@turnos.test` pide `entidad=pacientes`
- **THEN** recibe 403 y ningún archivo (O7: solo admin exporta pacientes)

#### Scenario: Incluir inactivos (Caso de Borde)
- **WHEN** el admin exporta pacientes con `incluir_inactivos=true`
- **THEN** recibe las dos filas y la columna activo dice `false` para "Mateo Prueba"

### Requirement: Exportación de cierres de caja en CSV
`entidad=cierres_caja` SHALL devolver una fila por cierre con id, día, estado (`vigente` o `anulado`), totales de ingresos, egresos y neto con dos decimales, quién y cuándo cerró, y quién, cuándo y por qué se anuló, filtrable por rango de días.

#### Scenario: Cierres del mes (Happy Path)
- **GIVEN** cierres vigentes del 2026-11-02 y del 2026-11-03, con neto "15000.00" y "0.00"
- **WHEN** recepción exporta con `desde=2026-11-01&hasta=2026-11-30`
- **THEN** recibe dos filas con los totales exactos `15000.00` y `0.00`, sin redondeos de punto flotante

#### Scenario: Odontóloga exporta (Error de Negocio)
- **WHEN** `dra.ficticia@turnos.test` pide cualquier exportación
- **THEN** recibe 403 y ningún archivo

#### Scenario: Día con cierre anulado y uno vigente (Caso de Borde)
- **GIVEN** el 2026-11-04 con un cierre anulado y uno vigente posterior
- **WHEN** recepción exporta ese día
- **THEN** recibe las dos filas, una `anulado` con su motivo y otra `vigente`

### Requirement: La exportación grande se entrega por partes sin frenar el servicio
La exportación SHALL enviarse por partes a medida que se lee, sin armar el archivo entero en memoria, y SHALL reflejar una sola foto consistente de los datos aunque haya cambios durante la descarga. Mientras dura, el resto de la API SHALL seguir respondiendo.

#### Scenario: Cien mil turnos (Happy Path)
- **GIVEN** 100 000 turnos sintéticos
- **WHEN** el admin exporta turnos sin filtros
- **THEN** recibe 100 001 líneas y la memoria del proceso no crece en proporción a la cantidad de filas

#### Scenario: Cambio durante la descarga (Error de Negocio)
- **GIVEN** una exportación de turnos en curso
- **WHEN** recepción cancela uno de esos turnos antes de que termine la descarga
- **THEN** el archivo muestra el estado que el turno tenía al empezar la exportación, sin filas duplicadas ni faltantes

#### Scenario: Otra petición durante la descarga (Caso de Borde)
- **GIVEN** una exportación grande en curso
- **WHEN** otra usuaria pide `GET /api/panel/agenda`
- **THEN** recibe su respuesta sin esperar a que termine la exportación

### Requirement: El CSV es estándar y legible
El archivo SHALL ser CSV RFC 4180 separado por comas, en UTF-8 con marca de orden de bytes, con fin de línea CRLF, decimales con punto, instantes ISO-8601 con desfase y fechas `AAAA-MM-DD`, y un nombre de descarga con entidad y fecha. La respuesta SHALL indicar que no se guarde en caché.

#### Scenario: Valores con coma, comillas y saltos de línea (Error de Negocio)
- **GIVEN** un cierre anulado con motivo `Error de carga, "duplicado"`
- **WHEN** se exporta
- **THEN** la celda llega entre comillas con las comillas internas duplicadas y la fila sigue teniendo la misma cantidad de columnas

#### Scenario: Acentos y eñes (Happy Path)
- **GIVEN** un paciente "Iñaki Muñoz Ejemplo"
- **WHEN** se exporta y se abre el archivo
- **THEN** el texto se lee sin caracteres corruptos porque el archivo declara UTF-8

#### Scenario: Encabezados de la descarga (Caso de Borde)
- **WHEN** recepción exporta turnos el 2026-11-13
- **THEN** la respuesta trae `Content-Disposition` con `turnos_2026-11-13.csv`, tipo `text/csv; charset=utf-8` y `Cache-Control: no-store`

### Requirement: Las celdas de texto libre no ejecutan fórmulas
Toda celda de texto libre (nombres, contacto, email, motivos, observaciones) que empiece con `=`, `+`, `-`, `@`, tabulación o retorno de carro SHALL exportarse precedida de un apóstrofo, para que una planilla no la ejecute como fórmula. Las columnas de formato validado (ids, números, instantes, teléfono E.164) SHALL exportarse sin cambios.

#### Scenario: Nombre de contacto malicioso (Happy Path de la defensa)
- **GIVEN** una reserva pública con nombre de contacto `=HYPERLINK("http://example.invalid","ver")`
- **WHEN** recepción exporta turnos
- **THEN** la celda llega como `'=HYPERLINK("http://example.invalid","ver")`

#### Scenario: Variantes de inicio peligroso (Error de Negocio)
- **GIVEN** nombres de contacto que empiezan con `+`, `-`, `@` y con una tabulación
- **WHEN** se exportan
- **THEN** las cuatro celdas llegan precedidas de un apóstrofo

#### Scenario: Teléfono E.164 intacto (Caso de Borde)
- **GIVEN** un contacto con teléfono `+5491100000001`
- **WHEN** se exporta
- **THEN** la celda de teléfono llega exactamente `+5491100000001`, sin apóstrofo

### Requirement: Cada exportación queda auditada antes de enviar datos
Antes de enviar el primer byte, cada exportación aceptada SHALL dejar un registro `exportacion` con el usuario, la IP, la entidad, los filtros y la cantidad de filas de la foto exportada, sin ningún dato exportado. Si el registro no puede guardarse, la exportación no SHALL empezar. Una exportación rechazada no SHALL dejar registro.

#### Scenario: Exportación auditada (Happy Path)
- **WHEN** el admin exporta pacientes con `incluir_inactivos=true` desde `203.0.113.20`
- **THEN** existe un registro `exportacion` con su usuario, la IP, entidad `paciente`, el filtro y la cantidad de filas, sin nombres ni DNI

#### Scenario: Exportación rechazada (Error de Negocio)
- **WHEN** recepción pide pacientes y recibe 403
- **THEN** no queda ningún registro `exportacion`

#### Scenario: Descarga interrumpida (Caso de Borde)
- **GIVEN** una exportación que ya empezó a enviarse
- **WHEN** el navegador corta la descarga a la mitad
- **THEN** el registro `exportacion` ya existe y el servidor libera la conexión a la base

### Requirement: Límite de exportaciones por usuario
Cada usuario SHALL poder tener a lo sumo una exportación en curso y hacer como máximo `EXPORT_MAX_POR_HORA` exportaciones por hora (20 por defecto). Superado el límite, la API SHALL responder 429 con `motivo: "demasiados_intentos"` y `Retry-After`, sin auditar ni exportar.

#### Scenario: Exportaciones normales (Happy Path)
- **WHEN** recepción hace 3 exportaciones seguidas, cada una terminada antes de la siguiente
- **THEN** las tres responden 200

#### Scenario: Superar el máximo por hora (Error de Negocio)
- **GIVEN** recepción con 20 exportaciones en la última hora
- **WHEN** pide la número 21
- **THEN** recibe 429 con `Retry-After` y no queda registro `exportacion`

#### Scenario: Dos exportaciones simultáneas (Caso de Borde)
- **GIVEN** una exportación de recepción en curso
- **WHEN** la misma usuaria pide otra desde otra pestaña
- **THEN** la segunda recibe 429 y la primera termina normalmente

### Requirement: Pantalla de exportación del panel
La sección "Datos" del panel SHALL permitir elegir la entidad (según el rol), un rango de fechas opcional y descargar el CSV con la sesión vigente, mostrando el progreso y los errores (403, 429, red) en lenguaje claro, y SHALL funcionar a 360 px (R3).

#### Scenario: Recepción descarga los turnos de la semana (Happy Path)
- **GIVEN** recepción en un teléfono de 360 px
- **WHEN** abre "Datos", elige "Turnos", el rango de la semana y toca "Descargar CSV"
- **THEN** se descarga `turnos_<fecha>.csv` y el botón vuelve a habilitarse

#### Scenario: Límite alcanzado (Error de Negocio)
- **WHEN** la descarga responde 429 con `Retry-After: 600`
- **THEN** ve "Hiciste muchas exportaciones seguidas. Probá de nuevo en 10 minutos" y no se descarga nada

#### Scenario: Opciones según el rol (Caso de Borde)
- **WHEN** recepción abre "Datos"
- **THEN** ve "Turnos" y "Cierres de caja" pero no "Pacientes", que solo ve el admin
