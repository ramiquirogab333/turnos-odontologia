# Spec Delta: plataforma/auditoria

## Purpose
Garantiza que toda acción de gestión interna del panel deje un rastro inmutable de quién la hizo, qué hizo, sobre qué entidad, cuándo y desde qué IP (RN-GL-01, US-011), y permite consultarlo con filtros y permisos (C-13, decisiones O1–O10, PENDIENTES de aprobación).

## ADDED Requirements

### Requirement: Toda acción aceptada del panel deja un registro en la misma transacción
Cada acción aceptada de gestión interna SHALL dejar, en la misma transacción que el cambio, un registro con el usuario, la acción, la entidad, su id, el instante con zona horaria y los datos de antes y después que la acción define. Si el registro no puede guardarse, la acción SHALL revertirse. Una acción rechazada (validación, permiso, regla de negocio) no SHALL dejar registro.

#### Scenario: Cierre de caja auditado (Happy Path)
- **GIVEN** la usuaria `recepcion@turnos.test` y el día 2026-11-12 terminado y sin cierre
- **WHEN** cierra la caja de ese día
- **THEN** existe un registro con su usuario, acción `cierre_caja`, entidad `cierre_caja`, el id del cierre y el instante del cierre

#### Scenario: Acción rechazada sin rastro (Error de Negocio)
- **GIVEN** un día que ya tiene un cierre vigente
- **WHEN** recepción intenta cerrarlo otra vez y recibe 409
- **THEN** no queda ningún registro nuevo de auditoría

#### Scenario: Falla al guardar el registro (Caso de Borde)
- **GIVEN** que la escritura del registro de auditoría falla dentro de la transacción de un cierre de caja
- **WHEN** recepción cierra el día
- **THEN** el cierre no se guarda y la respuesta es un error, nunca un cierre sin rastro

### Requirement: Los registros no contienen datos personales ni secretos
Ningún registro SHALL contener nombre, apellido, DNI, teléfono, email, número de afiliado ni contenido clínico de un paciente, ni contraseñas, tokens, códigos de gestión o el texto de una búsqueda (R19, Ley 25.326). Un intento de guardar alguno de esos datos SHALL hacer fallar la acción en lugar de guardarse.

#### Scenario: Alta manual sin datos personales (Happy Path)
- **GIVEN** un alta manual de turno para "Carlos Sintético" (+5491100000077)
- **WHEN** recepción la confirma
- **THEN** el registro contiene el id del turno y su estado, y no contiene el nombre ni el teléfono

#### Scenario: Datos prohibidos en un registro (Error de Negocio)
- **GIVEN** un caso de uso que, por error de programación, intenta auditar un dato con la clave `telefono`
- **WHEN** se ejecuta
- **THEN** la acción falla y no se guarda ni el cambio ni el registro

#### Scenario: Dato prohibido anidado (Caso de Borde)
- **GIVEN** un caso de uso que intenta auditar `{"lineas": [{"dni": "99000001"}]}`
- **WHEN** se ejecuta
- **THEN** la acción falla igual que con la clave en el primer nivel

### Requirement: Los registros de pedidos autenticados guardan la IP real
Todo registro originado en un pedido autenticado SHALL guardar la IP real del cliente, resuelta con la misma regla de proxies de confianza que el login (C-15). Los registros del sistema (trabajos programados, webhooks) o de pacientes sin login SHALL guardar la IP vacía o la del pedido público, nunca un texto inventado.

#### Scenario: Devolución de seña con IP (Happy Path)
- **GIVEN** la usuaria `admin@turnos.test` operando desde `203.0.113.20` sin proxy de confianza
- **WHEN** registra la devolución de una seña
- **THEN** el registro `devolucion_sena_registrada` guarda la IP `203.0.113.20`

#### Scenario: Cabecera falsificada sin proxy de confianza (Error de Negocio)
- **GIVEN** `TRUSTED_PROXIES` vacío y un pedido desde `203.0.113.20` con `X-Forwarded-For: 198.51.100.9`
- **WHEN** recepción marca un turno ausente
- **THEN** el registro guarda `203.0.113.20`, no la dirección de la cabecera

#### Scenario: Registro del sistema (Caso de Borde)
- **GIVEN** el barrido de pre-reservas vencidas del worker
- **WHEN** vence un turno `en_espera`
- **THEN** el registro queda sin usuario y con la IP vacía

### Requirement: El ingreso fallido no guarda el email intentado
El registro `LOGIN_FAILED` SHALL conservar la IP y el motivo, pero nunca el email ingresado: sin cuenta existente su `entidad_id` SHALL quedar vacío, y con una cuenta existente solo su id (C-13 O17).

