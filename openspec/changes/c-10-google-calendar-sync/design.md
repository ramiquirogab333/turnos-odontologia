# Design: c-10-google-calendar-sync

> Governance **ALTO**: las decisiones no obvias están en la tabla **O1–O20** al final, cada una con opciones y una recomendada. **Todas fueron APROBADAS por el usuario el 2026-11-12 (opción recomendada).** Los specs y `tasks.md` usan las recomendadas.

## Context

Motivación en `proposal.md` (Why). Estado actual relevado en el código (rama `feat/c-10-google-calendar-sync`, desde `2954100`):

- **Puerto de eventos (C-07):** `app/gestion/eventos.py` define `EventoTurno` (sin PII) y `NotificadorTurnos`, pero **solo para `turno_cancelado` y `turno_reprogramado`**. `app/gestion/deps.get_notificador` devuelve `NotificadorCompuesto([NotificadorRecordatorios(...)])` (C-09 D6), pensado para que C-10 sume el suyo. Se publica post-commit con `publicar_sin_romper` desde la gestión pública y la cancelación del panel.
- **Transiciones sin evento:** la acreditación de seña (`app/pagos/service.py`, `en_espera → reservado`), el alta manual (`app/panel/service.crear_turno_manual`, nace `reservado`), la reserva exenta (`app/public/service`, nace `reservado`), la confirmación (C-09), `ausente`/`atendido` y deshacer atendido (C-12) **no publican nada**. C-09 resolvió lo mismo reconciliando desde el estado del turno; C-10 hace igual y no toca esos servicios.
- **Base de trabajos (C-09):** `app/jobs/registro.py` (`TrabajoProgramado(nombre, intervalo, funcion(session, ahora) -> int)`, `ejecutar_trabajo` traga errores sin PII) y `app/jobs/worker.py` (arq 0.28 + redis 5.3.1, cron por intervalo, `unique` por ranura). La API no depende de Redis (C-09 O8).
- **Disponibilidad:** `app/public/service._cargar_bloqueos` arma la ocupación con turnos en `ESTADOS_BLOQUEANTES = (reservado, confirmado, atendido)`; la usan la consulta, la reserva y la reprogramación del paciente (`excluir_turno_id`). El 409 de horario ocupado lleva `motivo` (`profesional`/`sillon`) y alternativas.
- **Auth y roles:** `rol ∈ {admin, odontologo, recepcion}`; `usuario.profesional_id` vincula a la odontóloga con su agenda (C-08 O4); `require_recepcion_o_admin` en `app/auth/rbac.py`; la odontóloga es de solo lectura sobre turnos (C-08 O5) y no ve teléfonos (C-08 O6). El access token del panel vive en memoria y el refresh en cookie HttpOnly (C-08 D10): un redirect de Google al backend no trae `Authorization`.
- **Dependencias:** `httpx` ya está (cliente asíncrono). No hay librería de cifrado. El cliente oficial `google-api-python-client` es síncrono.
- **Frontend del panel:** navegación por hash (`#/caja`, `#/recordatorios`…) con secciones por rol en `Navegacion`; componentes con test al lado; E2E en `frontend-panel/e2e/`.
- **CI:** jobs `e2e` y `e2e-panel` levantan `postgres redis` y después `backend worker` con `docker compose up --wait`.
- **Última migración:** `010_recordatorios`. La siguiente es `011` (verificar antes del apply: C-14/C-15 pueden ir en paralelo).
- **Skill `gws-calendar-agenda`:** es una CLI de solo lectura de agenda; no sirve para la sincronía bidireccional. La integración se diseña contra la API REST de Google Calendar v3 detrás de un puerto propio.

## Goals / Non-Goals

**Goals:**
- El estado del turno es la fuente de verdad del lado sistema: perder un aviso nunca deja Google mal de forma permanente (reconciliación).
- La API nunca llama a Google (R16) y sigue funcionando con Google caído o sin credenciales.
- Ningún cambio en Google modifica un turno; todo desacuerdo queda como conflicto visible (RN-GC-02).
- Idempotencia: ni dos workers ni un ciclo interrumpido duplican eventos.
- Probar todo (pytest y E2E) sin cuenta real de Google.

**Non-Goals:**
- Canales `watch` (push de Google), calendarios secundarios, varios calendarios por profesional.
- Importar eventos de Google como turnos; editar turnos desde Google.
- Sincronizar sillones, recepción o pacientes.
- Reprogramar desde el panel (C-08 O13) — la resolución de un conflicto nunca mueve el turno.

## Decisions

### D1. Módulo `app/integraciones/gcal/`
```
app/integraciones/gcal/
  models.py        GcalConexion, EventoCalendar, GcalConflicto
  cifrado.py       cifrar/descifrar tokens (Fernet, O1)
  proveedor.py     Protocol ProveedorCalendario + tipos (EventoGoogle, CambiosGoogle, errores)
  proveedor_http.py adaptador httpx asíncrono contra Calendar v3 + OAuth (base URLs configurables solo en test/e2e)
  proveedor_falso.py proveedor en memoria para pytest
  oauth.py         iniciar (state firmado + PKCE), callback (canje, alta de conexión), desconectar
  contenido.py     (puro) armar título/descripción/horario del evento, id determinista, hash del contenido
  reconciliacion.py  (push) diff turnos ↔ evento_calendar por conexión
  pull.py          lectura incremental con syncToken, franjas ocupadas, detección movido/borrado
  conflictos.py    detección de solapes, cierre automático, resolución manual
  notificador.py   NotificadorCalendario (marca pendiente)
  sincronizacion.py  trabajo gcal_sync: por conexión → lock → token → pull → push → conflictos
  router.py, schemas.py
  servidor_falso.py  mini app FastAPI que imita OAuth + eventos (solo APP_ENV=e2e, O15)
```

