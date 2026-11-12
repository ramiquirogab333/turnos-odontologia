# Design: c-09-whatsapp-recordatorios-confirmacion

> Governance **ALTO**: las decisiones no obvias están en la tabla **O1–O18** al final, cada una con opciones y un default recomendado. **Todas fueron APROBADAS por el usuario el 2026-11-11 tal como se recomendaron** (columna Estado); las O19–O23 del apply fueron aprobadas el 2026-11-11. Los specs y `tasks.md` usan esas opciones.

## Context

Motivación en `proposal.md` (Why). Estado actual relevado en el código (rama `feat/c-09-whatsapp-recordatorios-confirmacion`, desde `69d327b`):

- **No hay Redis ni worker.** `docker-compose.yml` tiene solo `postgres` (healthcheck `pg_isready`) y `backend`. `requirements.txt` no tiene cliente Redis ni librería de colas.
- **Barrido de C-06 en la API:** `app/pagos/barrido.py` (`expirar_pre_reservas(session, ahora)` + `ciclo_barrido`) corre como tarea `asyncio` del `lifespan` de `app/main.py`, gobernado por `SENA_BARRIDO_HABILITADO` / `SENA_BARRIDO_SEGUNDOS`. Toma el advisory lock global de reservas y `FOR UPDATE SKIP LOCKED`: ya es idempotente y seguro con varias réplicas. Los E2E dependen de él con `SENA_BARRIDO_SEGUNDOS=3`.
- **Puerto de eventos de C-07:** `app/gestion/eventos.py` (`EventoTurno` sin PII, `NotificadorTurnos`, `NotificadorNulo`), inyectado por `app/gestion/deps.get_notificador` en la gestión pública y en la cancelación del panel; se publica después del commit con `publicar_sin_romper`.
- **Estados y transiciones:** `app/pagos/estados.TRANSICIONES_TURNO` ya admite `reservado → confirmado`; ningún endpoint lo usa todavía. La reprogramación del paciente deja un `confirmado` en `reservado` (C-07 O5) y conserva id y código de gestión. `cambiar_estado_turno` (C-06) aplica transiciones con el orden de locks advisory → turno → pago y reintenta deadlocks.
- **Datos de contacto:** `turno.contacto_telefono` con `CHECK` E.164 (`^\+[1-9][0-9]{1,14}$`); el alta manual del panel exige teléfono; `turno.paciente_id` opcional (C-11). El código de gestión es un UUID (≥ 8 caracteres por `CHECK`).
- **Frontends:** `frontend-paciente` ya tiene `GestionTurno` en `/gestionar#<código>` (código en el fragmento, C-07 O1). `frontend-panel` tiene navegación por hash con secciones por rol (Agenda, Pacientes, Indicadores, Caja).
- **CI** (`.github/workflows/ci.yml`): job de pytest con servicio Postgres (sin Compose); jobs E2E que levantan `postgres` y `backend` con `docker compose up -d --wait`.
- **Última migración:** `009_caja_cierres_devol` (C-12). La siguiente es `010`.

## Goals / Non-Goals

**Goals:**
- Una base de trabajos programados que C-10 reutilice sin rediseño (registrar un trabajo nuevo = una función idempotente + un intervalo).
- Recordatorios que se reconcilian solos a partir del estado del turno: perder un evento nunca deja un recordatorio incorrecto visible.
- WhatsApp manual sin acoplar el dominio a `wa.me`: cambiar a una API paga es cambiar la implementación del proveedor y agregar su webhook.
- Mantener verdes el pytest sin Redis y los E2E existentes.

**Non-Goals:**
- Envío automático, plantillas aprobadas por Meta, webhook de WhatsApp (O4).
- Una cola de mensajes de propósito general u outbox de eventos (O8).
- Rate limiting de endpoints públicos (O13, va a C-15).
- Barrido automático de pagos `en_revision` (O12).

## Decisions

