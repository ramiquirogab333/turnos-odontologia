# Tasks: c-10-google-calendar-sync

> **Governance ALTO.** Las decisiones **O1–O20** de `design.md` fueron **APROBADAS por el usuario el 2026-11-12** (opción recomendada en todas). Estas tareas las siguen.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR: el test se escribe primero y falla por la razón correcta (no por un import roto). Cada requisito de los specs tiene sus tres escenarios (esperado, error de negocio, caso de borde) y los tests llevan el nombre del escenario. Datos 100 % sintéticos (R19): "Paciente Ficticio", "Dra. Ana Prueba", `ana.prueba@example.com`, teléfonos `+54911000000xx`, tokens `token-sintetico-NNN`. Instantes siempre con zona (R4). Nunca un token en un assert de log ni en un snapshot. Sin commits (R11).
>
> Skills a cargar antes de cada grupo: `postgresql-table-design` (grupo 2), `vercel-react-best-practices` y `frontend-design` (grupo 12), `playwright-cli` (grupo 13), `spec-rules-auditor` (14.4). `gws-calendar-agenda` NO sirve para esta integración (solo lectura): no usarla.

## 0. Aprobación y línea base

- [x] 0.1 Confirmar con el usuario la tabla O1–O20 de `design.md` y registrar la decisión final de cada fila (con fecha). Si alguna cambia, ajustar specs, diseño y estas tareas antes de seguir. Verificar: ninguna fila sin decisión y `openspec validate c-10-google-calendar-sync --strict` pasa.
- [x] 0.2 Con `docker compose up -d postgres` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm test` + `npm run typecheck` en `frontend-paciente/` y `frontend-panel/`; registrar los conteos en el acta al final de este archivo. Si algo falla, frenar y reportarlo como falla previa.
- [x] 0.3 Verificar con `ls backend/src/alembic/versions` que `011` sigue libre (C-14/C-15 pueden ir en paralelo); si no, usar el siguiente número y anotarlo en el acta.

## 1. Dependencias y configuración (D10, O1)

- [x] 1.1 Fijar `cryptography` en `backend/requirements.txt` en una versión estable verificada con `pip install --dry-run -r requirements.txt`. Verificar: resuelve sin conflictos y `python -c "from cryptography.fernet import Fernet"` funciona.
- [x] 1.2 RED → GREEN: en `backend/tests/test_settings_gcal.py`, tests de `Settings` para `GCAL_CLIENT_ID`, `GCAL_CLIENT_SECRET` (`SecretStr`), `GCAL_REDIRECT_URI`, `GCAL_TOKEN_CLAVE` (obligatoria y Fernet válida si hay `GCAL_CLIENT_ID`), `GCAL_SYNC_HABILITADO` (default `true`), `GCAL_SYNC_INTERVALO_SEGUNDOS` (default 60, rechaza `0`/`abc`), `GCAL_HORIZONTE_DIAS` (default 60, 1–365), `PUBLIC_PANEL_URL`, y `GCAL_OAUTH_BASE_URL`/`GCAL_API_BASE_URL` distintos de Google solo con `APP_ENV ∈ {test, e2e}`; propiedad `gcal_configurado`. El error nunca muestra un secreto. Implementar en `app/shared/settings.py`. Verificar en verde y que `test_settings_*.py` existentes siguen en verde.
- [x] 1.3 Agregar las variables `GCAL_*` y `PUBLIC_PANEL_URL` a `backend` y `worker` en `docker-compose.yml`, vacías por defecto (sin secretos, R17). Verificar: `docker compose config` es válido y el backend arranca sin ellas.

## 2. Esquema: migración `011_google_calendar` (D2) — spec `integraciones/google-calendar`

- [x] 2.1 RED: `backend/tests/test_gcal_migracion.py`: tras `upgrade head` existen `gcal_conexion`, `evento_calendar` y `gcal_conflicto`; instantes `timestamptz` (R4); cada FK con índice cuyo prefijo es la FK (consulta a `pg_index`, R6); `CHECK` de estados, orígenes, tipos, resoluciones y largos. Verificar que falla porque la migración no existe.
- [x] 2.2 RED: invariantes vía ORM: segunda conexión de la misma profesional → rechazada; `activa` sin refresh token → rechazada; dos eventos vigentes del mismo turno y conexión → rechazado, uno `borrado` + uno vigente → aceptado; `origen = 'google'` con `turno_id` → rechazado; dos conflictos abiertos del mismo tipo y par → rechazado; `resuelto` sin `resolucion` → rechazado; `fin <= inicio` → rechazado.
- [x] 2.3 GREEN: `backend/src/alembic/versions/011_google_calendar.py` (`down_revision = "010_recordatorios"`, índice GiST parcial de franjas ajenas, sin SQL crudo fuera de la migración, R14) y modelos en `app/integraciones/gcal/models.py`, registrados en `app/models/__init__.py` y en la limpieza de `backend/tests/conftest.py`. Verificar: 2.1–2.2 en verde y `test_models_metadata.py` en verde.
- [x] 2.4 RED → GREEN: reversibilidad con `alembic_helpers`: `downgrade -1` borra las tablas e índices y `upgrade head` vuelve a pasar. Verificar en verde.
- [x] 2.5 Documentar en `knowledge-base/04_modelo_de_datos.md` §EventoCalendar (y la línea del ERD) las tres tablas, el vínculo vigente único (O16) y que de un evento ajeno solo se guardan horario y ocupación (O19). Verificar que coincide con la migración.

## 3. Piezas puras: contenido del evento y cifrado (D5, O1, O8, O17)

- [x] 3.1 RED: `backend/tests/test_gcal_contenido.py` (sin base): requisito "El evento no identifica al paciente" (título "Turno · Limpieza", sillón y enlace en la descripción, ni nombre ni teléfono ni código en ningún campo; tratamiento renombrado; turno interno sin código), hora con `APP_TZ`, `extendedProperties.private`, id determinista en base32hex válido para Google (5–1024 caracteres, alfabeto `a-v0-9`) distinto por generación, y hash de contenido estable que cambia con horario o título. Verificar que falla por falta de `app.integraciones.gcal.contenido`.
- [x] 3.2 GREEN + TRIANGULAR + REFACTOR: implementar `contenido.py` (puro); sumar un caso con otro tratamiento, otro sillón y un horario que cruza la medianoche UTC. Verificar en verde.
- [x] 3.3 RED → GREEN: `backend/tests/test_gcal_cifrado.py`: ida y vuelta, texto cifrado distinto del original y sin el token, clave equivocada → error tipado `TokenIlegible` (sin el token en el mensaje). Implementar `cifrado.py`. Verificar en verde.

## 4. Puerto del proveedor, falso en memoria y adaptador HTTP (D1, D4, O15)

- [x] 4.1 RED: `backend/tests/test_gcal_proveedor_falso.py`: contrato del `ProveedorCalendario` sobre el falso en memoria: insertar con id propio (segunda vez → `EventoDuplicado`), patch con `etag` (viejo → `EtagDesactualizado`), delete (ya borrado → `EventoInexistente`), listar incremental con `syncToken` (solo cambios, borrados con `status = cancelled`, token inválido → `SyncTokenVencido`), renovar token (revocado → `AccesoRevocado`), fallas inyectables `ErrorTransitorio`. Verificar que falla por falta del módulo.
- [x] 4.2 GREEN: `proveedor.py` (Protocol + tipos + errores) y `proveedor_falso.py`. Verificar 4.1 en verde.
- [x] 4.3 RED → GREEN: `backend/tests/test_gcal_proveedor_http.py` con `httpx.MockTransport` y respuestas de ejemplo de la documentación de Calendar v3: el adaptador `proveedor_http.py` (asíncrono, timeout 10 s, R16) arma URL, cabeceras (`Authorization`, `If-Match`) y cuerpo correctos, pagina con `nextPageToken`, devuelve `nextSyncToken`, y traduce 409→`EventoDuplicado`, 410→`SyncTokenVencido`/`EventoInexistente`, 412→`EtagDesactualizado`, 404, 429/5xx/timeout→`ErrorTransitorio`, `invalid_grant`→`AccesoRevocado`. Verificar en verde y que ningún mensaje de error contiene el token.

## 5. Conexión OAuth (D3, O1, O2, O3, O14) — requisitos de conexión, callback, desconexión y estado

- [x] 5.1 RED: `backend/tests/test_gcal_oauth_integration.py`: requisito "La profesional conecta su propio Google Calendar" (iniciar → URL con scope, `state`, `code_challenge`, conexión `pendiente`; recepción/admin → 403, sin sesión → 401; con conexión activa → 409 `conexion_activa`; sin credenciales → 503 `gcal_no_configurado`). Verificar que falla por falta del router.
- [x] 5.2 RED: requisito "El regreso de Google guarda la conexión con los tokens cifrados" con el canje simulado por `MockTransport`: éxito → `activa`, tokens cifrados (la columna no contiene el token), `cuenta_email`, auditoría sin tokens, 303 a `#/google-calendar?resultado=conectado`; `state` vencido (11 min), usado o adulterado → 303 `error_autorizacion` sin canje; `error=access_denied` → `desconectada`, `permiso_denegado`. Verificar que falla.
- [x] 5.3 GREEN: `oauth.py`, `schemas.py` y `router.py` (`/api/panel/google-calendar`, Pydantic in/out, R15) con `iniciar` y `callback`; router registrado en `app/main.py`. Verificar 5.1–5.2 en verde.
- [x] 5.4 RED → GREEN: requisito "Desconectar Google Calendar": la propia profesional → 204, sin tokens, eventos `desvinculado` (siguen en el falso), franjas borradas, conflictos cerrados, auditoría; otra odontóloga → 403; admin → 204; revocación con falla de red → igual `desconectada`, log sin token. Verificar en verde.
- [x] 5.5 RED → GREEN: requisito "Estado de las conexiones según el rol": recepción ve todas con `conflictos_abiertos`, la odontóloga solo la suya, 401 sin sesión, `revocada` con su indicación, `sin_conectar` para profesionales sin fila. Verificar en verde.