### D2. Modelo de datos (migración `011_google_calendar`, `postgresql-table-design`)

**`gcal_conexion`** (una por profesional):

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` PK | |
| `profesional_id` | `BIGINT NOT NULL` FK `profesional(id) ON DELETE RESTRICT` | `UNIQUE` (cubre el índice, R6) |
| `usuario_id` | `BIGINT NULL` FK `usuario(id)` | quien conectó; índice propio |
| `estado` | `TEXT NOT NULL` | `CHECK IN ('pendiente','activa','revocada','desconectada')` |
| `cuenta_email` | `TEXT NULL` | `CHECK (LENGTH <= 254)`; dato de la profesional, no del paciente |
| `calendario_id` | `TEXT NOT NULL DEFAULT 'primary'` | `CHECK (LENGTH <= 255)` (O3) |
| `refresh_token_cifrado` / `access_token_cifrado` | `TEXT NULL` | Fernet, `CHECK (LENGTH <= 4096)` |
| `access_expira_en` | `TIMESTAMPTZ NULL` | |
| `sync_token` | `TEXT NULL` | `CHECK (LENGTH <= 2048)` |
| `oauth_nonce_hash` | `TEXT NULL` | SHA-256 del nonce del `state` |
| `oauth_verifier_cifrado` | `TEXT NULL` | verificador PKCE cifrado |
| `oauth_expira_en` | `TIMESTAMPTZ NULL` | `state` válido 10 min |
| `ultimo_sync_ok_en`, `proximo_intento_en` | `TIMESTAMPTZ NULL` | |
| `fallos_consecutivos` | `INTEGER NOT NULL DEFAULT 0` | `CHECK (>= 0)` |
| `ultimo_error` | `TEXT NULL` | `CHECK (LENGTH <= 300)`, sanitizado (clase + código HTTP) |
| `conectada_en`, `created_at`, `updated_at` | `TIMESTAMPTZ` | |

`CHECK (estado <> 'activa' OR refresh_token_cifrado IS NOT NULL)`, `CHECK (estado <> 'pendiente' OR (oauth_nonce_hash IS NOT NULL AND oauth_expira_en IS NOT NULL))`. Índice parcial de trabajo `(proximo_intento_en) WHERE estado = 'activa'`.

**`evento_calendar`** (mapeo `Turno ↔ EventoCalendar` y franjas ajenas, O16):

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `BIGINT ... IDENTITY` PK | |
| `conexion_id` | `BIGINT NOT NULL` FK `gcal_conexion(id)` | cubierto por el único `(conexion_id, google_event_id)` |
| `turno_id` | `BIGINT NULL` FK `turno(id) ON DELETE RESTRICT` | índice propio (R6) |
| `origen` | `TEXT NOT NULL` | `CHECK IN ('sistema','google')` |
| `google_event_id` | `TEXT NOT NULL` | `CHECK (LENGTH BETWEEN 5 AND 1024)` |
| `estado` | `TEXT NOT NULL` | `CHECK IN ('pendiente','sincronizado','borrado','desvinculado')` |
| `inicio`, `fin` | `TIMESTAMPTZ NOT NULL` | último horario conocido en Google; `CHECK (fin > inicio)` |
| `ocupa` | `BOOLEAN NOT NULL` | `opaque` y no cancelado/rechazado (O19) |
| `etag` | `TEXT NULL` | `CHECK (LENGTH <= 255)` |
| `hash_contenido` | `TEXT NULL` | hash del título/descripción/horario empujados (O9) |
| `generacion` | `INTEGER NOT NULL DEFAULT 0` | sufijo del id determinista (O17) |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | |

`CHECK ((origen = 'sistema') = (turno_id IS NOT NULL))`; `UNIQUE (conexion_id, google_event_id)`; índice único parcial `(conexion_id, turno_id) WHERE origen = 'sistema' AND estado IN ('pendiente','sincronizado')` (un evento vigente por turno y conexión); índice GiST `(conexion_id, tstzrange(inicio, fin, '[)')) WHERE origen = 'google' AND ocupa` para la disponibilidad (requiere `btree_gist`, ya creada por la migración 001). Nunca se guardan título, descripción, lugar ni invitados de un evento ajeno.

**`gcal_conflicto`:**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `BIGINT ... IDENTITY` PK | |
| `conexion_id` | `BIGINT NOT NULL` FK | índice propio |
| `turno_id` | `BIGINT NOT NULL` FK `turno(id)` | índice propio |
| `evento_id` | `BIGINT NOT NULL` FK `evento_calendar(id)` | índice propio; el evento del sistema o la franja ajena |
| `tipo` | `TEXT NOT NULL` | `CHECK IN ('movido_en_google','borrado_en_google','solapa_evento_externo')` |
| `estado` | `TEXT NOT NULL DEFAULT 'abierto'` | `CHECK IN ('abierto','resuelto')` |
| `sistema_inicio/fin`, `google_inicio/fin` | `TIMESTAMPTZ` | foto al detectar (`google_*` nulos en `borrado_en_google`) |
| `resolucion` | `TEXT NULL` | `CHECK IN ('restaurar_en_google','desvincular','revisado','turno_cancelado','solape_desaparecido')` |
| `resuelto_por_usuario_id` | `BIGINT NULL` FK `usuario(id)` | índice propio |
| `detectado_en`, `resuelto_en` | `TIMESTAMPTZ` | |

`CHECK ((estado = 'resuelto') = (resolucion IS NOT NULL AND resuelto_en IS NOT NULL))`; índice único parcial `(evento_id, turno_id, tipo) WHERE estado = 'abierto'`; índice `(conexion_id, estado)` para el listado. `downgrade` borra las tres tablas (se pierde el vínculo con Google; los eventos quedan en los calendarios; documentado).

### D3. OAuth (O1, O2, O3)
- `POST /conexion/iniciar` (rol `odontologo` con `profesional_id`): genera `nonce` y verificador PKCE, guarda `sha256(nonce)` y el verificador cifrado en la conexión (`pendiente`, vence en 10 min) y devuelve `https://accounts.google.com/o/oauth2/v2/auth?client_id=…&redirect_uri=GCAL_REDIRECT_URI&response_type=code&scope=https://www.googleapis.com/auth/calendar.events openid email&access_type=offline&prompt=consent&state=<JWT>&code_challenge=…&code_challenge_method=S256`. El `state` es un JWT HS256 firmado con la clave existente (`JWT_SECRET_KEY`, `type = gcal_state`, `profesional_id`, `nonce`, `exp` 10 min).
- `GET /oauth/callback` (sin bearer; la autenticidad la da el `state`): valida firma, `exp`, `type` y que `sha256(nonce)` coincida con la conexión `pendiente` (un solo uso: se borra al canjear), canjea el código con el verificador (llamada `await` con `httpx`, timeout 10 s: es la única llamada a Google desde la API y es la respuesta a una acción explícita de la usuaria, no una transición de turno), guarda `refresh_token`/`access_token` cifrados y `cuenta_email` (del `id_token`), deja la conexión `activa`, borra `sync_token` (pull completo en el próximo ciclo), audita y responde `303` a `PUBLIC_PANEL_URL/#/google-calendar?resultado=conectado|error_autorizacion|permiso_denegado`.
- Desconectar: `POST https://oauth2.googleapis.com/revoke` (falla tolerada), borra tokens y `sync_token`, conexión `desconectada`, eventos del sistema `pendiente/sincronizado` → `desvinculado`, franjas ajenas borradas de la tabla (dejan de ocupar), conflictos abiertos → `resuelto` con `revisado` por el usuario que desconecta. Audita.

