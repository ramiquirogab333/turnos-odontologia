# Tasks: c-07-cancelacion-reprogramacion-24h

> **Governance MEDIO.** Las decisiones O1–O10 de `design.md` (§Decisiones a confirmar) tienen un default recomendado y los specs están escritos con ese default. Si el usuario cambia alguna antes del apply, se ajustan spec, diseño y estas tareas primero. Durante el apply, cualquier desvío del diseño se consulta antes de escribir código.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR: el test se escribe primero, tiene que fallar por la razón correcta y recién después va la implementación mínima. La verificación de cada tarea es el test que tiene que quedar en verde. Todos los datos son sintéticos ("Carlos Sintético", +5491144445555; R19). Ningún test usa el reloj real para la ventana de 24 h: se inyecta `ahora`.

## 0. Red de seguridad

- [x] 0.1 Confirmar con el usuario las decisiones O1–O10 (o aceptar los defaults) y registrar la respuesta en `design.md` §Decisiones a confirmar. Verificar que la tabla dice "aprobado" con fecha en cada fila.
- [x] 0.2 Con `docker compose up -d postgres` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm run typecheck && npm run lint && npm test && npm run e2e` en `frontend-paciente/`, y registrar la línea base (N tests en verde). Si algo falla antes de empezar, frenar y reportarlo como falla previa, sin arreglarlo.

## 1. Regla de la ventana (dominio puro)

- [x] 1.1 RED → GREEN: en `backend/tests/test_gestion_ventana.py`, testear `dentro_de_ventana(inicio, ahora)` y `limite_cambios(inicio)` en `app/pagos/estados.py` (o `app/gestion/ventana.py` si queda más claro), con `ahora` inyectado: 48 h → true; exactamente 24 h → true; 24 h − 1 s → false; 23 h 59 min → false; inicio ya pasado → false; `datetime` sin zona → `ValueError`; `limite_cambios` de un inicio "2026-11-16T10:00:00-03:00" devuelve "2026-11-15T10:00:00-03:00" con el offset de `APP_TZ`. Hacer que `aplicar_transicion` use la misma función y verificar que `test_sena_estados.py` sigue en verde.
- [x] 1.2 RED → GREEN: en `backend/tests/test_gestion_eventos.py`, testear `EventoTurno` y `NotificadorNulo` de `app/gestion/eventos.py`: el evento no tiene campos de contacto (inspección de `dataclasses.fields`), es inmutable, y `NotificadorNulo.publicar` loguea `tipo` y `turno_id` sin nombre ni teléfono (con `caplog`). Verificar en verde.

## 2. Cancelación: ajustes a `cambiar_estado_turno` (delta `pagos/sena-turno`)

- [x] 2.1 RED: en `backend/tests/test_sena_transiciones_integration.py`, agregar: `en_espera` con pago `en_revision` (monto informado "2500.00") cancelado a 3 h del inicio → turno `cancelado`, pago `a_reembolsar` con el monto informado intacto; `en_espera` con pago `pendiente` → `vencido` y ningún pago `acreditado`/`a_reembolsar`; aprobación por webhook firmado de ese pago después de cancelar → `a_reembolsar` y el turno sigue `cancelado`; la auditoría guarda el `origen` recibido (`cancelacion_paciente`). Verificar que el caso `en_revision` y el del `origen` fallan.
- [x] 2.2 GREEN: en `backend/src/app/pagos/service.py`, `_cambiar_estado_una_vez` acepta `origen`, bloquea también los pagos `en_revision` del turno (mismo orden advisory → turno → pagos) y los pasa a `a_reembolsar` al cancelar un `en_espera`, y `ResultadoCambioEstado` devuelve estado anterior, `profesional_id`, `inicio` y `fin`. Verificar 2.1 en verde y toda la suite `test_sena_*` en verde.

## 3. Endpoints de consulta y cancelación (`/api/public/gestion`)

- [x] 3.1 RED: en `backend/tests/test_gestion_cancelacion_integration.py`, cubrir:
  - 404 con el mismo cuerpo para cabecera ausente, vacía, código desconocido y turno interno sin código, en `GET`, `cancelar` y `reprogramar`.
  - `GET` de un `reservado` a 48 h: `puede_cancelar`/`puede_reprogramar` true, `limite_cambios` con offset -03:00, seña "3000.00" `acreditado`, ningún teléfono en el JSON.
  - `GET` dentro de las 24 h: ambos false con motivo `fuera_de_plazo`; `GET` de un `cancelado`: motivo `turno_no_modificable`.
  - Cancelar `reservado` a 48 h: 200 `cancelado` + `a_reembolsar`, el horario vuelve a `GET /api/public/disponibilidad`, auditoría `cancelacion_paciente`.
  - Cancelar `confirmado` a 23 h 59 min: 409 `fuera_de_plazo` con `limite_cambios`; turno, pago y disponibilidad sin cambios.
  - Exactamente 24 h (con `ahora` inyectado por dependencia de reloj): 200; 24 h − 1 s: 409.
  - Cancelar `en_espera` a 3 h: 200 sin ventana, pago `vencido`.
  - Cancelar `cancelado`, `ausente` (seña `no_reembolsado` intacta, R9) o `atendido`: 409 `turno_no_modificable`.
  - Notificador de prueba: un `turno_cancelado` por cancelación de `reservado`; ninguno para `en_espera` ni para un rechazo; con un notificador que lanza, la respuesta es 200 y el turno queda `cancelado`.
- [x] 3.2 GREEN: implementar `backend/src/app/gestion/schemas.py` (`extra="forbid"`, R15), `service.py` (`consultar_gestion`, `cancelar_turno_publico`), `router.py` con `X-Codigo-Gestion`, la dependencia de reloj (`get_reloj`, sobrescribible en tests) y `get_notificador`; registrar el router en `app/main.py`. Verificar 3.1 en verde.

## 4. Reprogramación

- [x] 4.1 RED: en `backend/tests/test_public_service_bloqueos.py` (o el test de servicio existente), testear que `_cargar_bloqueos(..., excluir_turno_id=X)` no devuelve el turno X y que sin el parámetro el resultado no cambia. GREEN en `app/public/service.py`. Verificar que la suite de C-05 sigue en verde.
- [x] 4.2 RED: en `backend/tests/test_gestion_reprogramacion_integration.py`, cubrir:
  - Feliz a 72 h: 200, mismo id y código, `reservado` en el nuevo horario con `fin` según la duración vigente, mismo pago `acreditado` "3000.00" al 30% y ningún otro pago activo, el horario viejo libre, auditoría `reprogramacion_paciente` con antes/después sin PII, un evento `turno_reprogramado`.
  - `confirmado` → queda `reservado` (O5).
  - 23 h 59 min: 409 `fuera_de_plazo`; exactamente 24 h y nuevo horario superpuesto solo con el propio: 200.
  - Horario ocupado por un `reservado` de la misma profesional: 409 `profesional` con alternativas, turno sin cambios; sin sillón libre: 409 `sillon`.
  - Fuera de franja (12:45 con franja hasta 13:00 para 30 min, y 20:00): 422 `fuera_de_disponibilidad`; mismo horario: 422 `mismo_horario`; pasado o sin offset: 422.
  - `en_espera`: 409 `sena_pendiente`; `atendido`/`ausente`: 409 `turno_no_modificable`.
  - Porcentaje y precio cambiados después de acreditar: la seña no cambia.
  - Dos reprogramaciones concurrentes (`asyncio.gather`) al mismo horario: una 200, otra 409 con alternativas, nunca 500.
  - Red de seguridad: forzar un 23P01 en el `flush` (pre-chequeo salteado con un monkeypatch) → 409, nunca 500.
- [x] 4.3 GREEN: implementar `reprogramar_turno_publico` en `app/gestion/service.py` según design D3 (advisory lock → turno → pago, ventana, franja, pre-chequeo con exclusión, `UPDATE` en el lugar, 23P01/40P01 → 409, reintento de transitorios) y el endpoint `POST /api/public/gestion/reprogramar`. Verificar 4.2 en verde y la suite completa de backend en verde.

## 5. Frontend: pantalla "Gestionar mi turno" a 360px (R1, R2, R3)

- [x] 5.1 RED → GREEN: en `frontend-paciente/src/lib/api.test.ts`, testear `consultarGestion`, `cancelarTurno` y `reprogramarTurno`: cabecera `X-Codigo-Gestion`, ningún código en la URL, y unión discriminada de resultados (ok, 404, 409 `fuera_de_plazo`/`turno_no_modificable`/`sena_pendiente`, 409 de solape con alternativas, 422) sin `any`. Implementar en `src/lib/api.ts` y `src/lib/tipos.ts`; verificar con `npm run typecheck`.
- [x] 5.2 RED → GREEN: en `src/components/GestionTurno.test.tsx`, con Testing Library: lee el código del `hash` y lo borra de la URL; sin hash pide pegar el código; muestra día, hora de la clínica, tratamiento, profesional, seña y "Podés cancelar o cambiar el horario hasta el <límite>"; dentro de las 24 h muestra el aviso "Ya no podés cancelar ni cambiar el turno online…" sin acciones habilitadas; un 404 muestra "No encontramos un turno con ese código". Implementar `GestionTurno.tsx` y la ruta `/gestionar` en `App.tsx`.
- [x] 5.3 RED → GREEN: en `GestionTurno.test.tsx`, cancelar: el diálogo dice "La clínica te va a devolver la seña de $ 3.000,00" (acreditada) o "No se te cobra nada" (`en_espera`), y al confirmar muestra "Turno cancelado"; un 409 `fuera_de_plazo` del servidor muestra el aviso de 24 h. Reprogramar: la disponibilidad se pide recién al tocar "Cambiar horario" (sin fetch al montar, R2), reutiliza `PasoHorario`, confirma y muestra "Turno reprogramado"; un 409 de solape muestra "Ese horario ya no está disponible" con las alternativas. Verificar `npm test`, `npm run lint` y `npm run typecheck` en verde.
- [x] 5.4 RED → GREEN: en `Confirmacion` (test existente o nuevo), el enlace "Gestionar mi turno" apunta a `/gestionar#<código>` y aparece el texto de la ventana de 24 h. Verificar en verde.

