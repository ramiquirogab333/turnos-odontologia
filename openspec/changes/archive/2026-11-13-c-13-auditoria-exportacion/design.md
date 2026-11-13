# Design: c-13-auditoria-exportacion

> Governance **CRÍTICO** (logs de auditoría y datos de salud): análisis y propuesta solamente. Las decisiones no obvias están en la tabla **O1–O16** al final, cada una con opciones y una recomendada. **Todas APROBADAS (opción recomendada) por el usuario el 2026-11-13**; los specs y `tasks.md` están escritos con la opción recomendada y se ajustan si alguna cambia. No se escribe código de producción, tests ni migraciones hasta aprobarlas.

## Context

Motivación en `proposal.md` (Why). Estado actual relevado en el código (HEAD `6dc9e58`, `main` limpio, última migración `012_sesion_panel`):

**Tabla** `registro_auditoria` (migración `002`, modelo `app/models/core.RegistroAuditoria`): `id BIGINT IDENTITY`, `usuario_id` FK `usuario(id) ON DELETE SET NULL` con `ix_registro_auditoria_usuario_id`, `accion`/`entidad TEXT CHECK (LENGTH BETWEEN 2 AND 50)`, `entidad_id TEXT`, `datos_antes`/`datos_despues JSONB`, `ip TEXT` sin límite, `created_at TIMESTAMPTZ DEFAULT now()` con `ix_registro_auditoria_created_at`. Sin trigger, sin índice por entidad. Los tests la limpian con `DELETE` (`conftest.py`, lista de modelos).

**Escritura — inventario de rutas autenticadas** (lo que la política por ruta de D3 formaliza):

| Área | Rutas con registro hoy | Rutas sin registro |
|---|---|---|
| Auth (`/api/auth`) | `login` (`LOGIN_OK`/`LOGIN_FAILED`/`LOGIN_BLOQUEADO`, con IP), `logout` (`LOGOUT`) | `refresh`, `me` |
| Turnos del panel (`/api/panel`) | alta manual (`CREATE`, origen `alta_manual_panel`), ausente / atendido / cancelar (`UPDATE` turno, orígenes `marcado_*_panel`, `cancelacion_panel`), deshacer atendido (`UPDATE`, `deshacer_atendido_panel`) | `GET agenda`, `GET agenda/opciones` |
| Alta interna C-01 (`POST /api/turnos`, recepción/admin) | — | **sí: alta sin rastro** |
| Pacientes | alta, edición, vínculo, ficha (lectura y edición) | **`GET listado`, `GET ?dni=`, `GET /{id}`** (datos personales) |
| Clínica | odontograma, presupuestos y pagos de presupuesto (lecturas y escrituras, RN-CL-03) | — |
| Caja | `GET caja` (`lectura_caja`), cierre, anulación, rechazo de revisión, devoluciones de seña y de excedente | `GET cierres`, `GET cierres/{id}`, `GET liquidacion`, `GET pendientes` (agregados, sin personas) |
| Admin seña (`/api/admin`) | acreditar, `PUT config/sena` | `GET config/sena` |
| Catálogo (`/api/admin/*`) | `CREATE`/`UPDATE`/`DELETE` con la fila completa e IP | todos los `GET` |
| Recordatorios | enviado, fallido | `GET` (operativo, trae nombre de contacto) |
| Google Calendar | callback, desconectar, resolver conflicto | **`POST conexion/iniciar`**, `GET conexiones`, `GET conflictos` |
| Indicadores | — | `GET ocupacion`, `GET ausentismo` (agregados) |

Además escriben auditoría sin usuario: reserva pública, gestión del paciente, barrido de pre-reservas, webhook de Mercado Pago, sincronización de Google, comando de usuarios (`SESIONES_REVOCADAS`).

**Helpers:** siete formas de escribir (`pacientes.auditoria.auditar` —la única con `CLAVES_PROHIBIDAS`—, `pagos.service._auditar`, `auth.router._audit`, `catalogo.service.CrudService._audit`, `gcal.oauth._auditar`, `gcal.conflictos._auditar`, `notificaciones.panel._auditar`) y `session.add(RegistroAuditoria(...))` directos en `panel/service.py`, `public/service.py`, `gestion/service.py`, `pagos/barrido.py`, `panel/usuarios.py`, `gcal/sincronizacion.py`. Todos escriben **en la transacción del caso de uso** (patrón correcto, se conserva).

**Convenciones de `accion` coexistentes:** CRUD (`CREATE`, `UPDATE`, `DELETE` + `datos_despues.origen`), eventos de auth en mayúsculas, y nombres semánticos en minúsculas (`cierre_caja`, `anulacion_cierre_caja`, `sena_revision_rechazada`, `devolucion_sena_registrada`, `devolucion_excedente_registrada`, `lectura_*`, `alta_paciente`, …).

**IP:** solo auth y catálogo la guardan (con `ip_cliente`, C-15 D6); `pagos._auditar` fija `ip=None`.

**Infra disponible:** Redis + `LimitadorSolicitudes` (C-15, fail-open), worker arq (C-09), sesión async de SQLAlchemy por pedido (`get_session`), `ProxyHeadersMiddleware` puro ASGI. El panel ya tiene navegación por secciones (`Navegacion.tsx`, `lib/ruta.ts`) y cliente con renovación de sesión (`lib/api.ts`, `lib/sesion.ts`); no hace sondeos periódicos.

## Goals / Non-Goals

**Goals:**
- Que "toda acción del panel deja rastro" sea **verificable por la suite**, no una convención (contrato de cobertura).
- Un solo punto de escritura con la guarda de datos personales para todos.
- Rastro inalterable a nivel de base (sin depender de la disciplina de la aplicación).
- Exportar cientos de miles de filas con memoria constante y sin bloquear el loop.
- Ningún dato de salud o secreto innecesario en el CSV, la auditoría ni los logs.