### D1. Redis + worker en Compose (O1, O11)
- Servicio `redis` (`redis:7-alpine`, healthcheck `redis-cli ping`, sin puerto publicado al host salvo para depurar) y servicio `worker` con la **misma imagen del backend** y otro comando (`python -m app.jobs.worker` o el CLI de la librería), `depends_on` `postgres` y `redis` con `condition: service_healthy`. Healthcheck del worker: la verificación de vida que ofrezca la librería (en arq, `arq --check`), o una clave de latido en Redis con TTL.
- Librería recomendada: **arq** (asyncio nativo, cron por segundos, reintentos con `Retry(defer=…)`, una dependencia chica sobre `redis`). Versión fijada en el apply con `pip install --dry-run` como en C-01 D8. Riesgo: arq está en modo mantenimiento; alternativas en O1.
- **La API no depende de Redis** (O8): el backend no gana `depends_on: redis`; solo el worker lo usa. Eso mantiene intactos el job de pytest y la API si Redis cae.
- Registro de trabajos en `app/jobs/registro.py`: cada trabajo es `async def trabajo(session, ahora) -> int` (pura respecto del reloj, testeable con Postgres y sin Redis) envuelta por un adaptador que abre la sesión, captura y loguea errores sin PII y nunca mata al worker.
- **Barrido de C-06:** el worker llama a `expirar_pre_reservas` sin cambios. El `lifespan` solo arranca `ciclo_barrido` si `SENA_BARRIDO_EN_API=true` (default `false`); los tests de pytest que lo cubren siguen llamando la función directamente. En Compose la API queda sin barrido y el worker lo hace.