## 6. Push por reconciliación (D5, O4, O6, O7, O9, O17) — requisitos de eventos del sistema

- [x] 6.1 RED: `backend/tests/test_gcal_push_integration.py` con `ahora` fijo y el falso en memoria: requisito "Solo los turnos que bloquean agenda tienen evento en Google" (acreditación de seña, alta manual sin seña, reserva exenta y confirmación → un evento; `en_espera` y vencido → ninguno; horizonte 59/61 días). Verificar que falla por falta de `reconciliacion.py`.
- [x] 6.2 GREEN: `reconciliacion.py` (`reconciliar_push(session, conexion, proveedor, ahora, horizonte)`, ORM sin SQL crudo). Verificar 6.1 en verde.
- [x] 6.3 RED → GREEN: requisito "Cancelar borra el evento y reprogramar lo mueve" (cancelación → `borrado`; reprogramación con el aviso perdido → mismo evento movido; reprogramado fuera del horizonte → igual se mueve; cancelado con evento ya borrado en Google → sin llamadas). Verificar en verde.
- [x] 6.4 RED → GREEN: requisito "Ausente y atendido conservan el evento" (atendido, ausente y deshacer atendido → sin llamadas al proveedor y un único evento). Verificar en verde.
- [x] 6.5 RED → GREEN: requisito "La sincronización no duplica eventos" (insert hecho y vínculo no guardado → 409 → vínculo sin duplicar; dos sesiones concurrentes con el advisory lock por conexión → un evento; restaurar un borrado → generación + 1 y vínculo viejo `borrado`). Verificar en verde.
- [x] 6.6 RED → GREEN: con conflicto abierto `movido_en_google`/`borrado_en_google` o vínculo `desvinculado` el push no escribe ese evento; `412` en el patch → no escribe y no falla el ciclo. Verificar en verde.