## 6. E2E Playwright (R7, 360px, backend real)

- [x] 6.1 Agregar a `frontend-paciente/e2e/ayudas.ts` helpers para sembrar por `pg` un turno público `reservado` con seña `acreditado` (o `en_espera` con pago `pendiente`) con `inicio = ahora + delta` y código conocido, y para leer el estado del turno y del pago. Verificar con `npm run typecheck`.
- [x] 6.2 Escribir `frontend-paciente/e2e/gestion.spec.ts` y verificarlo en verde, repetido 3 veces (`--repeat-each=3`), a 360px:
  - **(a) Borde aceptado:** turno `reservado` a 24 h + 5 min → "Cancelar turno" → "Turno cancelado"; en la base, `cancelado` y pago `a_reembolsar`; el horario vuelve a estar libre.
  - **(b) Borde rechazado:** turno a 23 h 55 min → aviso de 24 h sin acciones; un `POST` directo por `request` devuelve 409 `fuera_de_plazo` y la base no cambia.
  - **(c) Pre-reserva:** turno `en_espera` → cancelar → "No se te cobra nada"; en la base, `cancelado`, pago `vencido` y ningún `a_reembolsar` (R8).
  - **(d) Reprogramación feliz:** turno `reservado` a 3 días → elegir otro horario → "Turno reprogramado"; mismo id, pago `acreditado` intacto.
  - **(e) Horario ocupado:** mientras elige, otro turno `reservado` ocupa ese horario por `pg` → "Ese horario ya no está disponible" con alternativas; elegir una alternativa funciona.
  - **(f) Enlace y layout:** desde la confirmación de una reserva nueva, "Gestionar mi turno" abre la pantalla; sin scroll horizontal ni objetivos táctiles < 48px (`verificarPantalla`) en cada paso.