### D2. Modelo `Recordatorio` (migración `010_recordatorios`, O7)
Tabla `recordatorio` (`postgresql-table-design`):

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` PK | |
| `turno_id` | `BIGINT NOT NULL` FK `turno(id) ON DELETE RESTRICT` | índice propio (R6) |
| `canal` | `TEXT NOT NULL DEFAULT 'whatsapp'` | `CHECK (canal IN ('whatsapp'))` |
| `estado` | `TEXT NOT NULL` | `CHECK IN ('pendiente','enviado','confirmado','fallido','anulado')` |
| `turno_inicio` | `TIMESTAMPTZ NOT NULL` | horario del turno que se recuerda (foto) |
| `generado_en` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |
| `enviado_en` | `TIMESTAMPTZ NULL` | la "fecha_envío" de la KB; último envío |
| `enviado_por_usuario_id` | `BIGINT NULL` FK `usuario(id)` | índice propio (R6) |
| `confirmado_en` | `TIMESTAMPTZ NULL` | |
| `intentos_fallidos` | `INTEGER NOT NULL DEFAULT 0` | `CHECK (>= 0)` |
| `proximo_intento_en` | `TIMESTAMPTZ NULL` | solo con reintento programado |
| `motivo` | `TEXT NULL` | `CHECK IN ('sin_telefono','numero_invalido','sin_whatsapp','otro','error_proveedor','turno_cancelado','turno_reprogramado','turno_iniciado')` |
| `ultimo_error` | `TEXT NULL` | `CHECK (LENGTH <= 500)`, sanitizado |
| `created_at`/`updated_at` | `TIMESTAMPTZ` | mixin existente |

Constraints: `UNIQUE (turno_id, turno_inicio) WHERE estado <> 'anulado'` (índice único parcial: un vigente por horario, permite volver a un horario anulado); coherencia por `CHECK`: `estado = 'confirmado' ⇔ confirmado_en IS NOT NULL`, `estado = 'enviado' ⇒ enviado_en IS NOT NULL`, `estado IN ('fallido','anulado') ⇒ motivo IS NOT NULL`. Índice parcial de trabajo `(proximo_intento_en) WHERE proximo_intento_en IS NOT NULL` y `(estado, turno_inicio) WHERE estado IN ('pendiente','fallido')` para el listado. El mensaje **no se guarda** (PII y siempre recalculable). `downgrade` borra la tabla (se pierde el historial de recordatorios; documentado).

### D3. Trabajo de recordatorios (O5, O6, O9)
Un ciclo, en una transacción corta por lote, con `ahora` inyectado:
1. **Reconciliar:** pasa a `anulado` los recordatorios `pendiente`/`enviado`/`fallido` cuyo turno está `cancelado` (motivo `turno_cancelado`), cuyo `turno_inicio ≠ turno.inicio` (`turno_reprogramado`) o, solo si `pendiente`/`fallido`, cuyo turno ya empezó (`turno_iniciado`). Un turno `ausente` o `atendido` conserva su recordatorio `enviado`/`confirmado` como historial (hallazgo del auditor).
2. **Generar:** `INSERT … SELECT` de turnos `estado = 'reservado'` con `ahora < inicio ≤ ahora + REMINDER_LEAD_TIME` sin recordatorio vigente para ese `inicio`, con `ON CONFLICT DO NOTHING` sobre el índice único parcial (idempotencia ante workers concurrentes, sin lock global). Sin teléfono E.164 (turno, o paciente vinculado) → nace `fallido` `sin_telefono`.
3. **Procesar con el proveedor:** para cada `pendiente` nuevo o con `proximo_intento_en ≤ ahora`, `ProveedorWhatsApp.procesar(datos)`. `manual` devuelve `requiere_accion_manual` (sigue `pendiente`). Error transitorio → `intentos_fallidos += 1`, `proximo_intento_en = ahora + [1, 5, 15][n-1] min`; al tercero, `fallido` `error_proveedor` (O10).
4. Log solo con cantidades por paso.

El trabajo no genera para `confirmado` (O6): quien ya confirmó no necesita aviso, y el reprogramado vuelve a `reservado` (C-07 O5).

### D4. Proveedor y mensaje (O14, O15, O16)
- `app/notificaciones/proveedor.py`: `Protocol ProveedorWhatsApp` + `ProveedorManual`; un `ProveedorFalso` configurable solo en tests. Selección por `WHATSAPP_PROVEEDOR` (`manual` único valor válido fuera de test).
- `app/notificaciones/mensaje.py` (puro): `armar_mensaje(datos, zona, base_url, clinica)` y `link_wa_me(telefono_e164, texto)` → `https://wa.me/<dígitos>?text=<quote(texto, safe='')>`. Plantilla fija en español, día y hora con `APP_TZ`, `CLINICA_NOMBRE` desde el entorno. Dos enlaces: `/confirmar#<código>` y `/gestionar#<código>`; un turno del alta interna sin código (`POST /api/turnos`) recibe el mensaje sin enlaces, pidiendo responder (hallazgo del auditor). El teléfono se usa tal cual (sin insertar el `9` de móviles AR, O16).
- El link se arma **al responder** el listado del panel; nunca se persiste ni se loguea.

### D5. Confirmación (O3, O18)
- `POST /api/public/gestion/confirmar` en el router de gestión, mismo `CodigoGestion` por cabecera y mismo 404 genérico. Servicio `confirmar_turno_publico(session, codigo, ahora)`: resuelve el id, valida (en orden) estado final → `turno_no_modificable`, `en_espera` → `sena_pendiente`, `confirmado` → 200 idempotente, `inicio ≤ ahora` → `turno_iniciado`; aplica `cambiar_estado_turno(…, "confirmado", None, origen="confirmacion_paciente")` y, en la misma transacción, pasa el recordatorio vigente del `inicio` actual a `confirmado` con `confirmado_en`. Sin evento de calendario (el horario no cambió).
- `MotivoNoModificable` suma `turno_iniciado`; `GestionTurnoResponse` suma `puede_confirmar` y `motivo_no_confirmable` (`ya_confirmado` además de los anteriores). No rompe al frontend actual (campos nuevos).
- No exige recordatorio previo (O18) ni 24 h: confirmar no libera ni mueve horario.