### D4. Trabajo `gcal_sync` (O4, O5, O6, O13, O20)
Registrado en `trabajos_programados` si `GCAL_SYNC_HABILITADO` y hay credenciales. Un ciclo:
1. Toma las conexiones `activa` con `proximo_intento_en IS NULL OR <= ahora`.
2. Por conexión, en su propia sesión: `pg_try_advisory_xact_lock(<clave gcal>, conexion_id)`; si no lo obtiene, la saltea (otro worker la tiene). Un error de una conexión se loguea (clase + código HTTP, sin PII ni tokens) y sigue con la siguiente.
3. **Token:** si `access_expira_en <= ahora + 60 s`, renueva. `invalid_grant` → `revocada` + auditoría (sin usuario) y fin de esa conexión.
4. **Pull:** `events.list(singleEvents=true, showDeleted=true, syncToken=…)`; sin `syncToken` lee el horizonte (`timeMin` = hoy 00:00 de la clínica, `timeMax` = +`GCAL_HORIZONTE_DIAS`). Paginado. `410` → borra `sync_token` y relee. Para cada evento: si trae `extendedProperties.private.turnos_sistema = "1"` (es nuestro), compara con su `evento_calendar` (D6); si es ajeno, hace upsert de la franja con `ocupa = transparency != 'transparent' AND status != 'cancelled' AND la profesional no lo rechazó`; los cancelados borran la franja.
5. **Push** (D5) con el estado actual de los turnos.
6. **Conflictos** (D6): solapes nuevos y cierres automáticos.
7. Éxito → `fallos_consecutivos = 0`, `ultimo_sync_ok_en = ahora`. Error transitorio (red, 429, 5xx) → `fallos_consecutivos += 1`, `proximo_intento_en = ahora + [1, 5, 15, 60][min(n,4)-1] min`. Los pendientes no se pierden: siguen siendo diferencias en el próximo diff.

Intervalo `GCAL_SYNC_INTERVALO_SEGUNDOS` (60). El pull usa el `syncToken` (una llamada barata si no hubo cambios), así que 60 s es aceptable para la cuota de Calendar API con decenas de profesionales.

### D5. Push por reconciliación (O4, O7, O8, O9, O17)
- **Deseado:** turnos de la profesional con `estado IN ('reservado','confirmado')` e `inicio` en el horizonte, más los turnos con `evento_calendar` vigente (para detectar cancelaciones y reprogramaciones aunque salgan del horizonte).
- **Diff por turno:**
  - Sin evento vigente y bloqueante → `events.insert` con id determinista `t{turno_id}c{conexion_id}g{generacion}` (codificado en base32hex, el alfabeto que exige Google). `409 duplicate` = ya creado por un ciclo anterior o por otro worker → se lee y se vincula. Se guarda `estado = sincronizado`, `etag`, `hash_contenido`, `inicio/fin`.
  - Vigente y `cancelado` → `events.delete` (`404/410` = ya no está) → `borrado`.
  - Vigente y horario o contenido distinto del `hash_contenido` → `events.patch` con `If-Match: etag`; `412` (cambió en Google) → no se escribe, el pull del ciclo siguiente decide si hay conflicto.
  - `ausente`/`atendido` → nada (O7). Deshacer atendido vuelve a `reservado` con el mismo evento: nada.
  - Con conflicto abierto `movido_en_google`/`borrado_en_google` o `desvinculado` → nada (nunca sobrescribe, RN-GC-02).
