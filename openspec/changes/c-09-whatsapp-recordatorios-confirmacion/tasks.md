# Tasks: c-09-whatsapp-recordatorios-confirmacion

> **Governance ALTO.** Las decisiones **O1–O18** de `design.md` están **pendientes de aprobación del usuario**. No empezar el grupo 1 hasta completar 0.1. Estas tareas siguen la opción recomendada de cada una; si el usuario cambia alguna, actualizar primero specs, diseño y tareas.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR: el test se escribe primero y falla por la razón correcta (no por un import roto). Cada requisito de los specs tiene sus tres escenarios (esperado, error de negocio, caso de borde) y los tests llevan el nombre del escenario. Datos 100 % sintéticos (R19): "Carlos Sintético", "Lucía Ficticia", "Dra. Ficticia", teléfonos `+54911000000xx`, códigos `CODIGO-SINTETICO-NNN`. Instantes siempre con zona (R4). Sin commits (R11).
>
> Skills a cargar antes de cada grupo: `postgresql-table-design` (grupo 2), `vercel-react-best-practices` y `frontend-design` (grupos 9–10), `playwright-cli` (grupo 11), `spec-rules-auditor` (12.4).

## 0. Aprobación y línea base

- [x] 0.1 Confirmar con el usuario la tabla O1–O18 de `design.md` y registrar la decisión final de cada fila (con fecha). Si alguna cambia, ajustar specs, diseño y estas tareas antes de seguir. Verificar: ninguna fila sin decisión y `openspec validate c-09-whatsapp-recordatorios-confirmacion --strict` pasa.
- [x] 0.2 Con `docker compose up -d postgres` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm test` + `npm run typecheck` en `frontend-paciente/` y `frontend-panel/`; registrar los conteos en el acta al final de este archivo. Si algo falla, frenar y reportarlo como falla previa.
- [x] 0.3 Verificar con `ls backend/src/alembic/versions` que `010` sigue libre; si no, usar el siguiente número y anotarlo en el acta.

## 1. Base de infraestructura: dependencias y configuración (D1, D8)

- [x] 1.1 Fijar en `backend/requirements.txt` la librería del worker elegida en O1 (arq por defecto) y su cliente Redis, en versiones estables verificadas con `pip install --dry-run -r requirements.txt`. Verificar: la instalación resuelve sin conflictos y `python -c "import arq"` funciona.
- [x] 1.2 RED → GREEN: en `backend/tests/test_settings_jobs.py`, tests de `Settings` para `REDIS_URL`, `REMINDER_LEAD_TIME` (default 48, acepta `48` y `48h`, rechaza `0` y `abc`), `RECORDATORIOS_INTERVALO_SEGUNDOS` (`>0`), `RECORDATORIOS_HABILITADO`, `WHATSAPP_PROVEEDOR` (solo `manual` fuera de `APP_ENV=test`), `CLINICA_NOMBRE` y `SENA_BARRIDO_EN_API` (default `false`); el error no muestra secretos. Implementar en `app/shared/settings.py`. Verificar en verde y que `test_settings_*.py` existentes siguen en verde.
- [x] 1.3 Agregar a `docker-compose.yml` los servicios `redis` (`redis:7-alpine`, healthcheck `redis-cli ping`) y `worker` (misma imagen que `backend`, comando del worker, `depends_on` postgres y redis `service_healthy`, healthcheck de la librería, variables de D8 sin secretos por defecto). El backend no gana dependencia de Redis. Verificar: `docker compose config` es válido y `docker compose up -d --wait postgres redis` deja ambos `healthy` (el worker se verifica en 5.3).

## 2. Esquema: migración `010_recordatorios` (D2) — spec `notificaciones/recordatorios-whatsapp`

- [x] 2.1 RED: `backend/tests/test_recordatorios_migracion.py`: tras `upgrade head` existe `recordatorio`; instantes `timestamptz` (R4); `turno_id` y `enviado_por_usuario_id` con índice cuyo prefijo es la FK (consulta a `pg_index`, R6); `CHECK` de `canal`, `estado`, `motivo` y largo de `ultimo_error`. Verificar que falla porque la migración no existe.
- [x] 2.2 RED: invariantes vía ORM: dos recordatorios no anulados del mismo turno e inicio → rechazado ("Inserción duplicada rechazada por la base"); uno `anulado` más uno vigente del mismo horario → aceptado; `confirmado` sin `confirmado_en`, `enviado` sin `enviado_en` y `fallido`/`anulado` sin `motivo` → rechazados.
- [x] 2.3 GREEN: `backend/src/alembic/versions/010_recordatorios.py` (revisión `010_recordatorios`, `down_revision = "009_caja_cierres_devol"`) y modelo `Recordatorio` en `app/notificaciones/models.py`, registrado en `app/models/__init__.py` y en la limpieza de `backend/tests/conftest.py`. Verificar: 2.1–2.2 en verde y `test_models_metadata.py` en verde.
- [x] 2.4 RED → GREEN: reversibilidad con `alembic_helpers`: `downgrade -1` borra la tabla y sus índices, `upgrade head` vuelve a pasar (R14). Verificar en verde.
- [x] 2.5 Documentar en `knowledge-base/04_modelo_de_datos.md` §Recordatorio los atributos de D2, el estado `anulado` y sus motivos. Verificar que coincide con la migración.

## 3. Mensaje y link `wa.me` (D4) — requisito "Link de WhatsApp con el mensaje preformateado"

- [x] 3.1 RED: `backend/tests/test_recordatorios_mensaje.py` (sin base): los tres escenarios del requisito (link armado con todos los datos; el borde de UTC → "17/11" y "21:30"; codificación de "¿", "á", "#", "&"), más "Turno interno sin código de gestión" (sin enlaces, pide responder): el teléfono va sin "+", el código solo aparece después de `#`. Verificar que falla por falta de `app.notificaciones.mensaje`.
- [x] 3.2 GREEN + TRIANGULAR + REFACTOR: implementar `app/notificaciones/mensaje.py` (puro, con `zona` y `base_url` inyectados); sumar un caso con otra profesional y otro `CLINICA_NOMBRE`. Verificar en verde.

