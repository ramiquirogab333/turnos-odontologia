# Proposal: c-09-whatsapp-recordatorios-confirmacion

## Why
Hoy un turno `reservado` no avisa nada a la o el paciente antes de la fecha: no hay recordatorio ni forma de confirmar asistencia (US-004, RN-WA-01, RN-WA-02), y el ausentismo es la métrica que el consultorio quiere bajar. Además, el proyecto todavía no tiene la base de trabajos programados que el roadmap asignó a C-09: el barrido de pre-reservas vencidas de C-06 corre como tarea `asyncio` dentro de la API (C-06 D8, "C-09 lo consolida"), C-07 dejó el puerto `NotificadorTurnos` con una implementación nula esperando a C-09, y C-10 (Google Calendar) va a reutilizar esta base.

La Resolución 2026-09-30 nº2 fija WhatsApp **MANUAL en v1** (RN-WA-03): sin API paga, links `wa.me/` con el mensaje armado. Eso cambia el sentido de "enviar", "webhook" y "reintentos" respecto del texto original de CHANGES.md; este change lo resuelve y deja las alternativas como decisiones abiertas en `design.md` (O1–O18).

## What Changes
- **Base de trabajos programados (R16, R18):** Redis y un servicio `worker` en Docker Compose, ambos con healthcheck; el worker corre los trabajos periódicos (librería a confirmar, O1). El barrido de pre-reservas vencidas de C-06 se mueve al worker sin cambiar su servicio (`expirar_pre_reservas`) y la tarea del `lifespan` queda solo detrás de una bandera para desarrollo y tests (O11).
- **Recordatorios (Flujo 3):** un trabajo periódico genera un `Recordatorio` `pendiente` por cada turno `reservado` que empieza dentro de la anticipación configurada (`REMINDER_LEAD_TIME`, 48 h por defecto, O5) y todavía no tiene uno para ese horario. Un turno `en_espera` nunca recibe recordatorio (R8, RN-WA-03); el alta manual `reservado` sin seña sí (RN-WA-01).
- **WhatsApp manual v1:** detrás de un puerto de proveedor (`ProveedorWhatsApp`) la implementación `manual` no envía nada: deja el recordatorio esperando a recepción. El panel arma el link `https://wa.me/<teléfono>?text=<mensaje>` con el día y la hora en hora de la clínica, la profesional, el tratamiento y dos enlaces con el código de gestión en el fragmento: `/confirmar#<código>` y `/gestionar#<código>` (O14). El mensaje no se guarda en la base.
- **"Enviado" en v1 (O2):** el recordatorio pasa a `enviado` cuando recepción toca "Abrir WhatsApp" en el panel (queda quién y cuándo). Si el número no tiene WhatsApp, recepción lo marca "No se pudo enviar" (`fallido` con motivo).
- **Confirmación sin webhook (O3, O4):** `POST /api/public/gestion/confirmar` (código en la cabecera `X-Codigo-Gestion`, como C-07) pasa un `reservado` a `confirmado` y marca el recordatorio vigente como `confirmado` (RN-WA-02). La pantalla `/confirmar#<código>` exige tocar "Confirmar asistencia", así una vista previa del link nunca confirma sola. `POST /api/webhooks/whatsapp` **no se implementa en v1**: queda para cuando se migre a la API de WhatsApp.
- **Cancelar desde el recordatorio:** el enlace `/gestionar#<código>` es la pantalla de C-07; la ventana de 24 h, la seña `a_reembolsar` y los eventos se reutilizan sin duplicarse.
- **Cancelación y reprogramación:** C-09 implementa `NotificadorTurnos`: al cancelar o reprogramar se anulan los recordatorios del horario anterior (estado nuevo `anulado`, O7) y el trabajo genera uno nuevo para el horario nuevo. El trabajo además reconcilia solo cualquier recordatorio que haya quedado viejo (O8).
- **Fallos y reintentos (O10):** turno sin teléfono válido → `fallido` inmediato con motivo `sin_telefono`. Un error transitorio del proveedor se reintenta con espera creciente (1, 5 y 15 minutos) y al tercer fallo queda `fallido` con el error registrado sin datos personales. En v1 esto se ejercita con un proveedor falso en los tests; el proveedor manual no falla.
- **Panel (`frontend-panel/`):** sección nueva "Recordatorios" para recepción y admin (O17), a 360 px (R3): turnos por avisar, con estado y los botones "Abrir WhatsApp" y "No se pudo enviar". La odontóloga no la ve (no ve teléfonos, C-08).
- **Frontend del paciente:** pantalla "Confirmar asistencia" a 360 px.
- **Migración `010_recordatorios`** (reversible, R14): tabla `recordatorio` con FK indexadas (R6), instantes `TIMESTAMPTZ` y textos con `CHECK` (R4).
- **E2E Playwright (R7):** confirmación desde el celular, rechazo de una pre-reserva, link `wa.me` con el mensaje correcto en el panel y el recordatorio anulado al cancelar.
- **Decisiones a confirmar:** O1–O18 en `design.md`, cada una con un default recomendado; los specs usan esos defaults.