- **Contenido** (`contenido.py`, puro): título `Turno · <tratamiento>`; descripción `Sillón <nombre>` + enlace `PUBLIC_PANEL_URL/#/agenda?fecha=YYYY-MM-DD`; `start/end` con `timeZone = APP_TZ`; `extendedProperties.private = {turnos_sistema: "1", turno_id: "<id>"}`; `transparency = opaque`; sin invitados ni recordatorios propios. Nunca nombre, teléfono, DNI, email ni código de gestión (O8).

### D6. Detección de conflictos (O9, O18, O20)
- **Evento propio en el pull:** `status = cancelled` y el turno sigue bloqueante → conflicto `borrado_en_google`. Horario distinto del último empujado y el turno no cambió → `movido_en_google` (se guarda el horario de Google en `evento_calendar.inicio/fin`). Solo título/descripción distintos → nada (O9). Si el turno también cambió desde el último push (cambio de los dos lados), gana el conflicto: no se escribe y se registra `movido_en_google` con ambos horarios.
- **Solape:** franja ajena `ocupa` de la misma conexión que se superpone `[inicio, fin)` con un turno `reservado`/`confirmado` → `solapa_evento_externo` (uno por par franja-turno; `revisado` cierra ese par).
- **Cierre automático (O20):** turno cancelado → todos sus conflictos abiertos se cierran con `turno_cancelado`; franja que deja de superponerse (movida, borrada, pasa a libre) → `solape_desaparecido`. Un conflicto `movido_en_google` cuyo evento vuelve en Google al horario del turno se cierra con `solape_desaparecido`.
- **Resolución manual (recepción/admin):** `restaurar_en_google` (movido/borrado): cierra el conflicto; el push del ciclo siguiente hace `patch` al horario del turno o, si fue borrado, marca el vínculo viejo `borrado` y crea uno nuevo con `generacion + 1` (Google no reutiliza ids borrados). `desvincular` (movido/borrado): vínculo `desvinculado`, el sistema no vuelve a tocar ese turno en Google. `revisado` (solape): cierra. Si recepción quiere cancelar el turno, usa la cancelación existente (con su ventana de 24 h); la conciliación cierra el conflicto sola.
- Cada resolución deja `RegistroAuditoria` (`entidad = gcal_conflicto`, antes/después, sin PII).

### D7. Notificador (O4)
`NotificadorCalendario.publicar(evento)`: en sesión propia, `UPDATE evento_calendar SET estado = 'pendiente' WHERE turno_id = :id AND origen = 'sistema' AND estado = 'sincronizado'` y `UPDATE gcal_conexion SET proximo_intento_en = NULL` de la conexión de esa profesional (para que el próximo ciclo no espere un backoff viejo). Liviano, sin Redis ni Google. Se suma en `get_notificador`: `NotificadorCompuesto([NotificadorRecordatorios(...), NotificadorCalendario(...)])`. Si falla, `publicar_sin_romper` lo loguea y el diff de D5 lo corrige igual (el estado del turno manda).

### D8. Disponibilidad y alta manual (O10)
- `_cargar_bloqueos` suma, por profesional, las franjas `evento_calendar` con `origen = 'google' AND ocupa` de conexiones `activa` o `revocada` (no `desconectada`) que rozan el rango, como bloqueos de profesional sin sillón (`_profesional_ocupado` las considera; `_sillon_libre` no). Una sola consulta extra por operación (índice GiST). Consulta, reserva y reprogramación del paciente quedan cubiertas porque comparten esa función; el 409 sigue siendo `motivo = profesional`.
- La reserva pública no toma ningún lock nuevo: la franja de Google no es un turno y no entra en el EXCLUDE (R5 sigue garantizando turno vs turno). Una franja que llega entre la consulta y la reserva puede terminar en conflicto `solapa_evento_externo`: es el caso que RN-GC-02 manda resolver a mano.
- La acreditación de seña no revalida contra Google (RN-SN-05 habla de turnos): acredita y la sincronización registra el solape.
- Alta manual: misma consulta; si se superpone, crea el turno igual y responde `aviso_google_calendar = true` (campo nuevo en `TurnoManualCreado`).

### D9. API (R15) y pantallas (R1–R3)
- `router.py`, `prefix=/api/panel/google-calendar`:
  - `GET /conexiones` → `list[ConexionOut]` (recepción/admin: todas las profesionales; odontóloga: la suya).
  - `POST /conexion/iniciar` → `IniciarOut {url_autorizacion}`; 403 sin profesional vinculada, 409 `conexion_activa`, 503 `gcal_no_configurado` si faltan credenciales.
  - `GET /oauth/callback?code&state&error` → 303 al panel.
  - `DELETE /conexiones/{profesional_id}` → 204; odontóloga solo la suya, admin cualquiera; 404 sin conexión.
  - `GET /conflictos?estado=abierto&profesional_id=` → `list[ConflictoOut]` con `acciones` posibles por tipo.
  - `POST /conflictos/{id}/resolver` body `{accion: Literal[...]}` → `ConflictoOut`; 403, 404, 409 `conflicto_cerrado`, 422 `accion_no_valida`.