## 7. Documentación

- [x] 7.1 Actualizar `README.md` con los endpoints `/api/public/gestion/*` y el enlace `/gestionar#<código>`; en la KB: `05_reglas_de_negocio.md` marca RN-TU-02 como confirmada (misma ventana que RN-TU-01, IN-02 resuelta) y agrega las decisiones aprobadas O2–O7/O10 como reglas; `10_preguntas_abiertas.md` cierra IN-02; `09_decisiones_y_supuestos.md` registra O1 y O8. Verificar que los enlaces del README apuntan a archivos que existen.
- [x] 7.2 Corregir en `CHANGES.md` la sección C-07: rutas reales (O1), "R9 (seña retenida en cancelación de `reservado`)" → RN-SN-04 (la seña se devuelve; R9 es solo para ausente), y la nota para C-09/C-10 sobre el puerto `NotificadorTurnos`. Verificar con una lectura de la sección.

## 8. Verificación integral y terna de escenarios (`spec-rules-auditor`)

- [x] 8.1 **Escenario 1 (Happy Path):** cancelación de un `reservado` a 48 h → `a_reembolsar` y horario libre; reprogramación a 72 h conservando id, código y seña. Verificar con 3.1, 4.2 y 6.2a/d.
- [x] 8.2 **Escenario 2 (Error de Negocio):** 23 h 59 min rechazado con 409 `fuera_de_plazo` sin cambios; reprogramación a un horario ocupado con alternativas. Verificar con 3.1, 4.2 y 6.2b/e.
- [x] 8.3 **Escenario 3 (Caso de Borde):** exactamente 24 h aceptado y 24 h − 1 s rechazado; `en_espera` cancelado a 3 h sin ventana y sin caja; dos reprogramaciones concurrentes al mismo horario. Verificar con 1.1, 3.1, 4.2 y 6.2c.
- [x] 8.4 Corrida final: `python -m pytest -q` en verde (línea base + nuevos), `npm run typecheck && npm run lint && npm test && npm run e2e` en verde, y `openspec validate c-07-cancelacion-reprogramacion-24h --strict` sin errores. Registrar en este archivo una nota de verificación con los conteos.