### D6. Implementación de `NotificadorTurnos` (O8)
`NotificadorRecordatorios.publicar(evento)`: en una sesión propia post-commit anula los recordatorios vigentes del turno con `turno_inicio = evento.inicio_anterior` (motivo según `evento.tipo`). Es una sola `UPDATE` liviana (no bloquea el loop, R16). `get_notificador` lo devuelve (envuelto en un `NotificadorCompuesto` para que C-10 sume el suyo). Si falla, `publicar_sin_romper` lo loguea y el paso 1 de D3 lo corrige en el próximo ciclo. El listado del panel filtra además por `turno_inicio = turno.inicio` y estado bloqueante, así un recordatorio viejo nunca se muestra aunque la anulación no haya corrido.

### D7. API y pantallas del panel (O2, O17)
- `app/notificaciones/router.py`, `prefix=/api/panel/recordatorios`, `Depends(require_recepcion_o_admin)` (patrón de `app/caja/router.py`): `GET ""` (`estado` múltiple opcional, default `pendiente,fallido`), `POST /{id}/enviado`, `POST /{id}/fallido` (body `{motivo}` con `Literal`). Pydantic in/out (R15), errores `404`, `409 recordatorio_no_vigente`, `422`. Cada escritura deja `RegistroAuditoria` (entidad `recordatorio`, estados antes/después, sin PII).
- `frontend-panel`: sección `#recordatorios` en `Navegacion` solo para recepción/admin; componente `Recordatorios` con lista por día; "Abrir WhatsApp" es un `<a href={link} target="_blank" rel="noopener noreferrer">` cuyo `onClick` dispara `POST …/enviado` sin bloquear la apertura (la pestaña se abre aunque la marca falle; la fila muestra el error y permite reintentar). Estado vacío "No hay recordatorios por enviar". TS estricto (R1), sin cascadas (R2), 360 px (R3).
- `frontend-paciente`: ruta `/confirmar` con componente `ConfirmarTurno` que reutiliza el cliente de gestión (`GET /api/public/gestion` → muestra datos; botón → `POST …/confirmar`), y enlace a `/gestionar#<código>`.

### D8. Configuración (R17)
Nuevas variables (en `Settings` y Compose, sin secretos): `REDIS_URL` (`redis://redis:6379/0`), `REMINDER_LEAD_TIME` (horas, `48` por defecto, acepta `48h`), `RECORDATORIOS_HABILITADO` (`true`), `RECORDATORIOS_INTERVALO_SEGUNDOS` (`300`, `>0`), `WHATSAPP_PROVEEDOR` (`manual`), `CLINICA_NOMBRE` (`la clínica`), `SENA_BARRIDO_EN_API` (`false`). `PUBLIC_BASE_URL` ya existe. `WHATSAPP_API_TOKEN` / `WHATSAPP_SENDER` de la KB no se introducen (v1 manual).

### D9. Estrategia de pruebas (Strict TDD) y CI
- **Unit (sin DB):** `mensaje.py` (formato, zona, codificación, fragmento), backoff, motivos de confirmación, parseo de settings.
- **Integración (Postgres, sin Redis):** migración 010 (upgrade/downgrade, constraints, índice único parcial), trabajo de recordatorios con `ahora` fijo (bloqueantes, en_espera, borde de 48 h, tarde, iniciado, sin teléfono, reconciliación, concurrencia con dos sesiones), proveedor falso con fallas, notificador, endpoints del panel (RBAC 401/403, 404/409/422, auditoría), confirmación pública.
- **Worker:** test de que el registro expone ambos trabajos con sus intervalos y de que el adaptador traga excepciones; el arranque real se prueba en CI E2E.
- **E2E Playwright (R7):** paciente 360 px: confirmar desde `/confirmar#…`, pre-reserva sin botón; panel 360 px: aparece el recordatorio, `href` `wa.me` con el mensaje sintético, "Abrir WhatsApp" marca enviado, cancelar desde la gestión lo saca de la lista. Los jobs E2E levantan `postgres redis` y luego `backend worker` con `RECORDATORIOS_INTERVALO_SEGUNDOS=3` y `SENA_BARRIDO_SEGUNDOS=3` en el worker (los E2E de vencimiento de C-06 pasan a depender del worker).