**Non-Goals:**
- Reescribir registros históricos o unificar sus `accion` (sería alterar evidencia).
- Firma criptográfica / cadena de hashes de registros, envío a un SIEM externo.
- Exportar datos clínicos, la propia auditoría, o formatos distintos de CSV.
- Retención y purga de la auditoría (O16, supuesto abierto).
- Auditar lecturas operativas de alta frecuencia (agenda, recordatorios) y agregados sin personas.

## Decisions

### D1. Mecanismo: registro explícito en la transacción + contrato de cobertura (O1)

Se descarta el middleware HTTP como fuente del rastro:
- **No comparte la transacción**: un middleware escribe después (o antes) del commit del caso de uso, con otra conexión; puede quedar una acción sin rastro (el proceso muere entre commits) o un rastro de una acción revertida.
- **No sabe qué pasó**: ve método, ruta y estado HTTP, pero no la entidad afectada (un `POST /cierres` crea el cierre 42), ni antes/después, ni el `origen` semántico que ya usan specs aprobados (`deshacer_atendido_panel`).
- **Duplicaría** los ~45 registros explícitos que ya existen, o obligaría a borrarlos (perdiendo semántica).
- **Rompe el streaming**: `BaseHTTPMiddleware` de Starlette acumula/encadena la respuesta y tiene problemas conocidos con `StreamingResponse` y la cancelación; la exportación (D9) depende de streaming real. (Un middleware ASGI puro evitaría esto, pero no resuelve los tres puntos anteriores.)
- Para leer el cuerpo y saber la entidad habría que **leer datos personales** del request, justo lo que R19 prohíbe registrar.

Lo que **sí** aporta un middleware —cobertura automática de rutas nuevas— se obtiene con un **contrato verificado en la suite** (D3): cada ruta autenticada declara su política y un test falla si alguna no la tiene. La garantía pasa de runtime a CI, sin costo por pedido ni doble escritura.

### D2. Helper único `app/plataforma/auditoria.py`

```python
def registrar(session: AsyncSession, *, accion: str, entidad: str, entidad_id: int | str | None,
              usuario_id: int | None, antes: Mapping[str, Any] | None = None,
              despues: Mapping[str, Any] | None = None, ip: str | None | _Auto = AUTO) -> None
```
- Agrega la fila a la sesión del caso de uso (el caller hace `commit`; misma transacción, como hoy).
- **Guarda de datos personales** para todos: la lista `CLAVES_PROHIBIDAS` de C-11 se mueve acá y se amplía con `password`, `token`, `access_token`, `refresh_token`, `codigo_gestion`, `q`, `busqueda`, `contacto_nombre`, `contacto_telefono`, `url_autorizacion`, `state`, `code_verifier`. Recorre dicts y listas anidados (como hoy). Clave prohibida → `DatosProhibidosEnAuditoriaError` (la acción falla, no se guarda nada).
- `ip=AUTO` toma la IP del pedido en curso de un `ContextVar` (D4); los trabajos del sistema pasan `ip=None` explícito.
- `pacientes.auditoria.auditar`, `pagos._auditar`, `auth._audit`, `CrudService._audit`, los `_auditar` de gcal y notificaciones, y los `session.add` sueltos **delegan en `registrar` conservando exactamente los valores de `accion`/`entidad`/datos que graban hoy** (refactor sin cambio de comportamiento; los tests existentes que inspeccionan la auditoría son la red). `pacientes.auditoria` queda como reexportación para no romper imports.
- **Riesgo detectado:** el catálogo hoy guarda la fila completa (`_datos`), que para `profesional`, `tratamiento` y `sillon` incluye la columna `nombre`; al pasar por la guarda única (`nombre` está en `CLAVES_PROHIBIDAS`) esas altas fallarían. `CrudService` pasa a auditar los ids y la lista de `campos` cambiados (más los valores no identificatorios: duración, precio, estado), como ya hace `edicion_paciente`. Test RED específico en la tarea 2.3. Los registros históricos con la fila completa no se tocan (O5).

### D3. Política de auditoría por ruta + test de contrato (O1)

`app/plataforma/politica_auditoria.py`:
```python
class Politica(BaseModel): tipo: Literal["semantica", "lectura", "exenta"]; acciones: tuple[str, ...] = (); motivo: str = ""
POLITICAS: Final[Mapping[tuple[str, str], Politica]]  # (método, path_template) -> política
```
- Test `test_politica_auditoria_contrato.py`: recorre `app.routes` (`APIRoute`) con prefijo `/api/panel`, `/api/admin`, `/api/turnos`, `/api/auth`; falla si una ruta no tiene política, si una política no tiene ruta, si una `exenta` no tiene motivo, o si una `semantica`/`lectura` no lista acciones del catálogo (D5).
- Exentas iniciales (con motivo): `GET agenda`, `GET agenda/opciones`, `GET recordatorios` (lecturas operativas de alta frecuencia, cubiertas por el rastro de sesión, O2), `GET ocupacion`, `GET ausentismo`, `GET caja/cierres`, `GET caja/cierres/{id}`, `GET caja/liquidacion`, `GET caja/pendientes` (agregados o importes sin personas, C-12), `GET` de catálogo y `GET config/sena` (configuración sin personas), `GET google-calendar/conexiones` y `GET conflictos` (sin datos del paciente, RN-GC), `POST auth/refresh` (renovación técnica, C-15 D7), `GET auth/me`. `GET google-calendar/oauth/callback` se declara `semantica` (lo audita el servicio aunque llega sin token del panel).
- El contrato verifica **declaración**, no ejecución; que cada `semantica`/`lectura` efectivamente escriba lo prueban los tests de cada dominio (los existentes + los nuevos de este change).

### D4. IP en todo pedido autenticado (O9)