## 7. Pull incremental y franjas ocupadas (D4, O5, O19) — requisito "Los eventos ocupados de Google se traen como franjas ocupadas"

- [x] 7.1 RED: `backend/tests/test_gcal_pull_integration.py`: evento ajeno `opaque` → franja sin título (la tabla no tiene dónde guardarlo y el modelo no lo recibe); `transparent`, cancelado o rechazado por la profesional → no ocupa; movido o borrado → franja movida o liberada; primera lectura sin `syncToken` acotada al horizonte; `syncToken` guardado tras paginar; 410 → relectura completa sin duplicados. Verificar que falla por falta de `pull.py`.
- [x] 7.2 GREEN + REFACTOR: implementar `pull.py`. Verificar 7.1 en verde.

## 8. Conflictos: detección, cierre automático y resolución manual (D6, O9, O11, O12, O18, O20)

- [x] 8.1 RED: `backend/tests/test_gcal_conflictos_integration.py`: requisito "Un cambio en Google nunca modifica un turno" (movido → `movido_en_google` con ambos horarios y el turno igual; borrado → `borrado_en_google` sin recrear; solo título → sin conflicto; cambio de los dos lados → conflicto, sin escritura). Verificar que falla.
- [x] 8.2 RED: requisito "Conflicto por superposición con un evento ocupado de Google" (seña acreditada sobre franja → `solapa_evento_externo`; `en_espera` → sin conflicto; intervalos que se tocan en el borde → sin conflicto) y cierre automático O20 (turno cancelado → `turno_cancelado`; franja movida fuera o pasada a libre → `solape_desaparecido`; evento devuelto en Google al horario del turno → `solape_desaparecido`). Verificar que falla.
- [x] 8.3 GREEN: `conflictos.py` integrado en `pull.py`/`reconciliacion.py`. Verificar 8.1–8.2 en verde.
- [x] 8.4 RED → GREEN: requisitos "Resolución manual de conflictos con criterio visible" y "Desvincular un turno del calendario" sobre `GET /conflictos` y `POST /conflictos/{id}/resolver`: listado por rol con `acciones` por tipo; `restaurar_en_google` → el ciclo siguiente devuelve el evento; `desvincular` → ningún ciclo posterior lo toca; `revisado` en solape y conflicto nuevo si la superposición vuelve con otra franja; 422 `accion_no_valida`, 403 odontóloga, 401, 404, 409 `conflicto_cerrado`; auditoría sin PII. Verificar en verde.