- `GET /api/panel/agenda`: `AgendaResponse.ocupados_google: list[OcupadoGoogle]` y `TurnoAgenda.calendario: {estado, conflicto_abierto}` (campos nuevos, no rompe).
- `frontend-panel`: sección `#/google-calendar` en `Navegacion` para los tres roles. Componente `GoogleCalendar`: tarjeta de conexión (estado, cuenta, última sincronización, "Conectar Google Calendar" que hace `location.assign(url_autorizacion)`, "Desconectar" con diálogo); lista de conflictos en tarjetas apiladas a 360 px con "Sistema: 10:00–10:30 / Google: 12:00–12:30" y botones por acción (solo recepción/admin; la odontóloga los ve sin botones). Conexiones y conflictos se piden en paralelo (`Promise.all`, R2). Lee `?resultado=` del hash para el mensaje de vuelta. `Agenda`: bloque gris "Ocupado en Google" y aviso en `TarjetaTurno`. Textos en castellano simple que explican qué pasó y qué hacer.

### D10. Configuración (R17)
Nuevas variables en `Settings` y Compose: `GCAL_CLIENT_ID`, `GCAL_CLIENT_SECRET` (`SecretStr`), `GCAL_REDIRECT_URI` (p. ej. `http://localhost:8000/api/panel/google-calendar/oauth/callback`), `GCAL_TOKEN_CLAVE` (`SecretStr`, clave Fernet de 32 bytes base64; obligatoria si hay `GCAL_CLIENT_ID`), `GCAL_SYNC_HABILITADO` (`true`), `GCAL_SYNC_INTERVALO_SEGUNDOS` (`60`, `> 0`), `GCAL_HORIZONTE_DIAS` (`60`, 1–365), `PUBLIC_PANEL_URL` (`http://localhost:5174`), `GCAL_OAUTH_BASE_URL` / `GCAL_API_BASE_URL` (defaults de Google; otros valores solo con `APP_ENV ∈ {test, e2e}`, validador como el de `MP_GATEWAY`). Ningún valor en el repo; `.env*` sigue fuera (R20). Sin credenciales, la API arranca y los endpoints de conexión responden 503 `gcal_no_configurado`.

### D11. Estrategia de pruebas (Strict TDD) y CI (O15)
- **Unit (sin DB):** `contenido.py` (título, descripción sin PII, id base32hex determinista, hash, zona), `cifrado.py` (ida y vuelta, clave inválida), clasificación de errores HTTP, backoff, validadores de settings, `state` (firma, vencimiento, tipo).
- **Integración (Postgres, `ProveedorFalso` en memoria):** migración 011 (upgrade/downgrade, CHECK, únicos parciales, GiST); push por cada transición (acreditación, alta manual, exento, confirmación, cancelación, reprogramación, ausente, atendido, deshacer); `en_espera` sin evento; horizonte; idempotencia (409 duplicate, dos sesiones concurrentes con el advisory lock); pull (opaque/transparent/cancelado/rechazado, 410); conflictos y cierres automáticos; resolución (RBAC 401/403, 404/409/422, auditoría); token revocado; errores 429/5xx y backoff; notificador; disponibilidad pública y reprogramación excluyen franjas; alta manual con aviso; OAuth con el canje simulado por `httpx.MockTransport`.
- **Servidor falso de Google (`servidor_falso.py`):** implementa `/o/oauth2/v2/auth` (consiente al toque con una cuenta sintética `profesional.prueba@example.com` y redirige al callback), `/token`, `/revoke`, `GET/POST/PATCH/DELETE /calendar/v3/calendars/{id}/events` con `syncToken`, `etag`, ids propios y `409 duplicate`, y endpoints de control `/_control/*` para que el E2E simule cambios hechos "en Google" (mover, borrar, crear un ocupado, forzar 503 o `invalid_grant`). Se arranca solo con `APP_ENV=e2e`. Servicio `gcal-falso` en Compose con `profiles: ["e2e"]` y healthcheck.
- **E2E Playwright (R7, 360 px):** panel: conectar Google Calendar (flujo completo contra el falso) → aparece "Conectado"; acreditar la seña de una pre-reserva → el falso tiene el evento sin datos del paciente; pre-reserva sin evento; cancelar desde la gestión del paciente → evento borrado; mover el evento en el falso → conflicto visible y "Restaurar en Google" lo devuelve; franja ocupada en el falso → no se ofrece en la reserva pública (frontend-paciente). Los jobs E2E levantan `postgres redis gcal-falso` y luego `backend worker` con `GCAL_SYNC_INTERVALO_SEGUNDOS=3`, `GCAL_*_BASE_URL=http://gcal-falso:8090` y credenciales sintéticas.

## Risks / Trade-offs

- **[Datos de salud en un tercero]** → aun sin nombre, "Turno · Endodoncia" en el calendario de la profesional es un dato que sale del sistema. *Mitigación:* O8 sin identificadores del paciente; la profesional lo carga en su propia cuenta; revisar con el PO si el tratamiento se muestra.
- **[Verificación de la app OAuth de Google]** → el permiso `calendar.events` es "sensible": con la app sin verificar Google muestra un aviso y limita a 100 usuarios de prueba. *Mitigación:* suficiente para una clínica (pocas profesionales, usuarios de prueba); el README explica cómo cargarlas; verificación antes de escalar.
- **[Clave de cifrado perdida o rotada]** → los tokens no se pueden leer. *Mitigación:* el ciclo trata el error de descifrado como `revocada` (pide reconectar); rotación documentada (`MultiFernet` con clave vieja y nueva) como seguimiento.
- **[Latencia de hasta un intervalo]** → un turno nuevo tarda hasta 60 s en verse en Google y una franja nueva de Google hasta 60 s en dejar de ofrecerse. *Mitigación:* aceptado (O4/O5); la reserva sobre una franja recién creada termina en conflicto manual, no en doble turno.
- **[Conflictos ruidosos]** → si la profesional usa Google para anotar cosas "encima" de turnos, cada una es un conflicto. *Mitigación:* `revisado` cierra; cierre automático cuando desaparece; métrica de conflictos para revisar el criterio.
- **[Cuota de la API]** → muchas profesionales × ciclo de 60 s. *Mitigación:* pull incremental con `syncToken`; backoff por conexión; intervalo configurable.
- **[El servidor falso diverge de Google]** → los E2E pasan y producción no. *Mitigación:* el falso implementa solo el subconjunto documentado que usa el adaptador; tests de contrato del adaptador contra respuestas de ejemplo de la documentación; prueba manual con una cuenta sintética de Google antes del archive.
- **[Turnos de días pasados al conectar]** → no se crean (horizonte desde hoy). *Mitigación:* aceptado (O6).

