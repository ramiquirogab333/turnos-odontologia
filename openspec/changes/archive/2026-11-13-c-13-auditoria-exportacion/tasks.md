# Tasks: c-13-auditoria-exportacion

> **Governance CRÍTICO.** Las decisiones **O1–O16** de `design.md` fueron **APROBADAS (opción recomendada) el 2026-11-13**. Estas tareas siguen la opción recomendada; si alguna decisión cambia, se ajustan specs, diseño y tareas primero.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR: el test se escribe primero y falla por la razón correcta (no por un import roto). Cada requisito de los specs tiene sus tres escenarios (esperado, error de negocio, caso de borde) y los tests llevan el nombre del escenario. Datos 100 % sintéticos (R19): `recepcion@turnos.test`, `admin@turnos.test`, `dra.ficticia@turnos.test`, "Lucía Ejemplo" / "Mateo Prueba", DNI `99xxxxxx`, `+54911000000xx`, IPs de documentación (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`). Instantes con zona y reloj inyectado (R4), sin `sleep`. Nunca un dato personal en un assert de log ni en un registro de auditoría. Sin commits (R11).
>
> Skills a cargar antes de cada grupo: `postgresql-table-design` (grupo 2), `vercel-react-best-practices` y `frontend-design` (grupo 9), `playwright-cli` (grupo 10), `spec-rules-auditor` (11.3).

## 0. Aprobación y línea base

- [x] 0.1 Confirmar con el usuario la tabla O1–O16 de `design.md` y registrar la decisión final de cada fila (con fecha). Si alguna cambia, ajustar specs, diseño y estas tareas antes de seguir. Verificar: ninguna fila PENDIENTE y `openspec validate c-13-auditoria-exportacion --strict` pasa.
- [x] 0.2 Con `docker compose up -d postgres redis` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm test` + `npm run typecheck` en `frontend/panel`; registrar los conteos en el acta al final de este archivo. Si algo falla, frenar y reportarlo como falla previa.
- [x] 0.3 Verificar con `ls backend/src/alembic/versions` que `013` sigue libre (C-14 puede ir en paralelo) y, con una consulta de solo lectura, que no hay filas con `LENGTH(ip) > 45` en `registro_auditoria`; anotar ambos resultados en el acta.

## 1. Configuración (D10, O15)

- [x] 1.1 RED → GREEN: `backend/tests/test_settings_exportacion.py`: `EXPORT_MAX_POR_HORA` (default 20) y `EXPORT_TIMEOUT_SEGUNDOS` (default 300) rechazan `0`/`-1`/`abc` nombrando la variable. Implementar en `app/shared/settings.py`. Verificar en verde y que los `test_settings_*.py` existentes siguen en verde.
- [x] 1.2 `docker-compose.yml`: variables `EXPORT_*` con sus defaults en el backend (sin secretos, R17). Verificar: `docker compose config` válido.

## 2. Esquema y helper único (D2, D6, O4, O5) — specs `dominio/modelos-core`, `plataforma/auditoria`

- [x] 2.1 RED: `backend/tests/test_auditoria_migracion.py`: tras `upgrade head`, `UPDATE` y `DELETE` sobre `registro_auditoria` fallan con SQLSTATE `P0001`; la FK de usuario es `RESTRICT` (consulta a `pg_constraint`) y su índice existe (`pg_index`, R6); existe `(entidad, entidad_id, created_at)`; una IP de 46 caracteres es rechazada; borrar un usuario con registros es rechazado. Verificar que falla porque la migración no existe.
- [x] 2.2 GREEN: `backend/src/alembic/versions/013_auditoria_exportacion.py` (`down_revision = "012_sesion_panel"`) y modelo `RegistroAuditoria` actualizado (FK `RESTRICT`, `CheckConstraint`, `Index`); `backend/tests/conftest.py` limpia `registro_auditoria` con `TRUNCATE ... RESTART IDENTITY CASCADE` antes de los demás `DELETE`. Verificar: 2.1 en verde, `test_models_metadata.py` en verde, reversibilidad con `alembic_helpers` (`downgrade -1` restaura `SET NULL` y quita trigger/índice/CHECK sin perder filas; `upgrade head` vuelve) y que los tests de migración que fijaban `012_sesion_panel` como head se actualizan a `013`.
- [x] 2.3 RED: `backend/tests/test_plataforma_auditoria.py` (unit + integración): `registrar` agrega en la transacción del caller (rollback → sin fila); claves prohibidas en primer nivel y anidadas (`telefono`, `dni` en lista, `q`, `codigo_gestion`, `token`) → `DatosProhibidosEnAuditoriaError` sin fila; `ip=AUTO` sin pedido → `None`. Y un test del catálogo: crear un `profesional` audita ids y `campos`, sin `nombre`. Verificar que fallan.
- [x] 2.4 GREEN: `app/plataforma/__init__.py` + `app/plataforma/auditoria.py` (`registrar`, `CLAVES_PROHIBIDAS` ampliada, `contexto_auditoria`); `app/pacientes/auditoria.py` pasa a reexportar. Verificar 2.3 en verde.
- [x] 2.5 REFACTOR (sin cambio de comportamiento): `pagos.service._auditar`, `auth.router._audit`, `catalogo.service.CrudService._audit` (con el filtrado de identidad de D2), `gcal.oauth._auditar`, `gcal.conflictos._auditar`, `notificaciones.panel._auditar` y los `session.add(RegistroAuditoria(...))` de `panel/service.py`, `public/service.py`, `gestion/service.py`, `pagos/barrido.py`, `panel/usuarios.py`, `gcal/sincronizacion.py` delegan en `registrar` con los mismos valores. Verificar: `grep -rn "RegistroAuditoria(" backend/src/app` solo encuentra `app/plataforma/auditoria.py` y el modelo, y la suite completa vuelve al conteo de 0.2 (más los tests nuevos).
- [x] 2.6 Documentar en `knowledge-base/04_modelo_de_datos.md` la entidad `RegistroAuditoria` real (columnas, inmutabilidad, FK `RESTRICT`, índices). Verificar que coincide con la migración.

## 3. IP real en todo pedido autenticado (D4, O9) — spec `plataforma/auditoria`

- [x] 3.1 RED: `backend/tests/test_auditoria_ip_contexto_integration.py`: los tres escenarios de "Los registros de pedidos autenticados guardan la IP real" (devolución de seña desde `203.0.113.20`; `X-Forwarded-For` ignorado sin proxy de confianza al marcar ausente; barrido del worker sin IP) y dos pedidos concurrentes con IPs distintas (`ASGITransport(client=...)` + `asyncio.gather`) que graban cada uno la suya. Verificar que fallan.
- [x] 3.2 GREEN: `get_current_user` recibe `Request` y fija `contexto_auditoria` con `ip_cliente`; `registrar(ip=AUTO)` lo usa; los trabajos del sistema pasan `ip=None`. Verificar 3.1 en verde y `test_auditoria_ip_integration.py` (C-15) en verde.

## 4. Catálogo de tipos y política por ruta (D3, D5, O1, O5) — spec `plataforma/auditoria`

- [x] 4.1 RED: `backend/tests/test_tipos_auditoria.py` (unit): cada fila de la tabla de D5 da su `tipo` y etiqueta (incluidas las seis acciones de C-12), un `UPDATE` de `configuracion_sena` sin origen da `otro` con la acción original, y el predicado de filtro de cada tipo es el esperado. Verificar que falla.
- [x] 4.2 GREEN: `app/plataforma/tipos_auditoria.py`. Verificar 4.1 en verde.
- [x] 4.3 RED: `backend/tests/test_politica_auditoria_contrato.py`: los tres escenarios de "Toda ruta autenticada declara su política" (todas con política; ruta nueva sin política falla nombrándola —se prueba con una app de prueba que monta una ruta extra—; `exenta` sin motivo falla) y que toda acción declarada existe en el catálogo de 4.2. Verificar que falla.
- [x] 4.4 GREEN: `app/plataforma/politica_auditoria.py` con la tabla completa de D3 (incluidas las rutas nuevas de los grupos 5–8, declaradas a medida que existen). Verificar 4.3 en verde.

## 5. Cierre de brechas: lecturas de pacientes, alta interna, Google (D8, O2, O10) — specs `pacientes/registro-paciente`, `turnos/creacion-sin-solape`, `integraciones/google-calendar`

- [x] 5.1 RED: `backend/tests/test_pacientes_lecturas_auditadas_integration.py`: los escenarios de "Las lecturas de datos de pacientes quedan auditadas" (listado con `q=lucia` sin `lucia` en el registro; 403/422 sin rastro; DNI inexistente con `encontrados: 0` sin DNI) y de "Sin rastro no se entregan datos del paciente" (lectura normal; `registrar` que lanza → 500 sin datos; 404 sin rastro). Verificar que fallan.
- [x] 5.2 GREEN: `pacientes/listado.py` y `pacientes/service.py` auditan `lectura_listado_pacientes`, `busqueda_paciente_dni`, `lectura_paciente` con `commit` antes de responder. Verificar 5.1 en verde y `test_pacientes_listado_integration.py` en verde.
- [x] 5.3 RED → GREEN: `backend/tests/test_turnos_alta_auditada_integration.py`: alta interna auditada, alta con solape sin registro, dos altas simultáneas → un 201, un 409 y un solo registro. Implementar `alta_turno_interna` en `app/turnos/`. Verificar en verde y que `creacion-sin-solape` (C-01) sigue en verde.
- [x] 5.4 RED → GREEN: en `test_gcal_oauth_integration.py`: iniciar auditado sin URL ni `state`; 409 `conexion_activa` y 503 `gcal_no_configurado` sin registro. Implementar `inicio_conexion_gcal` en `gcal/oauth.py`. Verificar en verde.

## 6. Consulta de la auditoría (D7, O6) — spec `plataforma/auditoria`

- [x] 6.1 RED: `backend/tests/test_auditoria_cursor.py` (unit): codificar/decodificar el cursor; cursor ilegible o manipulado → error; `AuditoriaQuery` (default 7 días, `desde > hasta` y 400 días → error, `tipo` fuera del enum → error con la lista). Verificar que falla.
- [x] 6.2 RED: `backend/tests/test_auditoria_consulta_integration.py`: "Consulta filtrada" (historia del turno 501 con tres tipos en orden; rango inválido 422; keyset estable con 3 inserciones entre páginas), "Solo el admin consulta" (admin 200 + `lectura_auditoria`; recepción y odontóloga 403 sin `lectura_auditoria`; doble rol 200), "Tipos legibles" (seis acciones de C-12; `tipo=inventado` 422; histórico `otro` sin cambiar la fila) y que la consulta usa un único `SELECT` con `JOIN` a usuario (contador de sentencias). Verificar que fallan.
- [x] 6.3 GREEN: `require_admin` en `app/auth/rbac.py`, esquemas en `app/plataforma/schemas.py` (`extra="forbid"`), `app/plataforma/router_auditoria.py` registrado en `app/main.py`, política en 4.4. Verificar 6.1–6.2 en verde y la ruta en OpenAPI con 401/403/422.
- [x] 6.4 RED → GREEN: `GET /api/panel/usuarios` (solo admin, `{id, nombre_completo}`, sin email) con sus tres escenarios (admin 200; recepción 403; usuario inactivo incluido y marcado). Verificar en verde (O3; se omite si O3 elige (c)).

## 7. Exportación: núcleo puro (D9, O11–O13) — spec `plataforma/exportacion-datos`

- [x] 7.1 RED: `backend/tests/test_exportacion_csv.py` (unit): `neutralizar_celda` (los seis prefijos, texto normal, vacío); formateo de fila (Decimal con 2 decimales, instante en `-03:00`, fecha, booleanos, nulos); comillas/comas/saltos de línea RFC 4180; BOM solo en el primer chunk; CRLF; descriptores de columnas de turnos, pacientes y cierres en el orden de D9, sin `codigo_gestion`, y con el teléfono E.164 fuera de `texto_libre`. Verificar que falla.
- [x] 7.2 GREEN: `app/plataforma/exportacion.py` (descriptores, `neutralizar_celda`, escritor por lotes). Verificar 7.1 en verde.
- [x] 7.3 REFACTOR: extraer el formateo de valores compartido con la consulta de auditoría (zona de la clínica, Decimal) si hay duplicación. Verificar 6.x y 7.x en verde.

## 8. Exportación: endpoint, streaming, auditoría y límites (D9, D10, O7, O8, O14, O15) — spec `plataforma/exportacion-datos`

- [x] 8.1 RED: `backend/tests/test_exportacion_integration.py`: los tres escenarios de turnos (semana con 3 filas y sin código de gestión; `entidad=fichas`/`formato=xlsx` 422; rango vacío solo encabezado), pacientes (activos; recepción 403; `incluir_inactivos`), cierres (totales exactos; odontóloga 403; anulado + vigente), formato (motivo con comas y comillas; acentos; cabeceras `Content-Disposition`/`no-store`) y fórmulas (`=HYPERLINK`, cuatro prefijos, teléfono intacto). Verificar que fallan.
- [x] 8.2 RED: en el mismo archivo, "Cada exportación queda auditada antes de enviar datos" (registro con IP, entidad, filtros y filas, sin nombres ni DNI; 403 sin registro; desconexión a mitad: el registro existe y la conexión y el lease se liberan —cerrando el iterador del cuerpo a mitad—; `registrar` que falla → 500 y ningún byte de CSV). Verificar que fallan.
- [x] 8.3 GREEN: `app/plataforma/router_exportacion.py` (`ExportQuery`, permisos O7, orden de operaciones de D9 con conexión `REPEATABLE READ READ ONLY` + `statement_timeout`, `count(*)` en la misma foto, auditoría en sesión aparte, `StreamingResponse` con `yield_per=500` y `finally`), registrado en `app/main.py`, política en 4.4, OpenAPI con 200 `text/csv`, 403, 422, 429, 500. Verificar 8.1–8.2 en verde.
- [x] 8.4 RED → GREEN: "La exportación grande se entrega por partes": foto consistente (un `UPDATE` concurrente de estado entre lotes no aparece; sin duplicados ni faltantes), otra petición (`GET /api/panel/agenda`) responde mientras el stream está abierto, y 100 000 turnos sintéticos con pico de `tracemalloc` bajo un umbral fijo (marcado `slow`, corre en CI). Verificar en verde.
- [x] 8.5 RED → GREEN: "Límite de exportaciones por usuario" con el `LimitadorEnMemoria` y reloj inyectado: 3 seguidas 200; la 21 en la hora → 429 con `Retry-After` y sin registro; segunda simultánea → 429 y la primera termina; al terminar se libera el lease. Implementar D10. Verificar en verde y que con `LimitadorTolerante` y Redis caído se exporta igual (fail-open de C-15).

## 9. Panel: sección "Datos" (D11, O3, O6, O7) — specs `plataforma/auditoria`, `plataforma/exportacion-datos`

- [x] 9.1 RED: Vitest de funciones puras en `frontend/panel/src/lib/datos.test.ts`: `opcionesSegunRol` (recepción: turnos y cierres; admin: + pacientes; odontóloga: ninguna), `parametrosExportacion` (rango opcional, fechas locales), `nombreArchivo` desde `Content-Disposition` (con y sin cabecera), `etiquetaActor` (usuario / "Sistema / paciente"), y mensaje de 429 con `minutosDesdeRetryAfter`. Verificar que fallan.
- [x] 9.2 GREEN: `frontend/panel/src/lib/datos.ts` y funciones de `lib/api.ts` (`descargarExportacion` con `fetch` autenticado + `Blob`, `consultarAuditoria`, `listarUsuarios`), tipos en `lib/tipos.ts` sin `any` (R1). Verificar 9.1 en verde y `npm run typecheck`.
- [x] 9.3 RED → GREEN: componentes `Datos.tsx`, `Exportar.tsx`, `Auditoria.tsx` con sus tests (pestañas según rol; descarga ok vuelve a habilitar el botón; 403 y 429 con sus mensajes; "Ver más" con cursor; vacío "No hay registros para estos filtros"; usuarios y primera página en `Promise.all`, R2), y la sección `#/datos` en `lib/ruta.ts`/`Navegacion.tsx` (recepción y admin; odontóloga no). Verificar en verde, `npm run lint` y que a 360 px no hay desplazamiento horizontal (test de estilos o revisión en E2E 10.2).

## 10. E2E Playwright (R3, R7)

- [x] 10.1 CI y Compose E2E: los jobs `e2e-panel` exportan `EXPORT_MAX_POR_HORA=1000`. Verificar que `docker compose --profile e2e up -d --wait` levanta todo sano.
- [x] 10.2 `frontend/panel/e2e/datos.spec.ts` a 360 px: (a) recepción descarga turnos de la semana (`waitForEvent('download')`, nombre `turnos_<fecha>.csv`, BOM y encabezado esperados) y no ve "Pacientes" ni la pestaña "Auditoría"; (b) admin exporta pacientes y, en "Auditoría", filtra por tipo `exportacion` y ve su registro; (c) 429 simulado con `page.route` y `Retry-After: 600` muestra el mensaje de 10 minutos; (d) odontóloga no ve la sección. Verificar en verde.
- [x] 10.3 Correr las suites E2E completas de ambos frontends (C-05…C-15) con los umbrales E2E. Verificar: todo en verde, sin tests saltados nuevos.

## 11. Documentación, auditoría y cierre

- [x] 11.1 Actualizar `knowledge-base/03_actores_y_roles.md` (quién consulta la auditoría y quién exporta qué, según O6/O7), `knowledge-base/05_reglas_de_negocio.md` (precisiones de RN-GL-01/02: política por ruta, inmutabilidad, exportación auditada), `knowledge-base/06_funcionalidades.md` (US-011/US-012 con lo aprobado), `knowledge-base/08_arquitectura_propuesta.md` (`EXPORT_*`, `app/plataforma/`) y el README (columnas de cada CSV, cómo abrirlo en Excel, aviso de datos personales). Verificar coherencia con specs y código.
- [x] 11.2 Actualizar `CHANGES.md` §C-13 (scope final, migración `013`, seguimientos: retención O16, rol de BD O4 b). Verificar coherencia con los specs.
- [x] 11.3 Correr `spec-rules-auditor` sobre el código y los specs finales contra `05_reglas_de_negocio.md` y `AGENTS.md`; registrar el dictamen en `design.md` y corregir lo observado. Verificar dictamen APROBADO u OBSERVACIONES sin bloqueos.
- [x] 11.4 Verificación final: `python -m pytest -q` (backend), `npm test` + `npm run typecheck` + `npm run lint` + `npm run build` (panel), E2E completos, `openspec validate c-13-auditoria-exportacion --strict`, y `grep` de `TRUNCATE` fuera de tests y migraciones sin resultados. Registrar conteos en el acta.

- [x] 11.5 (O17) `LOGIN_FAILED` sin email: RED `backend/tests/test_login_fallido_sin_email_integration.py` (email inexistente → `entidad_id` NULL y sin email en ninguna columna; usuaria existente conserva su id; bloqueo 429 intacto) → GREEN en `auth/router.py`. Verificar tests de auth, límite de login y auditoría en verde.

## Workflow follow-up

- Archivar con `/opsx:archive c-13-auditoria-exportacion` cuando el usuario lo apruebe y marcar `[x]` C-13 en `CHANGES.md`.
- Sin commits ni push salvo pedido explícito (R11); commits en conventional commits (R12).

## Acta

- **Aprobación:** O1–O16 aprobadas por el usuario el 2026-11-13 (opción recomendada); O16 sigue como supuesto abierto.
- **Migración:** `013` libre (última era `012_sesion_panel`); filas con `LENGTH(ip) > 45`: ninguna (la migración aplicó el CHECK sin error).
- **Línea base (antes):** backend 702 passed antes de la primera falla flaky (corrida con `-x`; el conteo completo se perdió por una corrida concurrente); panel Vitest 424, paciente Vitest 211, typecheck limpio.
- **Final (después):** backend 2170 passed, 6 skipped, 0 fallas (con el worker de Docker detenido; con el worker activo hay 1-2 fallas flaky de Google Calendar que varían por corrida); panel Vitest 500 (typecheck, lint y build limpios), paciente Vitest 211; E2E panel 88 passed + 2 skipped previos (incluye `datos.spec.ts`, 8 en 360 y 1280 px); E2E paciente 26 passed; `openspec validate --strict` válido; sin `TRUNCATE` fuera de tests y migraciones.