## Risks / Trade-offs

- **[Recepción no abre los links]** → los recordatorios quedan `pendiente`. *Mitigación:* la sección muestra cuántos faltan; métrica para decidir la migración a API.
- **["Enviado" = abrió WhatsApp, no entrega real]** → puede marcarse sin mandar el mensaje. *Mitigación:* aceptado en v1 (O2); "No se pudo enviar" corrige.
- **[Link de confirmación reenviado a terceros]** → quien tenga el código puede confirmar o cancelar. *Mitigación:* igual que C-07 (código de 122 bits en el fragmento, auditoría); confirmar es reversible por recepción cancelando; rate limiting en C-15.
- **[Confirmación con un mensaje viejo después de reprogramar]** → el código es el mismo, se confirma el horario nuevo. *Mitigación:* la pantalla muestra el día y la hora actuales antes del botón.
- **[Teléfonos AR sin el 9 de móvil]** → `wa.me` puede no encontrar el número. *Mitigación:* O16; recepción marca `numero_invalido`.
- **[arq en modo mantenimiento]** → *Mitigación:* el dominio no depende de la librería (trabajos = funciones `(session, ahora)`); cambiarla toca solo `app/jobs/worker.py` (O1).
- **[Los E2E de vencimiento de C-06 pasan a depender del worker]** → *Mitigación:* CI levanta el worker; para desarrollo sin Redis, `SENA_BARRIDO_EN_API=true`.
- **[Turno que nunca recibe recordatorio si el worker estuvo caído hasta su inicio]** → *Mitigación:* healthcheck del worker y log; el trabajo genera apenas vuelve mientras el turno no haya empezado.

## Migration Plan

1. Verificar con `ls backend/src/alembic/versions` que `010` sigue libre (C-10, C-14 o C-15 pueden correr en paralelo) y aplicar `alembic upgrade head`.
2. Desplegar con `docker compose up -d --wait postgres redis` → `backend worker`. Sin `SENA_BARRIDO_EN_API`, el barrido pasa de la API al worker en el mismo despliegue (no hay ventana sin barrido si ambos se actualizan juntos; si se despliega solo la API, poner `SENA_BARRIDO_EN_API=true` hasta levantar el worker).
3. Rollback: bajar `worker` y `redis`, volver la API con `SENA_BARRIDO_EN_API=true` y `alembic downgrade 009_caja_cierres_devol` (borra la tabla `recordatorio`; los turnos no se tocan: un `confirmado` sigue siendo un estado válido de C-06).

## Auditoría de reglas de negocio (`spec-rules-auditor`, 2026-11-11)

**Dictamen: OBSERVACIONES** (sin bloqueos; dos gaps corregidos en los specs, tres supuestos que dependen de O5, O6 y O9).