`get_current_user` (C-15, punto único de todos los endpoints autenticados) recibe `Request` y fija `contexto_auditoria: ContextVar[str | None]` con `ip_cliente(request)`. `registrar(ip=AUTO)` lo lee. Es seguro con asyncio: las dependencias `async` sin `yield` corren en la misma tarea que el endpoint y cada pedido tiene su contexto. Login y logout siguen pasando la IP explícita (no pasan por `get_current_user`). Test: dos pedidos concurrentes con IPs distintas (`ASGITransport(client=...)` + `asyncio.gather`) graban cada uno la suya. Alternativa descartada: agregar `ip` a las firmas de ~30 servicios (mucho churn, mismo resultado).

### D5. Catálogo de tipos legibles (O5)

`app/plataforma/tipos_auditoria.py`: tabla pura `(accion, entidad | None, origen | None) -> TipoAuditoria(codigo, etiqueta)`. Se evalúa al leer (no se guarda, no se migra). Extracto:

| Registro guardado | `tipo` | Etiqueta |
|---|---|---|
| `cierre_caja` | `cierre_caja` | Cierre de caja |
| `anulacion_cierre_caja` | `anulacion_cierre_caja` | Anulación de cierre de caja |
| `devolucion_sena_registrada` | `devolucion_sena` | Devolución de seña |
| `devolucion_excedente_registrada` | `devolucion_excedente` | Devolución de excedente |
| `sena_revision_rechazada` | `rechazo_revision_sena` | Rechazo de revisión de seña |
| `UPDATE` + turno + origen `deshacer_atendido_panel` | `deshacer_atendido` | Corrección de atendido |
| `UPDATE` + turno + origen `marcado_ausente_panel` / `marcado_atendido_panel` / `cancelacion_panel` | `marcado_ausente` / `marcado_atendido` / `cancelacion_panel` | … |
| `CREATE` + turno + origen `alta_manual_panel` | `alta_manual` | Alta manual de turno |
| `UPDATE` + turno + origen `acreditacion_sena` | `acreditacion_sena` | Acreditación de seña |
| `lectura_listado_pacientes` (nueva) | `lectura_listado_pacientes` | Lectura del listado de pacientes |
| `LOGIN_OK` / `LOGIN_FAILED` / `LOGIN_BLOQUEADO` / `LOGOUT` / `SESIONES_REVOCADAS` | `login_ok` / … | … |
| `exportacion` (nueva) | `exportacion` | Exportación de datos |
| `lectura_auditoria` (nueva) | `lectura_auditoria` | Consulta de auditoría |
| cualquier otro | `otro` | la `accion` original |

El filtro `tipo=` se traduce a un predicado ORM (`accion = :a` o `accion = 'UPDATE' AND entidad = 'turno' AND datos_despues->>'origen' = :o`). Las acciones **nuevas** de C-13 usan nombres semánticos en minúsculas (`alta_turno_interna`, `inicio_conexion_gcal`, `lectura_listado_pacientes`, `busqueda_paciente_dni`, `lectura_paciente`, `exportacion`, `lectura_auditoria`). El test de contrato de D3 exige que toda acción declarada esté en el catálogo.

### D6. Migración `013_auditoria_exportacion` (O4) — `postgresql-table-design`

Reversible, con `op.execute` dentro de la migración (único lugar donde R14 permite SQL):
1. FK de usuario: `DROP CONSTRAINT` + `ADD CONSTRAINT ... REFERENCES usuario(id) ON DELETE RESTRICT` (el índice `ix_registro_auditoria_usuario_id` ya existe, R6).
2. `ALTER TABLE registro_auditoria ADD CONSTRAINT ck_auditoria_ip_len CHECK (ip IS NULL OR LENGTH(ip) <= 45)` — se verifica antes que no haya filas que lo violen (en datos actuales solo hay IPs válidas o `testclient` histórico de 10 caracteres).
3. `CREATE INDEX ix_registro_auditoria_entidad ON registro_auditoria (entidad, entidad_id, created_at DESC)` (consulta "historia de una entidad", D7). Con el volumen de una clínica (decenas de miles de filas/año) un BRIN no aporta frente al btree de `created_at` existente; se reevalúa si supera ~10 M filas.
4. Función `registro_auditoria_inmutable()` + trigger `BEFORE UPDATE OR DELETE ... FOR EACH ROW EXECUTE FUNCTION` que lanza `RAISE EXCEPTION ... USING ERRCODE = 'P0001'` con mensaje `registro_auditoria es de solo agregado`. `TRUNCATE` no dispara triggers de fila: queda como vía de mantenimiento del DBA y de la limpieza de tests.
5. **Downgrade:** borra trigger y función, el índice y el CHECK, y restaura la FK `ON DELETE SET NULL`. Sin pérdida de filas.
- Modelo: `ForeignKey("usuario.id", ondelete="RESTRICT")`, `CheckConstraint` de IP, `Index` declarado, para que `test_models_metadata` siga coherente.
- `conftest.py`: `registro_auditoria` se limpia con `TRUNCATE ... RESTART IDENTITY CASCADE` antes de los `DELETE` del resto (si no, el trigger y la FK `RESTRICT` romperían la limpieza).
- Precedente: C-12 ya usa un trigger para proteger `cierre_caja`.

### D7. `GET /api/panel/auditoria` (O6)

- Dependencia `require_admin` (O6). Query Pydantic `AuditoriaQuery` (`extra="forbid"`): `desde`/`hasta` (fechas locales de la clínica; por defecto hoy−6 … hoy; `hasta − desde ≤ 366` días; `desde ≤ hasta`), `entidad` (`TEXT` 2–50), `entidad_id` (1–50), `usuario_id` (> 0), `tipo` (enum del catálogo D5), `por_pagina` 1–100 (50), `cursor` opaco.
- **Paginación keyset** por `(created_at DESC, id DESC)`: el cursor es `base64url(json{"t": iso, "id": n})` validado (cursor ilegible → 422). Estable ante inserciones nuevas (spec "Paginación estable"); no usa `OFFSET`.
- Respuesta `AuditoriaPagina { items: list[RegistroAuditoriaOut], siguiente: str | None }`, con `RegistroAuditoriaOut { id, fecha_hora (con zona), usuario: {id, nombre_completo} | None, accion, tipo, tipo_etiqueta, entidad, entidad_id, datos_antes, datos_despues, ip }`. Un `JOIN` a `usuario` (sin N+1).
- La consulta aceptada se audita como `lectura_auditoria` con los filtros (todos son ids, fechas o códigos; no hay texto libre).
- Rango sobre `created_at` con el índice existente; `entidad`+`entidad_id` con el índice nuevo.