## 9. Trabajo `gcal_sync`, errores de Google y notificador (D4, D7, O4, O13) — specs `integraciones/google-calendar` y `plataforma/trabajos-programados`

- [x] 9.1 RED: `backend/tests/test_gcal_sincronizacion_integration.py`: requisito "Errores de Google sin perder cambios" (503 dos ciclos → backoff 1 y 5 min y luego el evento se crea; 429 en una conexión → las otras siguen; log sin PII ni tokens) y requisito "Token revocado deja de sincronizar sin tocar turnos" (`invalid_grant` → `revocada` + auditoría; ciclos siguientes sin llamadas; reconectar crea los pendientes sin duplicar); token ilegible → `revocada`. Verificar que falla por falta de `sincronizacion.py`.
- [x] 9.2 GREEN: `sincronizacion.py` con `sincronizar_calendarios(session_factory, proveedor, ahora) -> int` (por conexión: lock → token → pull → push → conflictos; error de una conexión no corta las demás). Verificar 9.1 en verde.
- [x] 9.3 RED → GREEN: requisitos de `plataforma/trabajos-programados`: `trabajos_programados` registra `gcal_sync` con su intervalo solo si `GCAL_SYNC_HABILITADO` y `gcal_configurado`; sin `GCAL_CLIENT_SECRET` no lo registra, avisa sin secreto y los otros trabajos siguen; dos ejecuciones concurrentes saltean la conexión tomada; un ciclo que excede el intervalo no duplica. Implementar en `app/jobs/registro.py` (y el proveedor HTTP real en el worker). Verificar en verde y `test_jobs_*.py` existentes en verde.
- [x] 9.4 RED → GREEN: requisito "La API nunca llama a Google": `NotificadorCalendario` marca `pendiente` y limpia el backoff de la conexión con una sola sesión; `get_notificador` devuelve el compuesto con recordatorios y calendario; cancelar/reprogramar con el proveedor que lanza error → 200 en tiempo normal (el proveedor no se llama desde la API); notificador que falla → la operación igual responde 200 y el ciclo corrige; profesional sin conexión → nada. Verificar en verde y `test_gestion_*` y `test_recordatorios_*` existentes en verde.

## 10. Disponibilidad, alta manual y agenda (D8, D9, O10, O19) — deltas `turnos/*`

- [x] 10.1 RED: `backend/tests/test_gcal_disponibilidad_integration.py`: requisito de `turnos/reserva-publica` (15:00/15:30 fuera y 14:30/16:00 dentro; `POST` a las 15:00 → 409 `motivo = profesional` con alternativas sin crear turno; `revocada` sigue excluyendo, `desconectada` no) y de `turnos/gestion-paciente` (reprogramar a 16:00 → ok; a 15:30 → 409 con alternativas; borde `[15:00, 16:00)`). Verificar que falla.
- [x] 10.2 GREEN: sumar las franjas en `app/public/service._cargar_bloqueos` como ocupación de profesional (una consulta, índice GiST). Verificar 10.1 en verde y `test_public_*`, `test_gestion_*` y `test_sena_*` existentes en verde.
- [x] 10.3 RED → GREEN: requisito de `turnos/gestion-panel`: alta manual sobre franja → 201 con `aviso_google_calendar = true` y conflicto tras el ciclo; sin franja o sin conexión → `false`. Implementar en `app/panel/service.py`/`schemas.py`. Verificar en verde y `test_panel_*` existentes en verde.
- [x] 10.4 RED → GREEN: requisitos de `turnos/agenda-panel`: `ocupados_google` con alcance por rol (la usuaria de la 8 no ve las de la 7); `calendario.estado` y `conflicto_abierto` por turno (`en_espera` → `sin_evento`); los campos existentes no cambian (snapshot del esquema anterior). Verificar en verde.