| Regla | Descripción breve | Estado | Observación / dónde |
|---|---|---|---|
| RN-WA-01 | Todo turno genera recordatorio | CUBIERTA con SUPUESTO | Todo `reservado` (incluido el alta manual sin seña y el reservado tarde, O9). `confirmado` no recibe (O6): interpretación "todo turno que todavía no confirmó" **[SUPUESTO / ABIERTO]** |
| RN-WA-02 | Confirmar por botón → `confirmado` | CUBIERTA | `gestion-paciente` "Confirmación de asistencia…" + "La confirmación… cierra el recordatorio"; botón como link + `POST` (O3) |
| RN-WA-03 | Manual v1 `wa.me`, sin API; `en_espera` no recibe | CUBIERTA | "Link de WhatsApp…", "Reintentos…" (proveedor manual), "Solo los turnos reservados…" escenario 2 |
| R8 / RN-SN-01 | `en_espera` no bloquea ni notifica | CUBIERTA | Sin recordatorio y sin confirmación (`sena_pendiente`) |
| RN-TU-01 / RN-SN-04 | Cancelar con ≥ 24 h, seña `a_reembolsar` | CUBIERTA (reutilizada de C-07) | "Cancelar o reprogramar anula…" escenarios 1–2; no se duplica la regla |
| C-07 O5 | Confirmado reprogramado vuelve a `reservado` | CUBIERTA | Escenario "Reprogramación con el publicador caído" |
| RN-SN-07 | Vencimiento de pre-reservas | CUBIERTA | `plataforma/trabajos-programados` "El barrido… corre en el worker" |
| RN-GL-01 | Acciones auditadas | CUBIERTA | Auditoría de envío/fallido y de la confirmación |
| R3 / R7 | 360 px y E2E | CUBIERTA | Pantallas de confirmación y de recordatorios; tareas 11.2–11.3 |
| R4 / R6 / R14 | Tipos, FK indexadas, migración reversible | CUBIERTA | D2, tareas 2.1–2.4 |
| R16 / R17 / R18 | Trabajo pesado en worker, secretos fuera, Compose con healthcheck | CUBIERTA | `plataforma/trabajos-programados`, D1, D8 |
| R19 | Sin PII en logs; datos sintéticos | CUBIERTA | "Recordatorios sin datos personales…"; todos los ejemplos sintéticos |
| R9 / RN-TU-12 | Ausente retiene seña; marcado ausente/atendido | NO AFECTADA | El recordatorio no cambia la seña; se agregó que ausente/atendido no anulan el historial |
| KB 08 `REMINDER_LEAD_TIME=24h` | Ejemplo de anticipación | CONTRADICHA por O5 | Default 48 h propuesto **[SUPUESTO / ABIERTO]**, requiere OK del PO |

**Gaps detectados y corregidos en los specs:**
1. Un turno del alta interna (`POST /api/turnos`) es `reservado` pero no tiene código de gestión: el mensaje habría tenido enlaces rotos. → Nuevo escenario "Turno interno sin código de gestión" y texto del requisito del link.
2. La reconciliación anulaba también los recordatorios `enviado` de turnos luego `ausente`/`atendido`, perdiendo historial (útil para medir ausentismo con recordatorio). → Solo la cancelación y la reprogramación anulan; escenario "Turno atendido o ausente conserva el historial".

**Riesgos que quedan para la revisión:** confirmación con un mensaje viejo tras reprogramar (mitigado mostrando el horario actual); "enviado" no garantiza entrega (O2); teléfonos AR sin `9` (O16).

**Terna canónica (ya incluida en los specs):**
- *Esperado:* GIVEN turno 101 `reservado` a 30 h, WHEN corre el trabajo, THEN un recordatorio `pendiente`; WHEN el paciente confirma con su código, THEN turno y recordatorio `confirmado`.
- *Error de negocio:* GIVEN turno 102 `en_espera`, WHEN corre el trabajo o se intenta confirmar, THEN sin recordatorio y 409 `sena_pendiente`.
- *Borde:* GIVEN turno a exactamente 48 h (y otro a 48 h 1 min), WHEN corre el trabajo, THEN solo el primero recibe recordatorio; GIVEN confirmación en el instante exacto del inicio, THEN 409 `turno_iniciado`.

## Decisiones (O1–O18) — aprobadas por el usuario el 2026-11-11