### D8. Lecturas de pacientes auditadas (O2)

En `pacientes/listado.py` y `pacientes/service.py`: `lectura_listado_pacientes` (`entidad="paciente"`, `entidad_id=None`, `datos={"pagina","por_pagina","orden","con_ausencias","con_busqueda": bool,"devueltos": n}`), `busqueda_paciente_dni` (`entidad_id` = id encontrado o `None`, `datos={"encontrados": 0|1}`), `lectura_paciente` (`entidad_id` = id). Se registra y se hace `commit` **antes** de devolver la respuesta: si falla, 500 sin datos (patrón ya usado por `lectura_ficha`/`lectura_caja`). Un 404 o 403 no audita. El texto de `q` y el DNI nunca entran (la guarda de D2 bloquea `q`/`dni`).

### D9. Exportación por streaming (O11–O15)

- **Endpoint:** `GET /api/panel/export` con `ExportQuery` (`entidad: Literal["turnos","pacientes","cierres_caja"]`, `formato: Literal["csv"]`, `desde`/`hasta: date | None`, `incluir_inactivos: bool = False`). Permisos (O7): `turnos` y `cierres_caja` → recepción o admin; `pacientes` → admin. Odontóloga → 403.
- **Orden de operaciones** (antes del primer byte, para poder responder 4xx/5xx con JSON): (1) permisos y validación; (2) límite (D10) → 429; (3) abrir una **conexión dedicada** con `isolation_level="REPEATABLE READ"`, `READ ONLY` y `SET LOCAL statement_timeout` (`EXPORT_TIMEOUT_SEGUNDOS`, 300); (4) `SELECT count(*)` con los mismos filtros **en esa misma instantánea**; (5) escribir el registro `exportacion` con **otra sesión corta** (`registrar` + `commit`; la transacción de lectura es `READ ONLY`) → si falla, 500 y no se exporta (O8); (6) devolver `StreamingResponse` cuyo generador async itera `await conn.stream(select(...).execution_options(yield_per=500))` y emite el CSV por lotes.
- **Sin bloquear el loop (R16):** la lectura es I/O async con cursor del servidor; el formateo CSV es CPU liviana por lote de 500 filas (`csv.writer` sobre `io.StringIO`, se vacía en cada lote). Con 100 000 filas son ~200 lotes de microsegundos; no hace falta hilo. Se descarta un job en el worker (O14 b) porque obligaría a guardar archivos con datos de salud en reposo y servirlos después.
- **Memoria constante:** nunca se arma la lista completa; el test mide que el pico (`tracemalloc`) con 100 000 filas no supera un umbral fijo independiente de N.
- **Cierre garantizado:** el generador cierra el cursor y la conexión en `finally` (también ante `CancelledError` por desconexión del cliente) y libera el "en curso" del limitador.
- **Columnas (O11)**, en orden fijo y documentadas en el README:
  - turnos: `id, inicio, fin, estado, origen, profesional_id, profesional, sillon_id, sillon, tratamiento_id, tratamiento, paciente_id, contacto_nombre, contacto_telefono, creado_en`. Nunca `codigo_gestion`, `periodo`, ids de Mercado Pago ni datos de Google.
  - pacientes: `id, nombre, apellido, dni, telefono, email, obra_social, numero_afiliado, activo, creado_en`.
  - cierres_caja: `id, dia, estado, total_ingresos, total_egresos, total_neto, cerrado_por, cerrado_en, anulado_por, anulado_en, anulado_motivo, observaciones` (usuarios por `nombre_completo`).
  - Joins a catálogo y usuarios en la misma consulta (sin N+1).
- **Formato (O12):** RFC 4180 con `,`, `QUOTE_MINIMAL`, `\r\n`, UTF-8 con BOM (el BOM va en el primer chunk), `Numeric` como `str(Decimal)` con 2 decimales (nunca `float`, R4), instantes `isoformat()` en la zona de la clínica (`zona_clinica()`), fechas `AAAA-MM-DD`, booleanos `true`/`false`, nulos como celda vacía. Cabeceras: `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="<entidad>_<AAAA-MM-DD>.csv"`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
- **Fórmulas (O13):** función pura `neutralizar_celda(valor: str) -> str` que antepone `'` si empieza con `=`, `+`, `-`, `@`, `\t` o `\r` (OWASP CSV Injection). Se aplica solo a columnas declaradas `texto_libre` en el descriptor de cada exportación (`contacto_nombre`, `nombre`, `apellido`, `email`, `obra_social`, `numero_afiliado`, `anulado_motivo`, `observaciones`, nombres de profesional/tratamiento/usuario). `contacto_telefono`/`telefono` (E.164 validado en el borde), ids, números e instantes salen sin tocar. `contacto_nombre` es texto de la **reserva pública**, o sea controlado por un tercero anónimo: la defensa no es opcional.
- **Esquema de salida:** el contrato de la respuesta exitosa es el archivo; para R15 se declaran en OpenAPI `responses={200: {"content": {"text/csv": {}}}, 403, 422, 429: LimiteSuperadoOut, 500}` y la entrada es Pydantic.

### D10. Límite de exportaciones (O15)