## 11. Servidor falso de Google, Compose y CI (D11, O15)

- [x] 11.1 RED → GREEN: `backend/tests/test_gcal_servidor_falso.py` con `httpx.ASGITransport`: el servidor falso solo arranca con `APP_ENV=e2e`; `/o/oauth2/v2/auth` redirige al `redirect_uri` con `code` y el `state` recibido; `/token` canjea y renueva; eventos con `syncToken`, `etag`, 409 por id repetido; `/_control/*` mueve, borra, crea un ocupado, fuerza 503 o `invalid_grant`. El adaptador HTTP real (grupo 4) pasa su suite contra este servidor. Implementar `servidor_falso.py`. Verificar en verde.
- [x] 11.2 Agregar a `docker-compose.yml` el servicio `gcal-falso` (misma imagen del backend, `profiles: ["e2e"]`, puerto interno 8090, healthcheck HTTP, `APP_ENV=e2e`). Verificar: `docker compose --profile e2e up -d --wait gcal-falso` lo deja `healthy` y `docker compose up -d` sin perfil no lo levanta.
- [x] 11.3 Actualizar `.github/workflows/ci.yml`: los jobs `e2e` y `e2e-panel` levantan `postgres redis gcal-falso` y luego `backend worker` con `GCAL_SYNC_INTERVALO_SEGUNDOS=3`, `GCAL_*_BASE_URL=http://gcal-falso:8090`, `GCAL_TOKEN_CLAVE` generada en el job y credenciales sintéticas; los logs de `gcal-falso` se vuelcan al fallar. Verificar: el YAML es válido (`docker compose config` y lint del workflow) y el job de pytest no necesita el falso.

## 12. Panel: sección Google Calendar y agenda (D9, O11, O12) — R1, R2, R3

- [x] 12.1 RED → GREEN: `frontend-panel/src/lib/api.gcal.test.ts`: cliente tipado (TS estricto, sin `any`, R1) para conexiones, iniciar, desconectar, conflictos y resolver, con guardas de tipos para las respuestas y los errores 403/409/422/503. Implementar en `src/lib/api.ts` (o módulo hermano) y `guardas.ts`. Verificar `npm test` y `npm run typecheck` en verde.
- [x] 12.2 RED → GREEN: `src/components/GoogleCalendar.test.tsx`: odontóloga sin conexión ve "Conectar Google Calendar" (llama a iniciar y navega a la URL); conectada ve cuenta, última sincronización y "Desconectar" con diálogo; mensajes de `?resultado=` ("No se pudo conectar Google Calendar. Volvé a intentarlo", "…no se dio el permiso"); recepción ve todas las profesionales y la lista de conflictos con "Sistema: … / Google: …" y botones por acción; la odontóloga ve sus conflictos sin botones; estado vacío "No hay conflictos con Google Calendar"; conexiones y conflictos se piden en paralelo (`Promise.all`, R2: el test verifica que ambas promesas se disparan antes de resolver la primera). Implementar `GoogleCalendar.tsx` y la entrada `#/google-calendar` en `Navegacion`/`ruta.ts` para los tres roles. Verificar en verde.
- [x] 12.3 RED → GREEN: `Agenda.test.tsx`/`TarjetaTurno`: bloque "Ocupado en Google" por franja y aviso "Conflicto con Google Calendar" con enlace a la sección; sin aviso en `en_espera`. Verificar en verde.
- [x] 12.4 Revisar en `estilos.css` que la sección y la agenda no desbordan a 360 px (tarjetas apiladas, botones de ancho completo, textos que cortan). Verificar con el E2E 13.2 a 360 px y `npm run build` sin errores.

## 13. E2E Playwright (R7, 360 px) — contra el servidor falso