#### Scenario: Email inexistente (Happy Path)
- **WHEN** alguien ingresa `nadie.existe@turnos.test` con una clave errónea
- **THEN** responde 401 y el registro `LOGIN_FAILED` queda con `entidad_id` vacío y sin el email en ninguna columna

#### Scenario: Usuaria existente con clave errónea (Error de Negocio)
- **WHEN** `recepcion@turnos.test` ingresa con una clave errónea
- **THEN** el registro conserva su id como `entidad_id` y no contiene el email

#### Scenario: Bloqueo por intentos (Caso de Borde)
- **WHEN** un mismo email inexistente acumula 5 fallos y hace un sexto intento
- **THEN** responde 429 y el bloqueo funciona igual, sin depender del email guardado en la auditoría

### Requirement: Toda ruta autenticada declara su política de auditoría
Cada ruta autenticada del panel, de administración, del alta interna de turnos y de sesión SHALL tener declarada una política: `semantica` (audita la acción), `lectura` (audita el acceso) o `exenta` (con motivo escrito). La suite de pruebas SHALL fallar si existe una ruta sin política o una política de una ruta inexistente.

#### Scenario: Todas las rutas con política (Happy Path)
- **GIVEN** las rutas actuales de `/api/panel/*`, `/api/admin/*`, `/api/turnos` y `/api/auth/*`
- **WHEN** corre la verificación de cobertura
- **THEN** cada ruta tiene exactamente una política y la verificación pasa

#### Scenario: Ruta nueva sin política (Error de Negocio)
- **GIVEN** que se agrega una ruta `POST /api/panel/algo-nuevo` sin declarar su política
- **WHEN** corre la verificación de cobertura
- **THEN** falla nombrando el método y la ruta

#### Scenario: Ruta exenta sin motivo (Caso de Borde)
- **GIVEN** una ruta declarada `exenta` con el motivo vacío
- **WHEN** corre la verificación de cobertura
- **THEN** falla: toda exención lleva un motivo

### Requirement: El registro de auditoría es de solo agregado
Ningún registro de auditoría SHALL poder modificarse ni borrarse, ni desde la aplicación ni con SQL directo de la aplicación; la base SHALL rechazarlo. Un usuario con registros de auditoría no SHALL poder borrarse (se desactiva).

#### Scenario: Agregar un registro (Happy Path)
- **WHEN** una acción aceptada agrega su registro
- **THEN** el registro queda guardado con su instante

#### Scenario: Intento de modificar o borrar (Error de Negocio)
- **GIVEN** un registro existente
- **WHEN** se ejecuta un `UPDATE` o un `DELETE` sobre él
- **THEN** la base rechaza la sentencia y el registro queda idéntico

#### Scenario: Borrar un usuario con historia (Caso de Borde)
- **GIVEN** la usuaria `recepcion@turnos.test` con registros de auditoría
- **WHEN** se intenta borrar su fila de usuario
- **THEN** la base lo rechaza y los registros siguen apuntando a ella

### Requirement: Consulta filtrada de la auditoría
`GET /api/panel/auditoria` SHALL devolver los registros del más reciente al más antiguo, filtrables por entidad, id de entidad, usuario, tipo de acción y rango de fechas (por defecto los últimos 7 días, máximo 366), paginados por cursor (1 a 100 por página, 50 por defecto). Cada fila SHALL traer instante con zona, usuario (id y nombre) o vacío, acción, tipo legible, entidad, id, datos e IP.

#### Scenario: Historia de un turno (Happy Path)
- **GIVEN** el turno 501 creado por alta manual, marcado `atendido` y luego corregido con `deshacer_atendido`
- **WHEN** el admin consulta con `entidad=turno&entidad_id=501`
- **THEN** recibe los tres registros del más reciente al más antiguo, con sus usuarios y los tipos `deshacer_atendido`, `marcado_atendido` y `alta_manual`

#### Scenario: Rango inválido (Error de Negocio)
- **WHEN** el admin consulta con `desde` posterior a `hasta`, o con un rango de 400 días
- **THEN** recibe 422 y ningún registro

#### Scenario: Paginación estable con registros nuevos (Caso de Borde)
- **GIVEN** 120 registros en el rango y la primera página de 50 ya leída
- **WHEN** se agregan 3 registros nuevos y el admin pide la segunda página con el cursor recibido
- **THEN** recibe los 50 siguientes a la primera página, sin repetir ni saltear ninguno