## Capabilities

### New Capabilities
- `notificaciones/recordatorios-whatsapp`: recordatorios por WhatsApp manual v1: qué turnos los reciben, el ciclo de estados del `Recordatorio`, el link `wa.me` y su mensaje, la operación desde el panel, la anulación al cancelar o reprogramar, los fallos y reintentos, y la pantalla del panel a 360 px.
- `plataforma/trabajos-programados`: la base de trabajos periódicos: Redis y worker en Docker Compose con healthcheck, ejecución periódica idempotente aunque haya más de un worker, un fallo que no detiene al worker, y el barrido de pre-reservas vencidas corriendo en el worker.

### Modified Capabilities
- `turnos/gestion-paciente`: se agrega la confirmación de asistencia con el código de gestión (endpoint y pantalla a 360 px). La cancelación y la reprogramación no cambian.

## Impact
- **Backend:** módulo nuevo `app/notificaciones/` (modelo, servicio de generación y reconciliación, proveedor manual y puerto, mensaje y link, router del panel); `app/jobs/` (worker y registro de trabajos); `app/gestion/` (confirmación, `get_notificador` devuelve la implementación de C-09); `app/main.py` (router, el barrido sale del `lifespan` por defecto); `app/shared/settings.py` (`REDIS_URL`, `REMINDER_LEAD_TIME`, intervalo del trabajo, `CLINICA_NOMBRE`, bandera del barrido).
- **API:** `POST /api/public/gestion/confirmar`; `GET /api/panel/recordatorios`, `POST /api/panel/recordatorios/{id}/enviado`, `POST /api/panel/recordatorios/{id}/fallido`. Ningún contrato existente cambia, salvo un motivo nuevo (`turno_iniciado`) en las respuestas 409 de gestión.
- **Base de datos:** migración `010_recordatorios`.
- **Infra:** `docker-compose.yml` (servicios `redis` y `worker`), `requirements.txt` (cliente Redis y librería de trabajos), CI (los jobs E2E levantan `redis` y `worker`; el job de pytest no necesita Redis).
- **Frontend:** `frontend-panel/` (sección Recordatorios), `frontend-paciente/` (pantalla de confirmación).
- **Docs/KB:** `04_modelo_de_datos.md` (§Recordatorio), `05_reglas_de_negocio.md` (RN-WA con las decisiones aprobadas), `08_arquitectura_propuesta.md` (variables de entorno), README.
- **Fuera de alcance:** API paga de WhatsApp y su webhook, Google Calendar (C-10), barrido automático de pagos `en_revision` (C-12 O6 b, O12), rate limiting de los endpoints públicos (C-15, O13), mover la preferencia de Mercado Pago fuera del lock y la conciliación periódica con Mercado Pago (seguimientos de C-06), plantilla del mensaje editable por el admin.