## Workflow follow-up

- Después de la revisión humana, archivar con `/opsx:archive c-07-cancelacion-reprogramacion-24h` y marcar `[x]` C-07 en `CHANGES.md`.
- Avisar a C-08 (cancelar desde el panel con `cambiar_estado_turno` y su propio `origen`), C-09 (implementar `NotificadorTurnos` para cancelar/reprogramar recordatorios y usar `/gestionar#<código>` en el link de WhatsApp; evaluar outbox y rate limiting con Redis), C-10 (implementar `NotificadorTurnos` para borrar o mover el evento de Google Calendar) y C-12 (los `a_reembolsar` por cancelación del paciente aparecen con auditoría `cancelacion_paciente`).

## Acta de desvío

- **Entorno (resuelto):** al principio el daemon de Docker no estaba en ejecución y las tareas con base quedaron bloqueadas; el usuario levantó Docker Desktop y Postgres, y se retomó desde 0.2. El backend de Compose se reconstruyó con `docker compose up -d --build backend` (con `APP_ENV=e2e MP_GATEWAY=fake`, secretos sintéticos exportados en el shell, sin `.env`) y se detuvo al terminar.
- **Tests puros sin conftest:** el `conftest.py` tiene fixtures `autouse` que se conectan a la base, por lo que hasta los tests sin DB fallan sin Postgres. Las tareas 1.1 y 1.2 se ejecutaron con `python -m pytest --noconftest` (no necesitan variables de entorno ni base). En CI y con la base arriba corren igual con el `conftest` normal.
- **5.1:** los tests del cliente de gestión están en `frontend-paciente/src/lib/api.gestion.test.ts` (archivo nuevo) en vez de ampliar `api.test.ts`, para no tocar un archivo estable.
- **1.1:** `dentro_de_ventana` y `limite_cambios` viven en `app/pagos/estados.py`; `limite_cambios` recibe la zona (`tzinfo`) por parámetro para mantener la función pura (el servicio le pasa `ZoneInfo(settings.app_tz)`).
- **Contrato (verificado contra el backend):** `CancelacionResponse = {estado: "cancelado", estado_sena}`; `ReprogramacionResponse = {estado, inicio, fin, estado_sena}`; el 422 puede traer cualquier cuerpo (el cliente lo trata como `horario_invalido`). El backend (3.2/4.3) debe respetarlo o se ajusta el cliente.
- **`ahora` y el advisory lock:** el reloj se toma una vez por solicitud (dependencia `get_reloj`), antes de esperar el lock, no después (D4 pedía lo contrario). `cambiar_estado_turno` de C-06 ya hacía lo mismo; la diferencia es de milisegundos y no cambia ninguna regla. Se deja así para poder inyectar el reloj.
- **Rechazos de reprogramación:** un nuevo inicio ya pasado responde 422 `horario_pasado` (la spec decía "`mismo_horario` o error de validación"); el sin-offset lo rechaza Pydantic (`AwareDatetime`) con 422.
- **Deadlock 40P01 en la reprogramación:** se traduce directo a 409 con alternativas (igual que `reservar_turno_publico`), no se reintenta; solo 40001 se reintenta. El advisory lock hace improbable el deadlock.
- **Pagos `en_revision` al cancelar:** se resuelven en `_cambiar_estado_una_vez` y quedan `a_reembolsar` conservando `monto_reportado`; cada uno deja su propia auditoría con el `origen` recibido. `estado_pago` del resultado es el del pago activo y, si no hay, `a_reembolsar` cuando se resolvió un pago en revisión.
- **Fixtures nuevas en `conftest.py`:** `notificador` (espía) y `reloj` (fija `get_reloj`).

## Nota de verificación (2026-11-06)

- Backend `python -m pytest -q`: **426 passed** (línea base de C-06: 362; +21 de 1.1/1.2 = 383 al retomar; +43 de 2.x, 3.x y 4.x).
- Frontend: `npm run typecheck` y `npm run lint` limpios; `npm test`: **151 passed** (11 archivos; línea base 120); `npm run build` ok.
- E2E Playwright a 360px contra el backend real: `npm run e2e` **21 passed** (reserva 8 + seña 6 + gestión 7); `gestion.spec.ts --repeat-each=3`: **21 passed** (7 x 3).
- `openspec validate c-07-cancelacion-reprogramacion-24h --strict`: válido.