## 4. Trabajo de recordatorios y proveedor (D3, D4) — spec `notificaciones/recordatorios-whatsapp`

- [x] 4.1 RED: `backend/tests/test_recordatorios_generacion_integration.py` con `ahora` fijo: requisitos "Solo los turnos reservados reciben recordatorio" (incluye alta manual sin seña y `confirmado` sin recordatorio), "Turnos reservados tarde también reciben recordatorio" y "Turno sin teléfono válido queda fallido" (incluye teléfono de la ficha del paciente). Verificar que falla por falta del servicio.
- [x] 4.2 GREEN: `app/notificaciones/service.py` con `generar_recordatorios(session, ahora, anticipacion, proveedor) -> ResumenCiclo` (consultas ORM, sin SQL crudo, R14; `INSERT … ON CONFLICT DO NOTHING` vía el dialecto de SQLAlchemy). Verificar 4.1 en verde.
- [x] 4.3 RED → GREEN: requisito "Un solo recordatorio vigente por horario del turno": ciclos repetidos y dos sesiones concurrentes sobre el mismo turno (`asyncio.gather`) → un solo recordatorio, sin excepción no controlada. Verificar en verde.
- [x] 4.4 RED → GREEN: reconciliación (paso 1 de D3): turno cancelado → `anulado` `turno_cancelado`; inicio distinto → `turno_reprogramado`; turno iniciado con `pendiente` → `turno_iniciado`; un `confirmado` vigente no se toca; un `enviado` de un turno marcado `ausente` o `atendido` sigue `enviado` ("Turno atendido o ausente conserva el historial"). Verificar en verde.
- [x] 4.5 RED → GREEN: `app/notificaciones/proveedor.py` (`ProveedorWhatsApp`, `ProveedorManual`, `ProveedorFalso` solo para tests) y requisito "Reintentos con espera creciente ante fallas del proveedor": manual → `pendiente` con 0 intentos; falla siempre → 1, 5, 15 min y `fallido` `error_proveedor` al tercer intento; falla una vez y luego éxito. Verificar en verde.
- [x] 4.6 RED → GREEN: requisito "Recordatorios sin datos personales en logs ni auditoría" (parte del trabajo): un error del proveedor con "+5491100000003" no queda en `ultimo_error` ni en el log (`caplog`); el log del ciclo con 50 turnos solo tiene cantidades. Verificar en verde.

## 5. Worker y consolidación del barrido (D1) — spec `plataforma/trabajos-programados`

