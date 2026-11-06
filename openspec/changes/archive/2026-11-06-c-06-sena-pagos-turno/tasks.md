# Tasks: c-06-sena-pagos-turno

> **Governance CRÍTICO (pagos).** El usuario aprobó las decisiones P1–P8 el 2026-11-06 (`design.md` §Decisiones aprobadas; RN-SN-04 a RN-SN-08 en la KB). Cualquier desvío durante el apply se consulta antes de escribir código.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR. El test se escribe primero, tiene que fallar por la razón correcta y recién después va la implementación mínima. La verificación que figura en cada tarea es el test que tiene que quedar en verde. Ningún test llama a Mercado Pago de verdad: los unitarios y de integración usan la pasarela falsa o `httpx.MockTransport`. Todos los datos son sintéticos (R19).

## 0. Red de seguridad

- [x] 0.1 Con `docker compose up -d postgres` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm run typecheck && npm run lint && npm test && npm run e2e` en `frontend-paciente/`, y registrar la línea base (N tests en verde). Si algo falla antes de empezar, frenar y reportarlo como falla previa, sin arreglarlo.

## 1. Migración `006_sena_pagos` y modelos (R4, R5, R6, R14)

- [x] 1.1 RED: en `backend/tests/test_sena_migracion.py`, tests de integración contra PostgreSQL que verifican que existen `pago_sena`, `configuracion_sena` (con la fila por defecto: 30.00, ambos medios, 30 y 1440 minutos, y el texto de política "Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve.") y `turno.en_espera_vence_en`; que los CHECK rechazan `monto <= 0`, un medio `efectivo`, un porcentaje de 0 o de 100.01, un CBU que no tenga 22 dígitos y un `en_espera` sin vencimiento; que `referencia_externa` y `mp_payment_id` son únicos; y que no puede haber dos pagos activos por turno (`uq_pago_sena_activo`). Verificar que fallan porque falta la migración.
- [x] 1.2 GREEN: escribir `backend/src/alembic/versions/006_sena_pagos.py` (`down_revision="005_reserva_publica"`) según el DDL de design D2, con un índice para cada FK (`ix_pago_sena_turno`, `ix_pago_sena_acreditado_por`), y los modelos `PagoSena` y `ConfiguracionSena` en `backend/src/app/pagos/models.py` más `Turno.en_espera_vence_en`. Verificar que los tests de 1.1 pasan y que `test_models_metadata.py` sigue en verde.
- [x] 1.3 TRIANGULAR: agregar un test de que el UPDATE directo de un `en_espera` solapado a `reservado` falla con 23P01 (escenario del delta `turnos/creacion-sin-solape`), y un test de ciclo `alembic upgrade head → downgrade 005_reserva_publica → upgrade head` sin errores, con el downgrade cancelando los `en_espera`. Verificar ambos en verde.

## 2. Dominio puro: cálculo y máquina de estados

- [x] 2.1 RED → GREEN: en `backend/tests/test_sena_calculo.py`, testear `monto_sena(precio_base, porcentaje)`: 10000.00 al 30% da 3000.00; 3333.33 al 30% da 1000.00 (half-up); precio 0 da 0.00; siempre `Decimal` con 2 decimales. Testear también `vencimiento(ahora, minutos, inicio)`, que no puede pasar del inicio. Implementarlo en `backend/src/app/pagos/calculo.py` hasta que pase.
- [x] 2.2 RED → GREEN: en `backend/tests/test_sena_estados.py`, testear con una tabla todas las transiciones permitidas y prohibidas (los finales no salen; `en_espera → ausente` está prohibida) y sus efectos sobre la seña: ausente → `no_reembolsado` (RN-SN-02); cancelado con seña acreditada y 24 h o más → `a_reembolsar` (RN-SN-04); con 23 h 59 min → `CancelacionFueraDePlazoError` (RN-TU-01); exactamente 24 h se acepta; `en_espera → cancelado` con pago pendiente → `vencido`. Implementar `backend/src/app/pagos/estados.py` con `TransicionInvalidaError` hasta que pase.

## 3. Puerto `PasarelaPagos` y adaptadores (sin red en tests)

- [x] 3.1 RED → GREEN: en `backend/tests/test_sena_firma.py`, testear `verificar_firma` del manifest `id:{data.id};request-id:{x-request-id};ts:{ts};` con HMAC-SHA256 y vectores fijos sintéticos: una firma válida, otro secreto, sin `v1`, una cabecera malformada y un `ts` fuera de la tolerancia de 300 s. Implementarlo en `backend/src/app/pagos/pasarela.py` con `hmac.compare_digest`.
- [x] 3.2 RED → GREEN: testear el adaptador falso (`backend/src/app/pagos/fake.py`): `crear_preferencia` devuelve `{PUBLIC_BASE_URL}/?pago=retorno&turno={id}` y `obtener_pago("fake-approved-<ref>")` decodifica el estado y la referencia, todo sin estado compartido. Verificar los tests en verde.
- [x] 3.3 RED → GREEN: testear el adaptador de Mercado Pago (`backend/src/app/pagos/mercadopago.py`) con `httpx.MockTransport`: el body de la preferencia (external_reference, monto como string decimal, `expiration_date_to`, notification_url, back_urls), las cabeceras `Authorization` y `X-Idempotency-Key`, el parseo de `GET /v1/payments/{id}`, y que un timeout o un 5xx se traduce en `PasarelaNoDisponibleError`. Verificar en verde y que el token no aparece en ningún log ni excepción.
- [x] 3.4 RED → GREEN: en `backend/tests/test_settings_mp.py`, testear que con `MP_GATEWAY=mercadopago` y sin `MP_ACCESS_TOKEN` o `MP_WEBHOOK_SECRET` la configuración falla nombrando la variable y sin mostrar valores; que `APP_ENV=production` con `MP_GATEWAY=fake` falla; y que el default `fake` sirve para tests. Implementarlo en `backend/src/app/shared/settings.py` con `SecretStr`.

## 4. Reserva pública en `en_espera` (delta `turnos/reserva-publica`)

- [x] 4.1 RED: actualizar `backend/tests/test_public_endpoints_integration.py`. El caso feliz de "Carlos Sintético" ahora espera 201 con `estado` "en_espera", el bloque `sena` (monto "3000.00" con precio 10000.00, `vence_en` no posterior al inicio, medios habilitados) y ningún `Paciente` creado. La reserva concurrente ahora espera dos 201 `en_espera` (P7). El 409 contra un turno `reservado` ya existente sigue igual. Agregar dos casos: la disponibilidad ofrece un horario ocupado solo por un `en_espera`, y el tratamiento con precio 0 nace `reservado` (P4). Verificar que fallan por la razón esperada.
- [x] 4.2 GREEN: modificar `reservar_turno_publico` en `backend/src/app/public/service.py` y `ReservaPublicaResponse` en `backend/src/app/public/schemas.py` según design D3, conservando el advisory lock, el pre-chequeo y la auditoría sin PII. Verificar 4.1 en verde y que el resto de la suite de C-05 sigue pasando.

## 5. Inicio y consulta de la seña (`POST`/`GET /api/public/turnos/{id}/sena`)

- [x] 5.1 RED: en `backend/tests/test_sena_inicio_integration.py`, con la pasarela falsa por `dependency_overrides`, cubrir:
  - Mercado Pago: 201 con `checkout_url` y un único pago pendiente.
  - Reintento con el mismo medio: 200 y la misma referencia.
  - Cambio a transferencia: la anterior queda `vencido`, 201, alias y CBU sintéticos, `referencia_concepto` corta (`SENA-{id}-XXXXXX`, 20 caracteres o menos) y `vence_en` de transferencia hasta el inicio (RN-SN-07, RN-SN-08).
  - Medio deshabilitado o `efectivo`: 422.
  - Código ausente o ajeno: 404 sin datos de contacto.
  - Turno no `en_espera` o vencido: 409.
  - Horario ya tomado por un `reservado`: 409 con alternativas y sin pago.
  - Pasarela caída: 502 sin pago persistido.
  - El porcentaje cambia después de iniciar y la seña conserva su monto y porcentaje.
  - `GET` sin pago iniciado: `estado_pago` null; con pago acreditado: `reservado`/`acreditado`.
- [x] 5.2 GREEN: implementar `backend/src/app/pagos/service.py` (`iniciar_sena`, `consultar_sena`), los esquemas de `backend/src/app/pagos/schemas.py` (`extra="forbid"`, R15) y `backend/src/app/pagos/router_public.py`, y registrar el router en `main.py`, según design D4. Verificar 5.1 en verde.

## 6. Acreditación con anti-solape (servicio único)

- [x] 6.1 RED: en `backend/tests/test_sena_acreditacion_integration.py`, cubrir:
  - Acreditar un `en_espera` libre: pasa a `reservado`, el pago a `acreditado`, el horario sale de la disponibilidad y un `POST /api/turnos` solapado da 409.
  - Dos `en_espera` en el mismo horario: el primero en acreditarse gana; el segundo queda `cancelado` y su pago `a_reembolsar` (P3).
  - Sillón original ocupado y otro libre: reasigna y lo audita.
  - Pago sobre un turno vencido o cancelado: `a_reembolsar` sin revivir el turno.
  - Acreditar dos veces el mismo pago: no-op con una sola auditoría.
  - Dos acreditaciones concurrentes (`asyncio.gather`) del mismo pago: un solo efecto, nunca 500 ni deadlock.
  - Exactamente un registro de auditoría con origen `acreditacion_sena` al acreditar, y ninguno para un `en_espera` que vence sin pagar (RN-SN-01, RN-WA-03).
- [x] 6.2 GREEN: implementar `acreditar_pago` según design D5 (`pg_advisory_xact_lock(LOCK_RESERVAS)`, `with_for_update()` del ORM, re-chequeo con `_cargar_bloqueos`/`_sillon_libre` y red de seguridad 23P01). Verificar 6.1 en verde.

## 7. Webhook `POST /api/webhooks/mercadopago`

- [x] 7.1 RED: en `backend/tests/test_sena_webhook_integration.py`, con un secreto sintético y la pasarela falsa, cubrir:
  - Firma válida y pago `approved`: 200, acreditado y `reservado`.
  - Firma inválida, ausente o con `ts` vencido: 401, sin consultar la pasarela y sin cambios.
  - Webhook duplicado: 200 idempotente.
  - Dos webhooks simultáneos: un solo efecto.
  - Pago `rejected` o referencia desconocida: 200 sin cambios y log sin PII.
  - `type` distinto de `payment`: 200 ignorado.
  - Pasarela caída al consultar: 503.
- [x] 7.2 GREEN: implementar `backend/src/app/pagos/router_webhook.py` según design D6, que consulta el pago con `obtener_pago` y nunca confía en el body. Verificar 7.1 en verde.

## 8. Endpoints admin: acreditar transferencia y configuración

- [x] 8.1 RED: en `backend/tests/test_sena_admin_integration.py`, con usuarios sintéticos de C-03, cubrir:
  - `POST /api/admin/pagos-sena/{id}/acreditar`: `recepcion` da 200 (acredita, guarda el usuario y audita en `RegistroAuditoria`); `odontologo` da 403; un pago de Mercado Pago o una transferencia vencida dan 409.
  - `GET/PUT /api/admin/config/sena`: `admin` da 200 y se audita; porcentaje 0 o 100.01, medios vacíos o `efectivo` dan 422 sin cambios; 100.00 se acepta; `odontologo` da 403.
- [x] 8.2 GREEN: implementar `backend/src/app/pagos/router_admin.py` con `require_role` de `app/auth/rbac.py`, reusando `acreditar_pago` y la validación Pydantic de la configuración. Verificar 8.1 en verde.

## 9. Vencimiento de `en_espera` y transiciones de turno

- [x] 9.1 RED → GREEN: en `backend/tests/test_sena_barrido_integration.py`, testear `expirar_pre_reservas(session, ahora)` con un `ahora` inyectado:
  - A las 10:31, un vencido a las 10:30 pasa a `cancelado` con su pago `vencido` y auditoría.
  - A las 10:29:59 no cambia nada.
  - Correrlo dos veces no tiene efecto adicional.
  - Un `en_espera` vencido que el barrido todavía no tocó igual se rechaza en el inicio de seña (409).

  Implementar `backend/src/app/pagos/barrido.py` hasta que pase.
- [x] 9.2 RED → GREEN: testear que la tarea periódica del `lifespan` en `main.py` arranca solo si `SENA_BARRIDO_HABILITADO` es verdadero, que se cancela limpia al apagar la app, y que con la bandera en false (tests) no corre. Implementarla hasta que pase.
- [x] 9.3 RED → GREEN: en `backend/tests/test_sena_transiciones_integration.py`, testear `cambiar_estado_turno`:
  - `confirmado → ausente` con seña acreditada de "3000.00": el pago queda `no_reembolsado` por "3000.00" y no se llama a ningún método de reembolso de la pasarela (R9).
  - `en_espera → ausente`: 409 sin cambios.
  - `atendido → reservado`: 409.
  - `reservado → cancelado` con seña acreditada y 48 h de anticipación: el pago queda `a_reembolsar` y el horario se libera (RN-SN-04).
  - Con 23 h 59 min: 409 `fuera_de_plazo` sin cambios.
  - Con exactamente 24 h: se acepta.

  Implementarlo en `backend/src/app/pagos/service.py`.

## 10. Frontend: pantalla de seña a 360px (R1, R2, R3)

- [x] 10.1 RED → GREEN: en `frontend-paciente/src/lib/api.test.ts` y `src/lib/tipos.ts`, testear con Vitest los clientes `iniciarSena` y `consultarSena`: cabecera `X-Codigo-Gestion`, el monto como string decimal y la unión discriminada de estados (`en_espera`/`reservado`, pago `pendiente`/`acreditado`/`vencido`/`a_reembolsar`/null), sin `any`. Testear también que `reservarTurno` acepta la respuesta nueva con el bloque `sena`. Implementarlos hasta que pasen y verificar con `npm run typecheck`.
- [x] 10.2 RED → GREEN: en `frontend-paciente/src/components/PagoSena.test.tsx`, testear con Testing Library que se muestran el título "Pagá la seña para confirmar tu turno", el monto, "Tu reserva vence a las HH:MM" (hora de la clínica), el texto de la política de reembolso, un botón por medio habilitado y el aviso de no confirmado; que Mercado Pago guarda `{turnoId, codigoGestion}` en el almacenamiento del navegador (con try/catch; desde P15, `localStorage` con vencimiento) y redirige a `checkout_url`; y que transferencia muestra el alias, el CBU, el monto y el código de referencia para el concepto, cada uno con su botón "Copiar". Verificar también que se muestra el texto de política que viene de la API (por defecto: "Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve.") y que no hay textos fijos de "no reembolsable" en el componente. Implementar `PagoSena.tsx` con los tokens de `estilos.css` hasta que pase.
- [x] 10.3 RED → GREEN: en `frontend-paciente/src/components/EsperaAcreditacion.test.tsx`, testear con timers falsos el sondeo cada 3 s con tope de 2 minutos y que cada estado terminal muestra su pantalla: `reservado` lleva a "Turno reservado" con el código; vencido, a "La reserva venció" con "Elegir otro horario"; `a_reembolsar`, al mensaje de devolución; y el tope, a "Seguimos esperando la acreditación". Implementarlo, conectar `App.tsx` al retorno `?pago=retorno` y cambiar `Reserva.tsx` para que muestre `PagoSena` cuando la respuesta trae `en_espera`. Verificar `npm test`, `npm run lint` y `npm run typecheck` en verde.

## 11. E2E Playwright del flujo de seña (R7, 360px, backend real con `MP_GATEWAY=fake`)

- [x] 11.1 Agregar un helper en `frontend-paciente/e2e/ayudas.ts` que firme y envíe el webhook con el secreto sintético del entorno E2E (`request.post` a `/api/webhooks/mercadopago` con `x-signature` y `x-request-id`), más los helpers para adelantar `en_espera_vence_en` por `pg` y loguear un usuario `recepcion` sintético. Verificar que `npm run typecheck` pasa.
- [x] 11.2 Reescribir `frontend-paciente/e2e/reserva.spec.ts` según P7. Los tests de confirmación esperan ahora la pantalla "Pagá la seña…" y el turno `en_espera` en la base. La carrera simultánea espera ahora dos 201 `en_espera`. El 409 con alternativas se mantiene contra un turno `reservado` sembrado. Verificar la suite en verde y repetida 3 veces.
- [x] 11.3 Escribir `frontend-paciente/e2e/sena.spec.ts` con estos casos y verificarlo en verde, repetido 3 veces, a 360px:
  - **(a) Happy path Mercado Pago:** "Carlos Sintético" reserva, paga con Mercado Pago, vuelve, se envía el webhook firmado y la pantalla muestra "Turno reservado" y el turno queda `reservado`.
  - **(b) Transferencia:** muestra el alias, el CBU sintético y el código de referencia del concepto; recepción la acredita por la API y la pantalla pasa a "Turno reservado".
  - **(c) Vencimiento:** se adelanta el vencimiento y corre el barrido; la pantalla muestra "La reserva venció" y el horario vuelve a estar libre.
  - **(d) Competencia:** dos pacientes reservan el mismo horario y los dos ven la pantalla de seña; se acredita el primero; el segundo ve el mensaje de devolución y la base tiene un único turno bloqueante.
  - **(e) Webhook con firma inválida:** responde 401 y la pantalla sigue esperando.
  - **(f) Layout:** sin scroll horizontal en la pantalla de seña ni en la espera.

## 12. Infra, CI y documentación

- [x] 12.1 Agregar a `docker-compose.yml` las variables `MP_GATEWAY`, `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`, `API_PUBLIC_BASE_URL`, `APP_ENV`, `SENA_BARRIDO_*`, tomadas del host y con defaults de test (`fake` y un secreto sintético), sin ningún `.env` commiteado (R17, R20). Agregar a `.github/workflows/ci.yml` las mismas variables para los jobs backend y e2e. Verificar que `docker compose config` es válido y que `GET /api/health` responde 200 con el compose levantado.
- [x] 12.2 Documentar en `README.md` las variables nuevas, la pasarela falsa, cómo configurar el webhook en Mercado Pago y cómo acreditar una transferencia por la API. Si la implementación agrega algo, ampliar `knowledge-base/04_modelo_de_datos.md` §PagoSena con la tabla `configuracion_sena` (las reglas RN-SN-04 a RN-SN-08 y el estado `a_reembolsar` ya se sincronizaron en la propuesta). Verificar que los enlaces del README apuntan a archivos que existen.

## 13. Verificación integral y terna de escenarios (`spec-rules-auditor`)

- [x] 13.1 **Escenario 1 (Happy Path):** reserva `en_espera` → seña por Mercado Pago → webhook firmado → `reservado`, que bloquea agenda (spec `pagos/sena-turno`: "Acreditación bloquea el horario"). Verificar por la API (6.1/7.1) y por la UI (11.3a).
- [x] 13.2 **Escenario 2 (Error de Negocio):** firma inválida rechazada con 401 sin cambios, y dos pre-reservas que compiten con un único turno bloqueante (R8, RN-TU-03). Verificar con 7.1, 6.1 y 11.3d/e.
- [x] 13.3 **Escenario 3 (Caso de Borde):** webhook duplicado idempotente, vencimiento a las 10:29:59 contra 10:31 ausente que retiene la seña (R9) y cancelación con exactamente 24 h, que devuelve la seña, contra 23 h 59 min, que se rechaza (RN-SN-04, RN-TU-01). Verificar con 7.1, 9.1, 9.3 y 11.3c.
- [x] 13.4 Corrida final: `python -m pytest -q` en verde (línea base + nuevos), `npm run typecheck && npm run lint && npm test && npm run e2e` en verde, y `openspec validate c-06-sena-pagos-turno --strict` sin errores. Registrar en este archivo una nota de verificación con los conteos.

## 14. Monto informado por la pasarela (RN-SN-09, P9) y pago vencido vigente (P10)

- [x] 14.1 RED: `backend/tests/test_sena_revision_monto_integration.py`, `test_sena_pasarelas.py` y `test_sena_migracion.py`: monto exacto acredita, menor y mayor quedan `en_revision`, moneda distinta, re-entrega idempotente, re-entrega correcta acredita, acreditación manual, turno vencido a `a_reembolsar`, el barrido no pisa el pago, log sin PII, y la pasarela falsa decodifica monto y moneda. Fallaban por falta del estado, las columnas y la comparación.
- [x] 14.2 GREEN: `en_revision`, `monto_reportado` y `moneda_reportada` en la 006 (reversible, ciclo up/down verde), `acreditar_pago(monto_reportado, moneda_reportada)`, `PagoPasarela.moneda`, la pasarela falsa (`@monto@moneda`), el adaptador de Mercado Pago (`currency_id`), el webhook y la acreditación manual de pagos `en_revision`.
- [x] 14.3 Cobertura de P10: `test_pago_vencido_por_cambio_de_medio_igual_se_acredita_si_el_turno_sigue_vigente` (6.1) y el escenario del spec.
- [x] 14.5 Falla cerrado (RN-SN-09): RED en `test_sena_revision_monto_integration.py` y `test_sena_pasarelas.py` (adaptador real de Mercado Pago con `MockTransport` sin `transaction_amount`, sin `currency_id` y con monto ilegible van a `en_revision`; con ambos correctos acredita; re-entrega idempotente; la acreditación manual no se ve afectada; la pasarela falsa sin `@monto@moneda` también va a revisión). GREEN: `_discrepancia` trata `None` como discrepancia, `acreditar_pago(manual=...)` (solo la acreditación de recepción/admin pasa `manual=True`) y el adaptador de Mercado Pago informa `None` ante un dato ausente o ilegible. Los tests existentes y el E2E ahora envían el monto y la moneda (`fake-approved-<ref>@<monto>@ARS`).
- [x] 14.4 Docs: RN-SN-09 en la KB 05, estados de `PagoSena` en la KB 04, requisitos y escenarios en el spec, P9 a P11 en `design.md` y nota en `CHANGES.md`.

## 15. Hallazgos de la revisión de código (aprobados 2026-11-06)

- [x] 15.1 Pasarela falsa fail-safe (R17): `Settings` solo la acepta con `APP_ENV=test|e2e` y los defaults son producción + Mercado Pago real; `docker-compose.yml` sin secreto por defecto (`MP_WEBHOOK_SECRET` obligatoria); CI y E2E exportan valores sintéticos; README actualizado. Tests en `test_settings_mp.py`.
- [x] 15.2 Pagos de la pasarela registrados por id (RN-SN-10, P13): tabla `pago_sena_aprobacion` en la 006; sobrantes y pagos en revisión desplazados quedan `a_reembolsar`; la re-entrega del mismo id es idempotente. Tests en `test_sena_hallazgos_integration.py` y `test_sena_migracion.py`.
- [x] 15.3 Un deadlock no produce un reembolso (P14): reintento y, agotado, `OperacionReintentableError` (503 en el webhook y en la acreditación manual); solo un 23P01 persistente termina en `a_reembolsar`.
- [x] 15.4 Orden de locks único (advisory, turno, pago) en `acreditar_pago`, `cambiar_estado_turno` y `expirar_pre_reservas`, con reintento de transitorios en `cambiar_estado_turno`. Verificado con un test que captura el orden de las sentencias SQL.
- [x] 15.5 Frontend: `en_revision` aceptado por el contrato y pantalla "Estamos revisando tu pago" (no dice "La reserva venció" si el barrido canceló el turno).
- [x] 15.6 Frontend: la seña pendiente va a `localStorage` con vencimiento y clave versionada (P15) y se borra al llegar a un estado terminal.
- [x] 15.7 `ts` de la firma solo con dígitos ASCII y largo acotado: cualquier cabecera malformada da 401 (antes `²` o un `ts` gigante daban 500).
- [x] 15.8 La acreditación manual (`validar_transferencia`) re-valida medio, estado y vigencia bajo lock; un test con una lectura vieja la reproduce.

## Nota de verificación (apply, 2026-11-06)

- **Línea base (0.1):** backend 127 tests en verde; Vitest 55; Playwright 6 de 7. La falla previa era `reserva.spec.ts` "R2: la carga inicial no hace cascadas": dependía de la hora de la corrida (esperaba el botón 10:00 en el primer día mostrado, que es "hoy"). No se tocó antes de empezar; al reescribir el archivo (11.2) se hizo que elija el día objetivo (siempre futuro) antes de esperar las 10:00.
- **Corrida final (13.4):** `python -m pytest -q` en backend: **302 passed** (127 de línea base + 175 nuevos). Frontend: `npm run typecheck` y `npm run lint` sin errores, `npm test` **107 passed** (55 + 52), `npm run build` OK. `npm run e2e`: **14 passed** (7 de `reserva.spec.ts` + 7 de `sena.spec.ts`), y `--repeat-each=3` **42 passed** a 360px contra el backend real de Docker Compose con `MP_GATEWAY=fake` y `SENA_BARRIDO_SEGUNDOS=3`. `openspec validate c-06-sena-pagos-turno --strict`: válido. `docker compose config`: válido; `GET /api/health` 200 con el compose levantado (lifespan con el barrido).
- **Entorno local:** el puerto 5433 del host lo ocupaba otro contenedor (`veterinaria-db`); se corrió con Postgres publicado en 5434 por un override de Compose fuera del repo y `E2E_PGPORT=5434` / `TEST_DATABASE_URL`. El repo no cambia el puerto 5433.
- **Ajustes dentro del alcance respecto de design.md:** (1) `GET /api/public/turnos/{id}/sena` también devuelve `inicio`, `fin`, `tratamiento_nombre` y `profesional_nombre` (sin datos de contacto) para poder mostrar "Turno reservado" al volver del checkout, donde no hay estado de la reserva; (2) la transferencia solo se ofrece a la/el paciente si el admin cargó alias y CBU (`medios_habilitados` de la respuesta de reserva ya viene filtrado); (3) un pago `vencido` por cambio de medio que se aprueba mientras el turno sigue vigente se acredita (el dinero llegó y el turno está vivo), vence los demás pendientes; (4) `en_espera -> reservado` manual no existe en `cambiar_estado_turno`: la única vía es la acreditación; (5) el monto de la preferencia viaja a Mercado Pago como literal numérico exacto (`3000.00`), sin pasar por float.
- **Pendiente de decisión del usuario:** no se valida que el `transaction_amount` informado por Mercado Pago coincida con el monto de la seña (no está en el diseño). Ver el reporte del apply.

## Workflow follow-up
- Después de la revisión humana (governance CRÍTICO), archivar con `/opsx:archive c-06-sena-pagos-turno` y marcar `[x]` C-06 en `CHANGES.md`. Corregir allí la referencia a la "migración 005" (la real es `006_sena_pagos`).
- Avisar a C-07 (exponer en el endpoint de cancelación la regla RN-SN-04, que devuelve la seña con 24 h o más, usando `cambiar_estado_turno`), C-09 (mover el barrido al scheduler y disparar el recordatorio al acreditar), C-10 (evento de GCal al acreditar) y C-12 (UI de caja para `a_reembolsar` y `no_reembolsado`).