| # | Decisión | Opciones | Recomendación (default de specs y tasks) | Estado |
|---|---|---|---|---|
| O1 | Librería del worker | (a) arq; (b) saq; (c) taskiq + scheduler; (d) loop `asyncio` propio con lock en Redis | **(a)** asyncio nativo, cron por segundos, reintentos, mínima. Si se prefiere una librería con mantenimiento activo, (b) con el mismo diseño. | Aprobada 2026-11-11 (recomendación) |
| O2 | Qué significa `enviado` en manual v1 | (a) se marca al tocar "Abrir WhatsApp"; (b) botón aparte "Ya lo envié"; (c) no existe, solo `pendiente`/`confirmado` | **(a)** un toque por paciente; "No se pudo enviar" corrige. | Aprobada 2026-11-11 (recomendación) |
| O3 | Cómo confirma el paciente | (a) página `/confirmar#código` + `POST /api/public/gestion/confirmar` al tocar el botón; (b) un GET que confirma al abrir el link; (c) webhook de WhatsApp | **(a)** (b) lo dispararían las vistas previas; (c) exige API paga. | Aprobada 2026-11-11 (recomendación) |
| O4 | `POST /api/webhooks/whatsapp` en v1 | (a) no se implementa, queda el puerto de proveedor; (b) endpoint que responde 501 | **(a)** sin proveedor no hay quién lo llame; se agrega con la migración a API. | Aprobada 2026-11-11 (recomendación) |
| O5 | Anticipación por defecto (`REMINDER_LEAD_TIME`) | (a) 24 h (KB); (b) 48 h; (c) dos recordatorios (48 h y 3 h) | **(b)** con 24 h el link de cancelar casi siempre cae fuera de la ventana de 24 h de C-07. Cambia el ejemplo de la KB 08: requiere OK del PO. | Aprobada 2026-11-11 (recomendación) |
| O6 | Estados que reciben recordatorio | (a) solo `reservado`; (b) `reservado` y `confirmado` | **(a)** un `confirmado` ya respondió; el reprogramado vuelve a `reservado`. | Aprobada 2026-11-11 (recomendación) |
| O7 | Historial de recordatorios | (a) estado nuevo `anulado` + foto `turno_inicio`; (b) borrar los obsoletos | **(a)** trazabilidad y permite un vigente por horario. Agrega un estado a los 4 de la KB 04. | Aprobada 2026-11-11 (recomendación) |
| O8 | Reacción a cancelar/reprogramar | (a) anulación post-commit en DB + reconciliación del trabajo + filtro del listado; (b) encolar en Redis; (c) tabla outbox | **(a)** liviana, la API no depende de Redis y el estado del turno es la fuente de verdad (C-07 O8). | Aprobada 2026-11-11 (recomendación) |
| O9 | Turno reservado ya dentro de la anticipación | (a) recordar mientras no empezó; (b) no recordar si faltan menos de X horas; (c) no recordar | **(a)** cumple RN-WA-01 ("todo turno"); al empezar se anula. | Aprobada 2026-11-11 (recomendación) |
| O10 | Reintentos en v1 manual | (a) máquina de reintentos 1/5/15 min y 3 intentos, probada con proveedor falso; `sin_telefono` sin reintento; (b) solo `fallido` manual | **(a)** cumple el done-criteria de CHANGES y queda lista para la API. | Aprobada 2026-11-11 (recomendación) |
| O11 | Barrido de pre-reservas | (a) al worker; la API solo con `SENA_BARRIDO_EN_API=true`; (b) queda en la API | **(a)** es la consolidación pedida por C-06 D8; evita dobles barridos con réplicas. | Aprobada 2026-11-11 (recomendación) |
| O12 | Barrido de `en_revision` vencidos (C-12 O6 b) | (a) fuera de C-09; (b) incluirlo como trabajo | **(a)** necesita una regla de negocio (plazo y destino) que no existe; la base queda lista. | Aprobada 2026-11-11 (recomendación) |
| O13 | Rate limiting de endpoints públicos con Redis | (a) diferir a C-15; (b) incluirlo en gestión/confirmar | **(a)** C-15 es obligatorio antes de producción y concentra el endurecimiento. | Aprobada 2026-11-11 (recomendación) |
| O14 | Enlaces en el mensaje | (a) dos: `/confirmar#c` y `/gestionar#c`; (b) uno solo a `/gestionar#c` con botón de confirmar | **(a)** coincide con "botones confirmar / cancelar" del Flujo 3. | Aprobada 2026-11-11 (recomendación) |
| O15 | Texto del mensaje | (a) plantilla fija en código con `CLINICA_NOMBRE`; (b) plantilla editable por el admin | **(a)** (b) suma tabla y pantalla; se puede agregar después sin cambiar el modelo. | Aprobada 2026-11-11 (recomendación) |
| O16 | Teléfonos móviles AR (`+54` sin `9`) | (a) usar el E.164 tal cual; (b) insertar el `9` | **(a)** normalizar mal es peor; recepción marca `numero_invalido`. Revisar con datos reales de la clínica. | Aprobada 2026-11-11 (recomendación) |
| O17 | Dónde opera recepción | (a) sección nueva "Recordatorios"; (b) un ícono por turno en la agenda | **(a)** lista de trabajo del día, sin recargar la agenda; la agenda ya muestra `confirmado`. | Aprobada 2026-11-11 (recomendación) |
| O18 | ¿Confirmar exige un recordatorio previo? | (a) no, cualquier `reservado` no iniciado; (b) solo con recordatorio vigente | **(a)** el paciente puede confirmar desde la gestión en cualquier momento. | Aprobada 2026-11-11 (recomendación) |

