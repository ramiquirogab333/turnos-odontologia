# Proposal: c-10-google-calendar-sync

## Why
Google Calendar es hoy el calendario principal de las profesionales (DD-05) y la agenda del sistema no se refleja ahí, ni lo que anotan en Google llega al sistema: la reserva pública puede ofrecer un horario que la profesional ya tiene ocupado en su calendario (US-006, RN-GC-01). C-07 dejó el puerto `NotificadorTurnos` esperando a C-10 y C-09 dejó la base de trabajos programados (Redis + worker arq) lista para registrar un trabajo nuevo. Falta además el criterio de conflictos que la KB deja abierto (RN-GC-02, `10_preguntas_abiertas.md`): este change lo propone como decisiones a aprobar.

## What Changes
- **Conexión OAuth por profesional (R17):** la odontóloga conecta su propio Google Calendar desde el panel (flujo OAuth web con `state` firmado y PKCE). `GCAL_CLIENT_ID` / `GCAL_CLIENT_SECRET` / `GCAL_REDIRECT_URI` por entorno; los tokens se guardan cifrados con una clave de entorno (O1). Se puede desconectar; un token revocado deja la conexión `revocada` y pide reconectar, sin tocar ningún turno (O13).
- **Sistema → Google (push):** cada turno que bloquea agenda (`reservado`, `confirmado`) de una profesional conectada tiene un evento en su calendario; un `en_espera` nunca (R8, RN-SN-01); al cancelar se borra el evento y al reprogramar se mueve. El evento no lleva datos que identifiquen al paciente (O8). `ausente` y `atendido` conservan el evento como historial (O7).
- **Google → sistema (pull incremental con `syncToken`):** los eventos ocupados (`opaque`) que la profesional carga en Google se guardan solo como franjas ocupadas (inicio, fin, sin título ni invitados, O19) y dejan de ofrecerse en la reserva pública y en la reprogramación del paciente (O10). El alta manual del panel avisa pero no bloquea.
- **Conflictos con resolución manual (RN-GC-02):** un cambio hecho en Google nunca mueve ni cancela un turno. Si un evento del sistema se mueve o se borra en Google, o si un turno que bloquea agenda se superpone con un evento ocupado de Google, se registra un conflicto con su criterio visible (qué dice el sistema y qué dice Google) y se deja de escribir ese evento hasta que recepción o admin lo resuelva: restaurar en Google, desvincular el turno del calendario o marcarlo revisado (O9, O18).
- **Trabajo `gcal_sync` en el worker (R16):** reconciliación periódica (60 s por defecto, O4) entre el estado de los turnos y el calendario dentro de un horizonte (hoy a +60 días, O6), con ids de evento deterministas para no duplicar. La API nunca llama a Google: la implementación de `NotificadorTurnos` solo marca el evento como pendiente en la base y se suma al `NotificadorCompuesto` de C-09. Las transiciones que no publican evento (acreditación de seña, alta manual, confirmación) las toma la misma reconciliación.
- **Errores de Google:** 429/5xx/red → reintento con espera creciente sin perder el pendiente; `410 Gone` del `syncToken` → resincronización completa sin duplicar (O13).
- **Panel (`frontend-panel/`), 360 px (R3):** sección nueva "Google Calendar" con el estado de conexión por profesional, el botón "Conectar Google Calendar" (odontóloga) y la lista de conflictos con sus acciones (recepción/admin, O11, O12). La agenda muestra un aviso en el turno con conflicto y las franjas "Ocupado en Google".
- **Migración `011_google_calendar`** (reversible, R14): tablas `gcal_conexion`, `evento_calendar` (mapeo `Turno ↔ EventoCalendar`) y `gcal_conflicto`, con FK indexadas (R6), `TIMESTAMPTZ` y `TEXT` + `CHECK` (R4).
- **Pruebas sin Google real (O15):** un servidor falso de Google Calendar (OAuth + subconjunto de la API de eventos) como servicio de Compose solo para E2E; el adaptador HTTP real apunta a él. Pytest con un proveedor falso en memoria. E2E Playwright (R7): conectar, evento creado al acreditar, `en_espera` sin evento, borrado al cancelar, cambio en Google → conflicto manual, franja ocupada fuera de la reserva pública.
- **Decisiones aprobadas:** O1–O20 en `design.md`, cada una con una opción recomendada, **APROBADAS por el usuario el 2026-11-12**; los specs y las tareas usan las recomendadas.