### Requirement: Solo el admin consulta la auditoría
Solo un usuario con rol `admin` SHALL poder consultar la auditoría (O6). Recepción y odontóloga SHALL recibir 403 sin ningún registro. Cada consulta aceptada SHALL quedar auditada como `lectura_auditoria` con sus filtros.

#### Scenario: Admin consulta (Happy Path)
- **WHEN** `admin@turnos.test` consulta la auditoría del día
- **THEN** recibe 200 y queda un registro `lectura_auditoria` con los filtros usados

#### Scenario: Recepción u odontóloga consultan (Error de Negocio)
- **WHEN** `recepcion@turnos.test` o `dra.ficticia@turnos.test` consultan la auditoría
- **THEN** reciben 403, sin registros y sin `lectura_auditoria`

#### Scenario: Usuario con roles recepción y admin (Caso de Borde)
- **GIVEN** un usuario con los roles `recepcion` y `admin`
- **WHEN** consulta la auditoría
- **THEN** recibe 200: vale el permiso más amplio

### Requirement: Tipos legibles de las acciones, incluidas las históricas
Cada registro SHALL exponer un tipo legible derivado de su acción y, si corresponde, de su origen, sin modificar el registro guardado. El catálogo SHALL incluir cierre y anulación de caja, devolución de seña y de excedente, rechazo de una revisión, `deshacer_atendido` y la lectura del listado de pacientes. Una acción sin tipo conocido SHALL mostrarse como `otro` con la acción original.

#### Scenario: Acciones de C-12 con su tipo (Happy Path)
- **GIVEN** registros de un cierre, una anulación, una devolución de seña, una de excedente, un rechazo de revisión y una corrección de `atendido`
- **WHEN** el admin los consulta
- **THEN** cada uno trae su tipo: `cierre_caja`, `anulacion_cierre_caja`, `devolucion_sena`, `devolucion_excedente`, `rechazo_revision_sena` y `deshacer_atendido`

#### Scenario: Filtrar por un tipo inexistente (Error de Negocio)
- **WHEN** el admin filtra con `tipo=inventado`
- **THEN** recibe 422 con la lista de tipos válidos

#### Scenario: Registro histórico sin tipo conocido (Caso de Borde)
- **GIVEN** un registro histórico con acción `UPDATE`, entidad `configuracion_sena` y sin origen
- **WHEN** el admin lo consulta
- **THEN** lo recibe con tipo `otro` y la acción `UPDATE` original, sin que el registro guardado cambie

### Requirement: Directorio mínimo de usuarios para filtrar
`GET /api/panel/usuarios` SHALL devolver a un `admin` la lista de usuarios del panel con id, nombre completo y si está activo, sin email ni roles, para elegir el filtro por usuario de la auditoría (O3). Cualquier otro rol SHALL recibir 403.

#### Scenario: Admin lista usuarios (Happy Path)
- **WHEN** el admin pide el directorio
- **THEN** recibe 200 con `recepcion@turnos.test` como "Recepción Ficticia" (id y nombre), sin el email

#### Scenario: Recepción pide el directorio (Error de Negocio)
- **WHEN** `recepcion@turnos.test` pide el directorio
- **THEN** recibe 403 sin ningún usuario

#### Scenario: Usuario desactivado (Caso de Borde)
- **GIVEN** un usuario desactivado con registros de auditoría
- **WHEN** el admin pide el directorio
- **THEN** lo recibe marcado como inactivo, para poder filtrar su historia

### Requirement: Pantalla de auditoría del panel
La sección "Datos" del panel SHALL mostrar al admin la auditoría con filtros por fechas, usuario, tipo y entidad, con paginación "Ver más", y SHALL funcionar a 360 px de ancho (R3). La sección de auditoría no SHALL mostrarse a recepción ni a la odontóloga.

#### Scenario: Admin revisa las acciones del día (Happy Path)
- **GIVEN** el admin en un teléfono de 360 px
- **WHEN** abre "Datos" → "Auditoría" y filtra por el tipo `cierre_caja`
- **THEN** ve la lista con fecha y hora, usuario, tipo legible y entidad, sin desplazamiento horizontal

#### Scenario: Recepción no ve la auditoría (Error de Negocio)
- **WHEN** `recepcion@turnos.test` abre la sección "Datos"
- **THEN** ve la exportación pero no la pestaña de auditoría, y si fuerza la ruta recibe el mensaje de permiso insuficiente

#### Scenario: Sin resultados (Caso de Borde)
- **WHEN** el admin filtra un rango sin registros
- **THEN** ve "No hay registros para estos filtros" y ningún botón "Ver más"