## Decisiones surgidas en el apply (PENDIENTES de confirmación)

> Las tomó el apply con la opción más conservadora porque no estaban cubiertas por O1–O18. El usuario las confirma o las cambia.

| # | Decisión | Qué se hizo | Estado |
|---|---|---|---|
| O19 | Semántica de los reintentos del proveedor (spec: "1, 5 y 15 minutos y, agotado el tercer reintento, `fallido`") | Un intento inicial más tres reintentos (a +1, +5 y +15 min): son 4 llamadas y `intentos_fallidos` = 4 al quedar `fallido` (`error_proveedor`). Alternativa: parar en el tercer fallo (3 llamadas, la espera de 15 min no se usaría). | Aprobada 2026-11-11 (recomendación) |
| O20 | Cierre del recordatorio al confirmar | La confirmación pública lo marca `confirmado` después del commit del cambio de estado (no en la misma transacción: `cambiar_estado_turno` hace commit propio). Si falla, el paso de reconciliación del ciclo lo corrige (un turno `confirmado` con recordatorio abierto del mismo horario pasa a `confirmado`). | Aprobada 2026-11-11 (recomendación) |
| O21 | Un `confirmado` cuyo turno se cancela o reprograma | Pasa a `anulado` (`turno_cancelado`/`turno_reprogramado`) y se limpia `confirmado_en` (el `CHECK` exige `confirmado ⇔ confirmado_en`), como pide el escenario "Reprogramación con el publicador caído". | Aprobada 2026-11-11 (recomendación) |
| O22 | Listado del panel | Pide `pendiente`, `fallido` y `enviado` (los enviados en una sección aparte, para ver el "Enviado" y poder reenviar); el endpoint por defecto devuelve solo `pendiente` y `fallido`. Solo turnos `reservado`/`confirmado` que empiezan en `(ahora, ahora + anticipación]`. | Aprobada 2026-11-11 (recomendación) |
| O23 | Librería y versiones | `arq==0.28.0` con `redis==5.3.1` (arq 0.28 exige `redis<6`). Intervalos que no dividen la unidad (cron) se redondean al divisor más cercano hacia abajo. `SENA_BARRIDO_SEGUNDOS` ahora exige `> 0`. | Aprobada 2026-11-11 (recomendación) |