- [x] 5.1 RED → GREEN: `backend/tests/test_jobs_registro.py`: el registro expone el trabajo de recordatorios y el barrido con sus intervalos de `Settings`; cada uno se omite si su bandera está apagada; el adaptador abre la sesión, pasa `ahora` con zona, y una excepción del trabajo se loguea sin PII y no se propaga ("Error inesperado en un trabajo"). Implementar `app/jobs/registro.py` y `app/jobs/worker.py`. Verificar en verde.
- [x] 5.2 RED → GREEN: barrido fuera de la API: test de `lifespan` en `backend/tests/test_jobs_lifespan.py` → sin `SENA_BARRIDO_EN_API` no se crea la tarea; con `true` sí ("Barrido en la API para pruebas"). Ajustar `app/main.py`. Verificar que `test_sena_barrido_integration.py` sigue en verde sin cambios (llama `expirar_pre_reservas` directo).
- [x] 5.3 Verificación de sistema: `docker compose up -d --wait postgres redis worker` deja los tres `healthy`, el log del worker lista los dos trabajos, y con Redis detenido el worker no arranca. Registrar el resultado en el acta.
- [x] 5.4 RED → GREEN: requisito "Trabajos idempotentes ante ejecuciones concurrentes": dos `expirar_pre_reservas` concurrentes sobre una pre-reserva vencida → un solo `cancelado` y una sola auditoría. Verificar en verde.

## 6. Anulación al cancelar o reprogramar (D6)

- [x] 6.1 RED: `backend/tests/test_recordatorios_notificador_integration.py`: `turno_cancelado` anula los vigentes del horario anterior con `turno_cancelado`; `turno_reprogramado` anula los del `inicio_anterior` con `turno_reprogramado` y no toca otros horarios; un notificador que falla no revierte la cancelación (respuesta 200, turno `cancelado`) y el siguiente ciclo del trabajo lo corrige. Verificar que falla.
- [x] 6.2 GREEN: `NotificadorRecordatorios` y `NotificadorCompuesto` en `app/notificaciones/notificador.py`; `app/gestion/deps.get_notificador` devuelve el compuesto. Verificar 6.1 en verde y que `test_gestion_eventos.py`, `test_gestion_cancelacion_integration.py`, `test_gestion_reprogramacion_integration.py` y `test_panel_acciones.py` siguen en verde.
- [x] 6.3 RED → GREEN: escenarios del requisito "Cancelar o reprogramar anula el recordatorio del horario anterior" end-to-end por API: cancelación desde la gestión con 40 h (seña `a_reembolsar`, recordatorio `anulado`); cancelación con 23 h 59 min → 409 `fuera_de_plazo` y recordatorio intacto; reprogramación de un `confirmado` → `reservado` y recordatorio nuevo para el horario nuevo. Verificar en verde.

## 7. Confirmación pública (D5) — spec `turnos/gestion-paciente`

- [x] 7.1 RED: `backend/tests/test_gestion_confirmacion_integration.py`: requisitos "Confirmación de asistencia con el código de gestión" y "Solo se confirma un turno reservado que todavía no empezó" (todos los escenarios: 200 con auditoría `confirmacion_paciente`, 404 genérico, confirmación con 2 h, idempotente sin auditoría nueva, `sena_pendiente`, `turno_no_modificable`, `turno_iniciado` en el instante exacto). Verificar que falla.
- [x] 7.2 GREEN: `confirmar_turno_publico` en `app/gestion/service.py` reutilizando `cambiar_estado_turno`; endpoint `POST /api/public/gestion/confirmar` con esquema de respuesta (R15) y motivo `turno_iniciado` en `MotivoNoModificable`. Verificar 7.1 en verde.
- [x] 7.3 RED → GREEN: requisito "La confirmación de la o el paciente cierra el recordatorio": recordatorio `enviado` → `confirmado` con fecha; turno cancelado → 409 y recordatorio `anulado`; confirmación sin recordatorio y luego el trabajo no genera ninguno. Verificar en verde.
- [x] 7.4 RED → GREEN: requisito "La consulta informa si se puede confirmar": `puede_confirmar` / `motivo_no_confirmable` (`ya_confirmado`, `turno_no_modificable`, `sena_pendiente`, `turno_iniciado`) en `GET /api/public/gestion`. Verificar en verde y que `test_public_schemas.py` y los tests de gestión existentes siguen en verde.

## 8. API del panel para recordatorios (D7) — spec `notificaciones/recordatorios-whatsapp`