- [x] 13.1 `frontend-panel/e2e/google-calendar.spec.ts` — conexión: la odontóloga sintética toca "Conectar Google Calendar", pasa por el consentimiento falso y vuelve a la sección con "Conectado como profesional.prueba@example.com". Verificar en verde local con Compose y en CI.
- [x] 13.2 Mismo archivo — eventos por transición y conflicto (viewport 360 px): una pre-reserva no genera evento en el falso (`/_control/eventos`); al acreditar la seña aparece un único evento "Turno · …" sin nombre ni teléfono; al cancelar desde la gestión del paciente el evento desaparece; mover un evento en el falso → la agenda muestra "Conflicto con Google Calendar", recepción toca "Restaurar en Google" y el falso vuelve a tener el horario del turno; sin desplazamiento horizontal. Verificar en verde.
- [x] 13.3 `frontend-paciente/e2e/google-calendar.spec.ts` — crear un ocupado en el falso para la profesional conectada → tras un ciclo, la pantalla de reserva a 360 px no ofrece ese horario y sí el contiguo. Verificar en verde.
- [x] 13.4 Correr la suite E2E completa de ambos frontends (incluidas las de C-05…C-12) con `gcal-falso` y el worker levantados. Verificar: todo en verde, sin tests saltados nuevos.

## 14. Documentación, auditoría y cierre

- [x] 14.1 Actualizar `knowledge-base/05_reglas_de_negocio.md` §Calendario: RN-GC-02 con el criterio aprobado (O9, O18, O20) y nuevas RN-GC-03 (qué turnos tienen evento y contenido sin datos del paciente, O7/O8) y RN-GC-04 (franjas ocupadas: qué se guarda y qué bloquean, O10/O19); cerrar la pregunta de conflictos en `10_preguntas_abiertas.md` y anotar la decisión en `09_decisiones_y_supuestos.md` (DD-05). Verificar que cada regla nueva tiene su escenario en los specs.
- [x] 14.2 Actualizar `knowledge-base/08_arquitectura_propuesta.md` (variables `GCAL_*`, `PUBLIC_PANEL_URL`, módulo `integraciones/gcal`) y `README.md` (cómo crear el cliente OAuth "Aplicación web" en Google Cloud, habilitar Calendar API, cargar usuarias de prueba, generar `GCAL_TOKEN_CLAVE`, levantar el falso con `--profile e2e`). Verificar que los comandos del README corren tal como están escritos.
- [x] 14.3 Actualizar `knowledge-base/06_funcionalidades.md` US-006 CA-1 con lo entregado y `CHANGES.md` §C-10 (scope final, migración `011`). Verificar coherencia con los specs.
- [x] 14.4 Correr `spec-rules-auditor` sobre el código y los specs finales contra `05_reglas_de_negocio.md` y `AGENTS.md`; registrar el dictamen en `design.md` y corregir lo que observe. Verificar dictamen APROBADO u OBSERVACIONES sin bloqueos.
- [x] 14.5 Verificación final: `python -m pytest -q` (backend), `npm test` + `npm run typecheck` + `npm run build` (ambos frontends), E2E completos, `openspec validate c-10-google-calendar-sync --strict`. Registrar conteos en el acta. Prueba manual opcional con una cuenta de Google sintética (sin datos reales, R19) antes del archive.

## Workflow follow-up

- Archivar con `/opsx:archive c-10-google-calendar-sync` cuando el usuario lo apruebe y marcar `[x]` C-10 en `CHANGES.md`.
- Sin commits ni push salvo pedido explícito (R11); commits en conventional commits (R12).

## Acta

- **Decisiones:** O1–O20 aprobadas el 2026-11-12, opción recomendada en todas.
- **Línea base (antes de C-10):** pytest 1569 passed.
- **Migración:** `011_google_calendar` (011 estaba libre).
- **Conteos finales:** pytest (ver informe del apply, ~1763 passed); frontend-panel vitest 403, typecheck, lint y build limpios; frontend-paciente vitest 177; Playwright panel 74 passed + 4 skips previos (viewport/medianoche), paciente 25 passed; `openspec validate --strict` válido.
- **No hecho:** la prueba manual opcional con una cuenta real de Google (14.5) no se ejecutó; no hay credenciales de Google en el entorno.
- **Stitch MCP:** ninguna tarea lo pedía.
- **Desvíos:** ver «Auditoría de implementación» en `design.md`.