## Capabilities

### New Capabilities
- `integraciones/google-calendar`: conexión OAuth por profesional y su ciclo de vida, el mapeo turno ↔ evento, qué turnos generan evento y cuándo se crea, mueve o borra, el pull incremental de eventos ocupados, la detección y resolución manual de conflictos, el manejo de errores de Google y la sección del panel a 360 px.

### Modified Capabilities
- `plataforma/trabajos-programados`: se suma el trabajo periódico de sincronización con Google Calendar (intervalo configurable, deshabilitable, idempotente con varios workers).
- `turnos/reserva-publica`: los horarios ocupados en el Google Calendar conectado de la profesional dejan de ofrecerse y de poder reservarse.
- `turnos/gestion-paciente`: la reprogramación del paciente trata una franja ocupada en Google como horario ocupado (409 con alternativas).
- `turnos/gestion-panel`: el alta manual se acepta sobre una franja ocupada en Google pero lo avisa (`aviso_google_calendar`) y deja un conflicto para resolver.
- `turnos/agenda-panel`: la agenda muestra las franjas ocupadas en Google y marca los turnos con conflicto de calendario abierto.

## Impact
- **Backend:** módulo nuevo `app/integraciones/gcal/` (modelos, cifrado de tokens, puerto `ProveedorCalendario` con adaptador HTTP `httpx` asíncrono y falso en memoria, servicio de OAuth, reconciliación push/pull, conflictos, router del panel); `app/jobs/registro.py` (trabajo `gcal_sync`); `app/gestion/deps.py` (`NotificadorCalendario` en el compuesto); `app/public/service.py` (franjas ocupadas de Google en la disponibilidad); `app/panel/` (agenda); `app/shared/settings.py` (variables `GCAL_*`); `app/main.py` (router).
- **API:** `GET /api/panel/google-calendar/conexiones`, `POST /api/panel/google-calendar/conexion/iniciar`, `GET /api/panel/google-calendar/oauth/callback`, `DELETE /api/panel/google-calendar/conexiones/{profesional_id}`, `GET /api/panel/google-calendar/conflictos`, `POST /api/panel/google-calendar/conflictos/{id}/resolver`. `GET /api/panel/agenda` suma campos (no rompe al cliente actual). `GET /api/public/...disponibilidad` y la reserva pública rechazan un horario ocupado en Google con el 409 de horario ocupado ya existente.
- **Base de datos:** migración `011_google_calendar`.
- **Dependencias:** `cryptography` (cifrado de tokens, O1). Sin cliente oficial de Google (es síncrono y bloquearía el loop, R16): `httpx` ya está.
- **Infra:** `docker-compose.yml` (variables `GCAL_*` en backend y worker; servicio `gcal-falso` con perfil `e2e`); CI (los jobs E2E del panel y del paciente levantan `gcal-falso`).
- **Frontend:** `frontend-panel/` (sección Google Calendar, aviso y franjas en la agenda). `frontend-paciente/` sin cambios de código (menos horarios ofrecidos).
- **Docs/KB:** `05_reglas_de_negocio.md` (RN-GC-02 con el criterio aprobado, RN-GC-03 nuevas), `04_modelo_de_datos.md` (§EventoCalendar), `08_arquitectura_propuesta.md` (variables), `10_preguntas_abiertas.md` (cierra la de conflictos), README (cómo crear el cliente OAuth en Google Cloud).
- **Fuera de alcance:** notificaciones push de Google (canales `watch`), elegir un calendario que no sea el principal, sincronizar sillones o recepción, reprogramar un turno desde el panel (C-08 O13), importar eventos de Google como turnos.