## Migration Plan

1. Verificar con `ls backend/src/alembic/versions` que `011` sigue libre y aplicar `alembic upgrade head` (`011_google_calendar`, reversible).
2. Crear el cliente OAuth "Aplicación web" en Google Cloud con la Calendar API habilitada y el redirect `GCAL_REDIRECT_URI`; generar `GCAL_TOKEN_CLAVE` (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`); cargar todo como variables de entorno de backend y worker (nunca en el repo).
3. Desplegar backend y worker juntos. Sin variables `GCAL_*` todo sigue igual que antes (trabajo no registrado, endpoints 503).
4. Rollback: `GCAL_SYNC_HABILITADO=false` detiene la sincronía al instante; `alembic downgrade 010_recordatorios` borra las tablas (los eventos ya creados quedan en los calendarios de las profesionales y hay que borrarlos a mano o antes desconectar).

## Auditoría de reglas de negocio (`spec-rules-auditor`, 2026-11-12)

**Dictamen: OBSERVACIONES** (sin bloqueos; tres gaps corregidos en los specs; RN-GC-02 queda completada por O9/O18/O20 y requiere OK del PO; O8 y O10 son supuestos de negocio).

| Regla | Descripción breve | Estado | Observación / dónde |
|---|---|---|---|
| RN-GC-01 | Sincronía bidireccional con el GCal del profesional | CUBIERTA con SUPUESTO | Push: "Solo los turnos que bloquean agenda…", "Cancelar borra…"; pull: "Los eventos ocupados de Google se traen como franjas ocupadas". "Y viceversa" (US-006 CA-1) se interpreta como franjas ocupadas, no como turnos **[SUPUESTO / ABIERTO: O10, O19]** |
| RN-GC-02 | Conflicto → resolución manual, criterio a definir | CUBIERTA, criterio PROPUESTO | "Un cambio en Google nunca modifica un turno", "Conflicto por superposición…", "Resolución manual…", "Desvincular…". Tipos, acciones y cierres automáticos en O9/O18/O20 **[SUPUESTO / ABIERTO hasta aprobación]** |
| R8 / RN-SN-01 | `en_espera` sin evento de calendario | CUBIERTA | Escenario "Pre-reserva sin evento"; "Pre-reserva superpuesta" sin conflicto; agenda `sin_evento` |
| C-08 O7 | Alta manual nace `reservado` sin seña | CUBIERTA | Escenario de borde del horizonte; `gestion-panel` alta con aviso |
| RN-TU-01/02 | Ventana de 24 h para cancelar/reprogramar | NO AFECTADA / reutilizada | La sincronía nunca cancela ni mueve turnos; la resolución tampoco (usa la cancelación existente) |
| RN-TU-03 / R5 | Anti-solape por profesional y sillón en DB | CUBIERTA | La franja de Google no entra al EXCLUDE (no es turno); se suma como ocupación de profesional en la disponibilidad (D8) |
| C-08 O19 | `atendido` ocupa la agenda; `ausente` libera | CUBIERTA | "Ausente y atendido conservan el evento" (O7) |
| RN-SN-05 | Pago tardío / horario perdido → `a_reembolsar` | NO AFECTADA | La acreditación no revalida contra Google (D8); el solape va a conflicto manual |
| RN-WA-* (C-09) | Recordatorios | NO AFECTADA | El compuesto de notificadores reparte el evento a ambos sin acoplarlos |
| RN-GL-01 | Auditoría de acciones del panel | CUBIERTA | Conectar, desconectar, revocación y resolución de conflictos auditadas |
| R3 / R7 | 360 px y E2E de flujos de turnos | CUBIERTA | Sección del panel y agenda a 360 px; E2E de creación/borrado por transición, `en_espera`, conflicto y reserva pública |
| R4 / R6 / R14 | Tipos con zona, `TEXT`+`CHECK`, FK indexadas, migración reversible | CUBIERTA | D2 |
| R15 / R16 | Pydantic en el borde; nada bloqueante en la API | CUBIERTA | D9; "La API nunca llama a Google" (salvo el canje OAuth, acción explícita con `httpx` async, D3) |
| R17 / R20 | Secretos por entorno, sin `.env` versionado | CUBIERTA | D10; tokens cifrados (O1); nunca en logs |
| R19 / Ley 25.326 | Datos sintéticos, mínimo de datos a terceros | CUBIERTA con SUPUESTO | "El evento no identifica al paciente" (O8); franjas ajenas sin título (O19). Mostrar el tratamiento **[SUPUESTO / ABIERTO: O8]** |

**Gaps detectados y corregidos en los specs:**
1. Un turno cancelado con conflicto abierto dejaba el conflicto colgado y el push intentaba borrar un evento ya borrado. → Escenario "Cancelar un turno cuyo evento ya no está en Google" y cierre automático `turno_cancelado` (O20).
2. La reprogramación del paciente y el alta manual usaban la disponibilidad sin franjas de Google y no estaban en ninguna capability. → Deltas `turnos/gestion-paciente` y `turnos/gestion-panel`.
3. El horizonte excluía los turnos ya vinculados que salían de él (p. ej. reprogramado a 70 días), dejando el evento viejo en Google. → D5 incluye en el diff todo turno con evento vigente.

**Riesgos que quedan para la revisión:** datos de salud en Google (O8), verificación de la app OAuth, latencia de un intervalo entre una franja nueva y la oferta pública (D8).

**Terna canónica (incluida en los specs):**
- *Esperado:* GIVEN profesional 7 conectada y turno 501 `en_espera`, WHEN se acredita la seña y corre la sincronización, THEN existe un único evento "Turno · Limpieza" sin datos del paciente.
- *Error de negocio:* GIVEN el turno 512 `reservado` a las 10:00 con evento, WHEN la profesional lo mueve a las 12:00 en Google, THEN el turno sigue a las 10:00, hay conflicto `movido_en_google` con ambos horarios y el sistema no reescribe el evento hasta la resolución manual.
- *Borde:* GIVEN un turno de 14:30 a 15:00 y una franja ocupada de 15:00 a 16:00, WHEN corre la sincronización, THEN no hay conflicto (intervalos `[inicio, fin)`); GIVEN horizonte de 60 días, THEN un turno a 59 días tiene evento y uno a 61 no.

## Decisiones (O1–O20) — APROBADAS (2026-11-12)

| # | Decisión | Opciones | Recomendación (default de specs y tasks) | Estado |
|---|---|---|---|---|
| O1 | Guardado de los tokens OAuth | (a) refresh y access token cifrados en la base con Fernet (`cryptography`), clave `GCAL_TOKEN_CLAVE` por entorno; (b) en texto plano en la base; (c) en un gestor de secretos externo | **(a)** un volcado de la base no expone el acceso al calendario; (c) no existe en el stack. | APROBADA (recomendada) |
| O2 | Quién conecta | (a) la propia odontóloga desde el panel (OAuth web + PKCE); (b) admin en su nombre; (c) cuenta de servicio con delegación de dominio | **(a)** el consentimiento lo da la dueña de la cuenta; (c) exige Google Workspace. | APROBADA (recomendada) |
| O3 | Qué calendario | (a) el principal de la profesional; (b) uno secundario "Turnos" creado por el sistema; (c) elegir de una lista | **(a)** DD-05: Google es su calendario principal y quiere ver todo junto; (b)/(c) se pueden sumar después (`calendario_id` ya existe). | APROBADA (recomendada) |
| O4 | Cadencia del push sistema→Google | (a) reconciliación periódica en el worker (60 s) + el notificador solo marca pendiente; (b) la API llama a Google al confirmar la transición; (c) la API encola en Redis | **(a)** cubre también las transiciones que no publican evento, la API no depende de Google ni de Redis (R16, C-09 O8). | APROBADA (recomendada) |
| O5 | Cadencia del pull Google→sistema | (a) pull incremental con `syncToken` en cada ciclo; (b) notificaciones push de Google (`watch`) con webhook; (c) ambas | **(a)** (b) exige un endpoint HTTPS público y renovar canales; queda como mejora. | APROBADA (recomendada) |
| O6 | Horizonte de sincronización | (a) desde hoy hasta `GCAL_HORIZONTE_DIAS` (60) + todo turno ya vinculado; (b) todos los turnos, pasados y futuros | **(a)** acota llamadas y no llena el calendario con historia. | APROBADA (recomendada) |
| O7 | Evento de `ausente` / `atendido` | (a) se conserva sin cambios; (b) se borra; (c) se actualiza el título ("Ausente") | **(a)** es historia de un horario pasado; (c) expone el ausentismo en un tercero. | APROBADA (recomendada) |
| O8 | Contenido del evento (Ley 25.326) | (a) "Turno · <tratamiento>" + sillón + enlace al panel, sin datos del paciente; (b) solo "Turno" + sillón; (c) nombre de contacto + tratamiento | **(a)** sirve a la profesional sin identificar al paciente; (c) requiere OK legal/PO. **Supuesto de negocio.** | APROBADA (recomendada) |
| O9 | Qué hace un cambio hecho en Google sobre un evento del sistema | (a) mover/borrar → conflicto y se deja de escribir ese evento; cambios solo de texto se ignoran (no conflicto, no se pisan hasta que el turno cambie); (b) todo cambio es conflicto; (c) el sistema reescribe siempre | **(a)** nunca mueve ni cancela un turno (RN-GC-02) y no genera ruido por retoques de texto; (c) es auto-sobrescritura. | APROBADA (recomendada) |
| O10 | ¿Los eventos ocupados de Google bloquean disponibilidad? | (a) solo se muestran en la agenda; (b) se excluyen de la reserva pública y de la reprogramación del paciente; el alta manual avisa sin bloquear; (c) bloquean todo, también el alta manual | **(b)** evita que el público reserve un horario que la profesional ya ocupó, y deja a recepción decidir. **Supuesto de negocio.** | APROBADA (recomendada) |
| O11 | UI de conflictos | (a) sección "Google Calendar" (conexión + lista de conflictos con criterio y acciones) + aviso en la tarjeta del turno; (b) solo un aviso/toast en la agenda | **(a)** RN-GC-02 pide criterio visible y la resolución necesita contexto (sistema vs Google). | APROBADA (recomendada) |
| O12 | Quién resuelve los conflictos | (a) recepción y admin; la odontóloga los ve sin acciones; (b) también la odontóloga los suyos; (c) solo admin | **(a)** coherente con C-08 O5 (odontóloga solo lectura sobre turnos); recepción opera la agenda. | APROBADA (recomendada) |
| O13 | Google caído / token revocado / `syncToken` vencido | (a) transitorios con backoff por conexión (1/5/15/60 min) sin perder pendientes; `invalid_grant` → `revocada` + aviso "Volvé a conectar"; 410 → relectura completa; (b) desconectar ante cualquier error | **(a)** se recupera solo y nunca toca turnos. | APROBADA (recomendada) |
| O14 | Qué pasa al desconectar | (a) se revoca y se borran los tokens; los eventos quedan en Google, desvinculados; (b) además se borran de Google los eventos futuros del sistema; (c) preguntar en el momento | **(a)** desconectar no debería vaciarle el calendario a la profesional; (c) puede sumarse después. | APROBADA (recomendada) |
| O15 | E2E sin Google real | (a) servidor falso de Google (OAuth + eventos + control) como servicio de Compose con perfil `e2e`, el adaptador HTTP real apunta a él; pytest con proveedor en memoria; (b) proveedor falso dentro del proceso con estado en una tabla; (c) interceptar la red en Playwright | **(a)** prueba el adaptador real y el worker (que corre en otro proceso); (c) no ve las llamadas del worker. | APROBADA (recomendada) |
| O16 | Forma del mapeo `Turno ↔ EventoCalendar` | (a) `evento_calendar` con a lo sumo un evento vigente por turno y conexión, historial de borrados/desvinculados, y las franjas ajenas en la misma tabla con `turno_id` nulo; (b) tabla N:M literal de la KB 04 | **(a)** la KB dice `*───*` porque un turno puede tener varios eventos en el tiempo (historial); (a) lo cumple con una garantía de unicidad. Ajusta la KB 04. | APROBADA (recomendada) |
| O17 | Idempotencia del push | (a) id de evento determinista (`turno`, `conexión`, `generación`) + advisory lock por conexión; (b) solo el lock; (c) buscar por `extendedProperties` antes de crear | **(a)** un ciclo cortado entre "crear en Google" y "guardar" no duplica (Google responde 409); (c) suma una llamada por turno. | APROBADA (recomendada) |
| O18 | Tipos de conflicto y acciones | (a) `movido_en_google` y `borrado_en_google` → "Restaurar en Google" o "Desvincular"; `solapa_evento_externo` → "Marcar revisado"; cancelar el turno se hace con la cancelación existente; (b) sumar "Mover el turno al horario de Google" | **(a)** (b) sería reprogramar desde el panel, fuera de alcance (C-08 O13) y con la ventana de 24 h de por medio. | APROBADA (recomendada) |
| O19 | Datos guardados de un evento ajeno | (a) solo inicio, fin, si ocupa y estado (sin título, descripción, lugar ni invitados); la agenda muestra "Ocupado en Google"; (b) guardar y mostrar el título | **(a)** minimización: la agenda personal de la profesional no es dato del sistema y recepción no necesita el detalle. | APROBADA (recomendada) |
| O20 | Cierre automático de conflictos | (a) se cierran solos si el turno se cancela o si el solape/movimiento desaparece (quedan como historia con la resolución automática); (b) siempre los cierra una persona | **(a)** evita una lista llena de conflictos que ya no existen; no sobrescribe nada. | APROBADA (recomendada) |

## Auditoría de implementación (`spec-rules-auditor`, 2026-11-12)

**Dictamen: APROBADO con observaciones menores (sin bloqueos).** Contra `05_reglas_de_negocio.md` y R1–R20, sobre el código y los specs finales.

| Regla | Estado | Evidencia |
|---|---|---|
| RN-GC-01 / RN-GC-03 / RN-GC-04 | CUBIERTAS | `test_gcal_push_*`, `test_gcal_pull_*`, `test_gcal_disponibilidad_*`; KB 05 actualizada |
| RN-GC-02 | CUBIERTA | `test_gcal_conflictos_*`: nunca se escribe sobre un conflicto abierto, nunca cambia un turno |
| R8 | CUBIERTA | `en_espera` jamás tiene evento ni conflicto (push, solape y agenda) |
| RN-TU-01/02 (24 h) | NO AFECTADA | la sincronía no cancela ni mueve turnos |
| R4/R6/R14 | CUBIERTAS | `test_gcal_migracion` (timestamptz, FK indexadas, reversible); sin SQL crudo fuera de la migración |
| R15/R16 | CUBIERTAS | Pydantic en todos los endpoints; la API solo llama a Google en el canje OAuth (httpx async); `NotificadorCalendario` solo toca la base |
| R17/R19/R20 | CUBIERTAS | tokens Fernet, `SecretStr`, tests de "sin token en logs", datos sintéticos, sin archivos sueltos en la raíz |
| R3/R7 | CUBIERTAS | E2E a 360 px y 1280 px contra el Google falso |

**Observaciones y desvíos respecto del diseño:**
1. Se agregó `GCAL_TOKEN_BASE_URL` (además de `GCAL_OAUTH_BASE_URL`/`GCAL_API_BASE_URL`): en E2E el consentimiento lo abre el navegador del host y el canje lo hace el contenedor.
2. Al desconectar, las franjas ajenas quedan `estado = borrado, ocupa = false` (no se borran filas) para no romper la FK del historial de conflictos.
3. Tras desconectar y volver a conectar, los vínculos `desvinculado` anteriores no se resincronizan (los turnos ya vinculados quedan fuera; los turnos nuevos sí se sincronizan). Mejora futura.
4. Las pruebas de migraciones previas (`test_caja_migracion`, `test_recordatorios_migracion`) fijaban `010` como head; se actualizaron a `011`.