Con el `LimitadorSolicitudes` de C-15 (sin primitivas nuevas):
- **Por hora:** `consumir("rl:v1:export:hora:<usuario_id>", EXPORT_MAX_POR_HORA=20, 3600)`.
- **En curso:** `consumir("rl:v1:export:encurso:<usuario_id>", 1, EXPORT_TIMEOUT_SEGUNDOS)` como *lease*; el generador hace `reiniciar(...)` en su `finally`. Si el proceso muere, el lease vence solo con el timeout.
- 429 con `respuesta_limite_superado` (`motivo: "demasiados_intentos"`, `Retry-After`). Con Redis caído rige el fail-open de C-15 (O5): se exporta igual y queda el aviso de log.
- Variables nuevas en `Settings` (`Field(gt=0)`) y Compose: `EXPORT_MAX_POR_HORA`, `EXPORT_TIMEOUT_SEGUNDOS`. Los E2E suben el máximo por hora.

### D11. Frontend del panel (O3)

- Sección nueva **"Datos"** en `lib/ruta.ts` (`#/datos`), visible para recepción y admin; la odontóloga no la ve (igual criterio que Caja). Dos pestañas: **Exportar** (recepción y admin) y **Auditoría** (solo admin, O6).
- **Exportar:** selector de entidad filtrado por rol (O7), rango de fechas opcional, botón "Descargar CSV". La descarga usa `fetch` con el access en memoria y la renovación existente (el token no viaja en la URL ni en cookie), lee la respuesta como `Blob` y dispara un `<a download>` con `URL.createObjectURL` (luego `revokeObjectURL`). Mensajes: 403 "No tenés permiso para exportar esto", 429 con minutos desde `Retry-After` (reutiliza `minutosDesdeRetryAfter` de C-15), error de red. Estado "Preparando archivo…" con el botón deshabilitado (evita la segunda exportación simultánea).
- **Auditoría:** filtros (fechas, usuario —lista de usuarios del panel—, tipo, entidad + id), lista en tarjetas a 360 px (fecha y hora local, usuario o "Sistema / paciente", etiqueta del tipo, entidad#id, IP), "Ver más" con el cursor, detalle desplegable con `datos_antes`/`datos_despues` en `<pre>` con quiebre de línea. Un solo fetch por página (R2: no hay cascadas; la lista de usuarios se pide en paralelo con la primera página con `Promise.all`).
- Para la lista de usuarios se agrega `GET /api/panel/usuarios` (solo admin, `{id, nombre_completo}`; política `exenta` con motivo "directorio del personal sin datos de pacientes"). **Alternativa** (si se prefiere no sumar ruta): filtrar por usuario con un campo numérico. Va dentro de O3.
- TS estricto sin `any` (R1), componentes `Datos`, `Exportar`, `Auditoria` en PascalCase, funciones puras testeables con Vitest (`nombreArchivo`, `parametrosExportacion`, `opcionesSegunRol`, `etiquetaActor`).
- **Límite asumido:** el `Blob` vive entero en memoria del navegador. Para el volumen de una clínica (100 000 turnos ≈ 15 MB) es aceptable; el servidor igual hace streaming (protege a la API, no al navegador). Ver Riesgos.

### D12. Estrategia de pruebas (Strict TDD)

- **Unit (pytest):** `neutralizar_celda` (6 prefijos + texto normal + vacío + `None`), formateo de filas (Decimal, zona, booleanos, nulos, comillas/comas/saltos), catálogo de tipos (cada fila de D5 + `otro`), guarda de claves prohibidas (anidadas), codificación/decodificación del cursor (ilegible → error), validación de `AuditoriaQuery`/`ExportQuery` (rangos, enum), `Settings` de exportación.
- **Contrato:** `test_politica_auditoria_contrato.py` (D3) y un test que garantiza que toda acción declarada existe en el catálogo.
- **Integración (pytest + PostgreSQL real, reloj inyectado):** migración 013 (trigger rechaza `UPDATE`/`DELETE` con SQLSTATE `P0001`; FK `RESTRICT` vía `pg_constraint`; índice vía `pg_index`; CHECK de IP; downgrade/upgrade sin pérdida), refactor de helpers (los tests de auditoría existentes de C-03…C-15 en verde sin tocarlos salvo el catálogo), IP por `ContextVar` con pedidos concurrentes, lecturas de pacientes (3 rutas × 3 escenarios, falla de auditoría → 500 sin datos con un `registrar` que lanza), alta interna y gcal iniciar auditados, consulta de auditoría (filtros, keyset estable con inserciones intermedias, permisos, `lectura_auditoria`), exportación (columnas exactas, foto consistente con un `UPDATE` concurrente durante el stream, 403/422/429, registro `exportacion` antes del stream y ausente en rechazos, desconexión a mitad libera conexión y lease, 100 000 filas con memoria acotada — marcado `slow`).
- **Vitest (panel):** funciones puras y componentes `Exportar`/`Auditoria` (roles, mensajes 403/429, "Ver más", vacío).
- **E2E Playwright (`frontend/panel/e2e/datos.spec.ts`, 360 px):** recepción descarga turnos (`page.waitForEvent('download')`, verifica nombre, BOM y encabezado), no ve "Pacientes" ni "Auditoría"; admin exporta pacientes y ve el registro `exportacion` en la pestaña Auditoría filtrando por tipo; 429 simulado con `page.route`. La suite E2E completa sigue en verde (R7).

## Risks / Trade-offs

- [El contrato verifica declaración, no ejecución: una ruta `semantica` podría no escribir] → Cada dominio ya prueba su auditoría; C-13 suma los tests de las rutas nuevas. Un test por ruta sería redundante con ellos.
- [Trigger de inmutabilidad: un bug que haga `UPDATE` sobre auditoría ahora da 500] → Es el efecto buscado; ningún código actual actualiza auditoría (relevado). La FK `SET NULL` era el único `UPDATE` implícito y pasa a `RESTRICT`.
- [Borrar usuarios queda bloqueado] → Desde C-15 los usuarios se desactivan (`--desactivar`); nadie los borra. Documentado como BREAKING operativo.
- [`TRUNCATE` sigue pudiendo vaciar la tabla] → Requiere privilegio de dueño de la tabla; la aplicación nunca lo emite (lo comprueba un grep en CI de `TRUNCATE` fuera de tests/migraciones). Separar roles de BD (O4 b) queda como mejora de despliegue.
- [Conexión de base ocupada durante toda la descarga; un cliente lento la retiene] → Una exportación por usuario (D10), `statement_timeout` y cierre en `finally`; el pool por defecto (5 + 10) alcanza para una clínica.
- [REPEATABLE READ largo retiene versiones viejas (vacuum)] → Limitado por el timeout de 300 s; volumen chico.
- [El `count(*)` previo duplica la lectura] → Es barato al lado del stream y da la cantidad para la auditoría sin actualizar el registro después (es inmutable).
- [Blob completo en el navegador] → Aceptable al volumen previsto; si una clínica supera ~200 MB, migrar a descarga nativa con un ticket de un solo uso (O3, alternativa documentada).
- [El CSV exportado sale del perímetro (Ley 25.326)] → Solo admin exporta pacientes, cada exportación queda auditada con usuario, IP, filtros y filas; el README y la pantalla avisan que el archivo contiene datos personales y debe guardarse cifrado.
- [Teléfono `+549…` en Excel se muestra como número científico] → Se prioriza la integridad para migración (O12); el README explica abrirlo con "Datos → Desde texto/CSV" y columna como texto.
- [`ContextVar` vacío fuera de un pedido] → `registrar(ip=AUTO)` cae a `None`, nunca inventa; los trabajos del sistema pasan `ip=None` explícito.
- [Volumen de la auditoría crece sin purga] → Decenas de miles de filas por año; índices adecuados; retención en O16.

## Migration Plan

1. Aprobar O1–O16; ajustar specs y tareas si alguna cambia.
2. Verificar que `013` está libre (C-14 puede ir en paralelo) y que no hay filas con `LENGTH(ip) > 45`.
3. `013_auditoria_exportacion` (`down_revision = "012_sesion_panel"`): FK `RESTRICT`, CHECK de IP, índice por entidad, función + trigger.
4. Desplegar backend y panel juntos (la sección "Datos" llama a rutas nuevas). Sin cambios en el worker.
5. Configurar `EXPORT_MAX_POR_HORA` / `EXPORT_TIMEOUT_SEGUNDOS` si los defaults no sirven.
6. **Rollback:** `alembic downgrade -1` (quita trigger, índice, CHECK y restaura `SET NULL`, sin perder filas) + imagen anterior. Los registros nuevos (`exportacion`, `lectura_*`) quedan y la versión vieja los ignora.

## Open Questions

- Ninguna que cambie specs o tareas: todas las decisiones están en la tabla O1–O16. El plazo legal de retención (O16) se responde fuera del código.

## Decisiones (O1–O16 APROBADAS el 2026-11-13; O16 queda como supuesto abierto)

| # | Prioridad | Pregunta | Opción recomendada | Alternativas |
|---|---|---|---|---|
| O1 | ALTA | ¿Cómo se garantiza que toda acción del panel deja rastro? | **APROBADA (a) 2026-11-13:** registro explícito en la transacción del caso de uso (lo existente) + helper único + política declarada por ruta verificada por un test de contrato (D1–D3) | (b) middleware ASGI que graba una fila por pedido del panel (método, ruta, estado, usuario) además de los explícitos: cobertura automática pero sin entidad ni transacción, duplica registros y complica el streaming; (c) solo agregar las llamadas que faltan, sin contrato |
| O2 | ALTA | ¿Qué lecturas se auditan además de las ya auditadas (clínica, `lectura_caja`)? | **APROBADA (a) 2026-11-13:** lecturas con datos identificables de pacientes fuera de la operación diaria: listado, búsqueda por DNI, datos administrativos; más exportaciones y consultas de auditoría | (b) (a) + agenda y recordatorios (miles de filas por día, poco valor: ya hay rastro de sesión); (c) todo `GET` del panel |
| O3 | ALTA | ¿C-13 incluye pantallas o solo API? | **APROBADA (a) 2026-11-13:** API + sección "Datos" del panel (Exportar / Auditoría) a 360 px con E2E, descarga por `fetch` + `Blob`, y `GET /api/panel/usuarios` mínimo para el filtro | (b) solo API; pantallas en un change nuevo (como C-11 → C-16): la exportación sin UI no la puede usar recepción; (c) (a) sin `GET /usuarios` (filtro por id numérico); (d) descarga nativa con ticket de un solo uso en la URL (streaming en el navegador, pero el ticket queda en historial/logs) |
| O4 | ALTA | ¿Cómo se protege la auditoría contra cambios? | **APROBADA (a) 2026-11-13:** trigger `BEFORE UPDATE OR DELETE` que rechaza, FK de usuario `ON DELETE RESTRICT`, tests limpian con `TRUNCATE` (D6) | (b) además, rol de BD de la aplicación sin `UPDATE`/`DELETE`/`TRUNCATE` sobre la tabla (más fuerte, pide cambiar Compose y credenciales); (c) sin garantía en la base, solo disciplina de la aplicación |
| O5 | Media | ¿Qué se hace con las tres convenciones de `accion`? | **APROBADA (a) 2026-11-13:** no se reescribe nada; catálogo de tipos legibles derivado de `accion` + `origen` al leer (D5); acciones nuevas en minúsculas semánticas; el catálogo deja de guardar nombre/matrícula del personal a futuro (D2) | (b) migración de datos que unifica los nombres históricos (alterar evidencia, choca con O4); (c) exponer la `accion` cruda sin catálogo |
| O6 | ALTA | ¿Quién consulta la auditoría? | **APROBADA (a) 2026-11-13:** solo `admin` (menor privilegio: contiene la actividad e IPs de colegas). **Enmienda la matriz RBAC de `03`** ("Recepción/admin: lectura/generación") | (b) recepción y admin, como dice la matriz; (c) recepción ve solo sus propias acciones y admin todo |
| O7 | ALTA | ¿Quién exporta qué? | **APROBADA (a) 2026-11-13:** turnos y cierres de caja: recepción y admin; pacientes (padrón completo con DNI y contacto): solo admin. **Enmienda US-012 / matriz `03`** para pacientes | (b) recepción y admin exportan todo (matriz tal cual); (c) solo admin exporta todo |
| O8 | ALTA | ¿Se auditan las exportaciones y cuándo? | **APROBADA (a) 2026-11-13:** un registro `exportacion` antes del primer byte, con usuario, IP, entidad, filtros y cantidad de filas (contada en la misma foto), sin contenido; si no se puede guardar, no se exporta | (b) registro al terminar la descarga (se pierde si se corta, y exige actualizar o agregar un segundo registro); (c) no auditar |
| O9 | Media | ¿Se guarda la IP en todos los registros? | **APROBADA (a) 2026-11-13:** sí, en todo registro de un pedido autenticado, vía `ContextVar` fijado en `get_current_user` (D4) | (b) solo auth y catálogo, como hoy; (c) pasando `ip` por la firma de cada servicio (mismo resultado, mucho más cambio) |
| O10 | Media | ¿Qué se hace con las escrituras del panel sin rastro (`POST /api/turnos`, iniciar Google)? | **APROBADA (a) 2026-11-13:** auditarlas (`alta_turno_interna`, `inicio_conexion_gcal`) | (b) retirar `POST /api/turnos` (**BREAKING**: lo usan tests y quizá integraciones; el panel usa `/api/panel/turnos`) y auditar iniciar; (c) declararlas `exentas` con motivo |
| O11 | ALTA | ¿Qué columnas lleva cada exportación? | **APROBADA (a) 2026-11-13:** perfil administrativo completo para respaldo/migración, sin datos clínicos ni secretos (D9): turnos con contacto, pacientes con DNI y contacto, cierres con totales y anulación; nunca `codigo_gestion` ni ids de pasarela | (b) perfil mínimo (solo ids, sin contacto ni DNI): seguro pero no sirve para migrar; (c) dos perfiles seleccionables (`minimo`/`completo`) |
| O12 | Media | ¿Qué dialecto de CSV? | **APROBADA (a) 2026-11-13:** RFC 4180 con coma, UTF-8 con BOM, CRLF, decimales con punto, ISO-8601 con desfase de la clínica (legible por máquinas para migrar) | (b) punto y coma + coma decimal (abre directo en Excel es-AR, peor para migrar); (c) parámetro `dialecto=rfc|excel_ar` |
| O13 | ALTA | ¿Cómo se evita la inyección de fórmulas? | **APROBADA (a) 2026-11-13:** apóstrofo delante de celdas de **texto libre** que empiezan con `= + - @ TAB CR`; columnas validadas (E.164, números, fechas, ids) intactas | (b) neutralizar todas las celdas (rompe `+549…` y negativos); (c) no neutralizar (el nombre de contacto lo escribe cualquiera en la reserva pública) |
| O14 | ALTA | ¿Cómo se manejan exportaciones grandes (R16)? | **APROBADA (a) 2026-11-13:** streaming desde la API con cursor del servidor (`yield_per` 500), transacción `REPEATABLE READ READ ONLY` y `statement_timeout` (D9) | (b) job en el worker que genera un archivo y deja un link (exige guardar datos de salud en reposo y servirlos); (c) JSON paginado que el navegador convierte a CSV (muchos pedidos, sin foto consistente) |
| O15 | Media | ¿Se limita el uso de la exportación? | **APROBADA (a) 2026-11-13:** una exportación en curso por usuario y 20 por hora (`EXPORT_MAX_POR_HORA`), con el limitador de C-15 (429); rango de fechas opcional | (b) sin límite; (c) rango obligatorio de 366 días como máximo (impide el respaldo completo de una vez) |
| O16 | Baja | ¿Retención/purga de la auditoría? | **APROBADA (a) 2026-11-13:** sin purga en C-13; se conserva indefinidamente. `[SUPUESTO / ABIERTO]` plazo legal a confirmar con la clínica (referencia: historia clínica, Ley 26.529, 10 años) | (b) trabajo de purga programado a N años (exige excepción al trigger de O4) |
| O17 | ALTA | ¿`LOGIN_FAILED` puede guardar el email intentado? | **APROBADA (a) 2026-11-13:** LOGIN_FAILED sin email: `entidad_id` NULL cuando la cuenta no existe (con cuenta, solo su id). Efecto en C-15: ninguno funcional; los contadores del límite usan la huella del email en Redis, no la auditoría, y ningún test de C-03/C-15 dependía del dato | (b) huella SHA-256 en `entidad_id`; (c) dejarlo (contradice R19 y el requisito de datos personales) |

## Auditoría de reglas de negocio (`spec-rules-auditor`, 2026-11-13, sobre la propuesta)

**Dictamen: OBSERVACIONES** (sin bloqueos; dos enmiendas de la KB quedan sujetas a O6/O7 y un supuesto abierto en O16).

| Regla | Descripción breve | Estado | Observación |
|---|---|---|---|
| RN-GL-01 | Toda acción de panel auditada (quién, qué, cuándo) | CUBIERTA | Registro en la transacción + contrato por ruta (D1–D3); brechas `POST /api/turnos` e iniciar Google cerradas (O10); IP en todos (O9); inmutable (O4). Spec `plataforma/auditoria` y deltas de `creacion-sin-solape` y `google-calendar` |
| RN-GL-02 | Exportación masiva tabular | CUBIERTA | Turnos, pacientes y cierres en CSV por streaming (spec `plataforma/exportacion-datos`) |
| US-011 CA-1 / US-012 CA-1 | Acciones auditadas / exporto turnos y pacientes | CUBIERTA con enmienda | Pacientes solo admin (O7) y auditoría solo admin (O6) son **más estrictos que la matriz de `03`**: se marcan como enmienda a aprobar; si se rechazan, rige (b) |
| Matriz RBAC (03) | Auditoría/exportación: recepción/admin; odontóloga — | CUBIERTA | Odontóloga 403 en exportación y auditoría (escenarios); "vale el permiso más amplio" en escenario de doble rol |
| RN-CL-03 | Lecturas/escrituras clínicas auditadas | NO AFECTADA / reforzada | Siguen igual; pasan por el helper único con la misma guarda |
| RN-CJ-03 | Día cerrado no cambia | NO AFECTADA | La exportación de cierres es de solo lectura (`READ ONLY`) |
| RN-TU-12 (C-12) | `deshacer_atendido` auditado | CUBIERTA | Tipo legible `deshacer_atendido` sin migrar datos (D5) |
| RN-SN-11 / RN-SN-04 | Rechazo de revisión y devoluciones | CUBIERTA | Tipos `rechazo_revision_sena`, `devolucion_sena`, `devolucion_excedente` |
| RN-TU-08 | El código de gestión es la credencial del paciente | CUBIERTA | `codigo_gestion` nunca se exporta ni audita (columnas D9, guarda D2) |
| R8 / R9 | `en_espera` no bloquea; ausente no reembolsa | NO AFECTADA | Sin cambios de estado |
| R3 / RN-GL-03 | 360 px | CUBIERTA | Escenarios de pantalla a 360 px + E2E |
| R4 / R6 / R14 | Timestamptz, Numeric, CHECK; FK indexada; migración reversible | CUBIERTA | CHECK de IP, índice por entidad, FK `RESTRICT` sobre índice existente, downgrade sin pérdida; Decimal en CSV |
| R13 / R15 | Type hints; Pydantic en el borde | CUBIERTA | `AuditoriaQuery`, `ExportQuery`, `AuditoriaPagina`, `LimiteSuperadoOut`; 200 `text/csv` declarado en OpenAPI |
| R16 | No bloquear el loop | CUBIERTA | Cursor async + lotes de 500; sin archivos en disco (O14) |
| R17 / R18 / R20 | Config por entorno; Compose; sin `.env` | CUBIERTA | `EXPORT_*` con defaults sin secretos |
| R19 / Ley 25.326 | Datos sintéticos; sin PII en logs/auditoría | CUBIERTA | Guarda ampliada (D2), texto buscado y DNI nunca auditados, CSV neutralizado, exportación auditada, datos sintéticos en todos los escenarios (`Lucía Ejemplo`, DNI `99xxxxxx`, `+54911000000xx`, IPs de documentación) |
| R7 | E2E de flujos | CUBIERTA | `datos.spec.ts` + suite completa |
| R1 / R2 / R21 | TS estricto; sin cascadas; frontends en `frontend/` | CUBIERTA | Usuarios y primera página en `Promise.all`; todo en `frontend/panel` |
| R11 / R12 | Sin commits; conventional commits | CUBIERTA | Workflow follow-up |

**Supuestos marcados:** `[SUPUESTO / ABIERTO]` O16 (plazo de retención); `[SUPUESTO]` volumen de una clínica (≤ 100 000 turnos) que justifica `Blob` en el navegador y sin BRIN.

**Observaciones corregidas en el acto:** (1) el catálogo de `CrudService` guardaba `nombre` del profesional, que la guarda única rechazaría: se agregó a D2 el filtrado de columnas de identidad y una tarea RED específica; (2) la exportación usaba la misma transacción para leer y auditar, incompatible con `READ ONLY`: se separó en dos sesiones (D9, paso 5).

**Terna de escenarios:** cada requisito ADDED de los seis deltas tiene Happy Path, Error de Negocio y Caso de Borde, deterministas y traducibles a pytest/Vitest/Playwright con reloj inyectado.

## Auditoría de reglas de negocio sobre el código y los specs finales (`spec-rules-auditor`, 2026-11-13)

**Dictamen: OBSERVACIONES (sin bloqueos).** Matriz de trazabilidad: RN-GL-01 (CUBIERTA: política por ruta + registro en la transacción + IP real + inmutabilidad), RN-GL-02 (CUBIERTA: CSV por streaming, auditado antes del primer byte, límites, neutralización), RN-TU-08 (CUBIERTA: `codigo_gestion` nunca se exporta ni audita), RN-CJ-03 (NO AFECTADA: export `READ ONLY`), R4/R6/R14 (CUBIERTA: migración 013 reversible, FK `RESTRICT` indexada, CHECK de IP, `set_config` en vez de SQL crudo), R15, R16, R17/R20 (`EXPORT_*` sin secretos), R19 (datos sintéticos; guarda ampliada), R3/R7 (E2E `datos.spec.ts` a 360 y 1280 px). Cada requisito nuevo tiene sus tres escenarios (esperado, error, borde) como tests con el nombre del escenario.

Observaciones:
1. **Corregida por O17 (aprobada 2026-11-13, opción a):** `LOGIN_FAILED` con un email inexistente guarda ese email en `entidad_id` (C-03/C-15). Contradice "Los registros no contienen ... email". Recomendado: `entidad_id = NULL` o huella SHA-256; requiere cambiar tests de C-15.
2. `GET /api/panel/auditoria` registra `entidad`/`entidad_id` que escribe el admin (texto libre); la guarda bloquea claves, no valores. Riesgo bajo (solo admin).
3. Desvío menor de D9: el CSV de turnos no trae `creado_en` porque `turno` no tiene esa columna (el spec no la exige).
4. D2 aplicado: el catálogo (`CrudService`) ya no audita `nombre` ni `matricula`, solo ids, valores no identificatorios y `campos`; se actualizó el test de C-04 que esperaba `nombre`.
5. Tipos extra del catálogo respecto de D5 (`reserva_publica`, `cancelacion_paciente`, etc.) para que las acciones históricas legibles no caigan en `otro`.
6. `[SUPUESTO / ABIERTO]` O16 (retención) sigue abierto.