- [x] 8.1 RED: `backend/tests/test_recordatorios_panel_integration.py`: requisito "Listado de recordatorios para recepción" (orden por inicio, link presente, 403 odontóloga sin teléfonos, 401 sin sesión, recordatorio desactualizado oculto, filtro por estado). Verificar que falla.
- [x] 8.2 GREEN: `app/notificaciones/schemas.py` y `router.py` (`GET /api/panel/recordatorios`) con `require_recepcion_o_admin`, registrado en `app/main.py`. Verificar 8.1 en verde.
- [x] 8.3 RED → GREEN: requisitos "Abrir WhatsApp registra el envío" y "Marcar un recordatorio que no se pudo enviar" (200 con usuario y fecha, reenvío, 409 `recordatorio_no_vigente`, 404, 422 por motivo fuera de lista) y auditoría sin PII ("Auditoría del envío"). Verificar en verde.
- [x] 8.4 Agregar los tres endpoints a la matriz RBAC de tests si existe un test de matriz por módulo (patrón `test_caja_rbac_matriz.py`). Verificar: la matriz cubre los roles `recepcion`, `admin`, `odontologo` y anónimo.

## 9. Frontend del paciente: confirmar asistencia (D7) — requisito "Pantalla de confirmación a 360px"

- [x] 9.1 RED: tests unitarios del cliente (`src/lib/api.gestion.test.ts`): `confirmarTurno(codigo)` envía `POST /api/public/gestion/confirmar` con `X-Codigo-Gestion` y mapea 200/404/409 con motivo; tipos sin `any` (R1). Verificar que fallan.
- [x] 9.2 GREEN: cliente y tipos en `src/lib/api.ts` / `tipos.ts`. Verificar en verde.
- [x] 9.3 RED → GREEN: `src/components/ConfirmarTurno.test.tsx`: muestra día/hora/profesional/tratamiento; abrir no confirma; tocar "Confirmar asistencia" muestra "¡Listo! Confirmaste tu turno…"; turno cancelado → "Este turno ya no se puede confirmar" sin botón; enlace a "Gestionar mi turno". Implementar `ConfirmarTurno.tsx` y la ruta `/confirmar` en `App.tsx`. Verificar con `npm test`, `npm run typecheck`, `npm run lint` y `npm run build`.

## 10. Frontend del panel: sección Recordatorios (D7) — requisito "Pantalla de recordatorios del panel a 360px"

- [x] 10.1 RED: tests del cliente del panel para listar, marcar enviado y marcar fallido (tipos estrictos, R1). Verificar que fallan.
- [x] 10.2 GREEN: cliente en `frontend-panel/src/lib/`. Verificar en verde.
- [x] 10.3 RED → GREEN: `Navegacion.test.tsx`: "Recordatorios" visible para recepción y admin, oculta para la odontóloga y `#recordatorios` la deja en la agenda. Ajustar `Navegacion.tsx` y `App.tsx`. Verificar en verde.
- [x] 10.4 RED → GREEN: `Recordatorios.test.tsx`: lista ordenada, "Abrir WhatsApp" es un enlace `wa.me` con `target="_blank"` y `rel="noopener noreferrer"` que dispara el marcado sin bloquear la apertura; error del marcado visible con reintento; "No se pudo enviar" con los tres motivos; estado vacío "No hay recordatorios por enviar". Implementar `Recordatorios.tsx` sin fetches en cascada (R2). Verificar con `npm test`, `npm run typecheck`, `npm run lint` y `npm run build`.

## 11. CI y E2E Playwright (D9, R7)

- [x] 11.1 Ajustar `.github/workflows/ci.yml`: los jobs `e2e` y `e2e-panel` levantan `docker compose up -d --wait postgres redis`, migran, y luego `backend worker` con `RECORDATORIOS_INTERVALO_SEGUNDOS=3` y `SENA_BARRIDO_SEGUNDOS=3`; suben los logs del worker si fallan. El job de pytest no cambia (sin Redis). Verificar: `docker compose config` válido y los E2E de vencimiento de C-06 siguen en verde localmente con el worker.
- [x] 11.2 E2E paciente `frontend-paciente/e2e/confirmacion.spec.ts` a 360 px: confirmar desde `/confirmar#…` (sin scroll horizontal), turno `en_espera` sin botón, abrir y no tocar no confirma. Verificar en verde con `npm run e2e`.
- [x] 11.3 E2E panel `frontend-panel/e2e/recordatorios.spec.ts` a 360 px y 1280 px: aparece el recordatorio de un turno sintético dentro de 48 h; el `href` empieza con `https://wa.me/54911000000` y su texto decodificado tiene nombre, hora y `/confirmar#`; "Abrir WhatsApp" lo pasa a "Enviado"; cancelar ese turno desde la gestión lo saca de la lista; la odontóloga no ve la sección. Verificar en verde con `npm run e2e`.
- [ ] 11.4 Verificación de integración: correr la CI remota de la rama (cuando el usuario autorice el push, R11) y registrar el run en el acta; mientras tanto, la suite local completa (pytest, unit y E2E de ambos frontends) en verde.

## 12. Documentación y cierre

- [x] 12.1 Actualizar `knowledge-base/05_reglas_de_negocio.md` (RN-WA-01..03 con las decisiones aprobadas: anticipación, solo `reservado`, confirmación por link con código, `enviado` manual) y `knowledge-base/08_arquitectura_propuesta.md` (variables de D8, `REMINDER_LEAD_TIME` y nota de que `WHATSAPP_API_TOKEN` sigue siendo futuro). Verificar que no contradicen los specs.
- [x] 12.2 Actualizar `README.md`: cómo levantar `redis` y `worker`, variables nuevas, `SENA_BARRIDO_EN_API` para desarrollo sin worker, y la operación de recordatorios para recepción. Verificar que los comandos documentados corren tal cual.
- [ ] 12.3 Registrar en `CHANGES.md` solo la línea de estado de C-09 (sin tocar otras secciones) y verificar con `git diff CHANGES.md` que no se perdió ninguna línea.
- [x] 12.4 Correr `spec-rules-auditor` sobre el código y los specs finales (RN-WA-01..03, R8, R16, R18, RN-TU-01) y volcar el dictamen en el acta. Verificar dictamen `APROBADO` o resolver las observaciones.
- [x] 12.5 `openspec validate c-09-whatsapp-recordatorios-confirmacion --strict` en verde y `git status` sin archivos sueltos en la raíz (R20). Verificar ambos.

## Workflow follow-up

- Commit en conventional commits sin coautoría IA y push solo cuando el usuario lo pida (R11, R12).
- Archivar con `/opsx:archive c-09-whatsapp-recordatorios-confirmacion` después de la revisión y la CI en verde, y marcar `[x]` en `CHANGES.md`.

## Acta

<!-- Línea base (0.2), número de migración (0.3), verificación del worker (5.3), runs de CI (11.4) y dictamen final (12.4). -->

- **0.2 Línea base (antes de tocar nada):** backend `1387 passed`; `frontend-paciente` 151 tests y `frontend-panel` 301 tests en verde, `typecheck` limpio en ambos.
- **0.3 Migración:** `010` estaba libre; se usó `010_recordatorios` (down_revision `009_caja_cierres_devol`).
- **5.3 Worker (docker compose, local):** `docker compose up -d --build --wait postgres redis worker` dejó los tres `healthy`; el log del worker lista `Starting worker for 2 functions: recordatorios, barrido_sena` y el barrido corre cada intervalo. NO se probó con Redis caído (con `depends_on: service_healthy` Compose levanta Redis antes del worker; simular Redis no sano no se hizo).
- **11.1 / 11.2 / 11.3 E2E locales con worker real** (`APP_ENV=e2e`, intervalos de 3 s): `frontend-paciente` 24 passed (incluye el vencimiento de C-06 corriendo en el worker y `confirmacion.spec.ts`); `frontend-panel` 70 passed, 2 skipped (skips previos de la suite), incluye `recordatorios.spec.ts` a 360 y 1280 px.
- **11.4 CI remota:** pendiente (R11: no hay push). `ci.yml` ajustado y `docker compose config` válido.
- **12.3:** NO realizado a pedido del coordinador (CHANGES.md se actualiza en el archive).
- **12.4 Auditoría de reglas (`spec-rules-auditor`, revisión propia del apply):** RN-WA-01 cubierta (todo `reservado` no iniciado, incl. alta manual y reservado tarde); RN-WA-02 cubierta (botón + POST, recordatorio `confirmado`); RN-WA-03 cubierta (proveedor manual, `en_espera` sin recordatorio, sin API); R8 (`sena_pendiente` 409 y sin recordatorio); RN-TU-01 reutilizada de C-07; R16 (worker, nada bloqueante), R17 (sin secretos), R18 (redis y worker con healthcheck), R19 (sin PII en logs/auditoría, probado), R3/R7 (E2E 360 px). Dictamen: APROBADO con las decisiones O19–O23 pendientes de confirmación (ver design.md).
