# Tasks: c-08-agenda-profesional-panel

> **Governance MEDIO, con cambios CRÍTICOS de auth aprobados por el usuario el 2026-11-09.** Las decisiones O1–O18 están resueltas en `design.md`. Cualquier desvío del diseño, sobre todo en auth, se consulta antes de escribir código.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR: el test falla por la razón correcta antes de implementar. Datos 100 % sintéticos ("Carlos Sintético", +5491144445555; R19). El tiempo se inyecta con `reloj`.

## 0. Línea base

- [x] 0.1 Con `docker compose up -d postgres` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm run typecheck && npm run lint && npm test && npm run e2e` en `frontend-paciente/`, y registrar los conteos. Si algo falla, frenar y reportarlo como falla previa.
- [x] 0.2 Verificar con `ls backend/src/alembic/versions` que `007` sigue libre (C-11 corre en paralelo). Si no lo está, usar el siguiente número y anotarlo en el acta.

## 1. Modelo, ocupación y reglas puras

- [x] 1.1 (O10) RED → GREEN: en `backend/tests/test_panel_migracion.py`, testear que `origen` existe, es `NOT NULL`, rechaza valores fuera de `web`/`manual`/`whatsapp`, y el backfill. Implementar la parte de `origen` de `007_turno_origen_ocupacion` y `Turno.origen`. Verificar `alembic downgrade -1`, `upgrade head` y la suite completa en verde.
- [x] 1.2 (O14) RED → GREEN: en `backend/tests/test_panel_marcado.py` (sin base), testear `ausente_habilitado_desde` y `atendido_habilitado_desde`: inicio + 10 min; tolerancia 0; 00:00 local con un turno cuya fecha UTC difiere de la local; `datetime` sin zona → `ValueError`. Implementar en `app/pagos/estados.py`. Verificar en verde.
- [x] 1.3 (O14) RED → GREEN: en `backend/tests/test_settings_panel.py`, `AUSENTE_TOLERANCIA_MINUTOS` por defecto 10, 0 válido, -1 y texto rechazados nombrando la variable. Implementar en `Settings` y exponerla en `docker-compose.yml`. Verificar en verde y `docker compose config`.
- [x] 1.4 (O14) RED → GREEN: en `backend/tests/test_panel_estados_integration.py`, testear `cambiar_estado_turno(..., habilitado_desde=...)` bajo lock: antes del instante → `MarcadoNoHabilitadoError` sin cambios; exactamente en el instante → acepta; un estado inválido gana como `TransicionInvalidaError`; sin el parámetro, comportamiento actual. Implementar en `app/pagos/service.py`. Verificar que `test_sena_*` y `test_gestion_*` siguen en verde.
- [x] 1.5 RED → GREEN: en `backend/tests/test_panel_acciones.py` (sin base), testear `acciones_permitidas` para cada estado, a cada lado de los bordes de atendido, ausente y la ventana de 24 h, y sin permiso de escritura. Verificar en verde.

- [x] 1.6 (O19) RED → GREEN, base de datos: en `backend/tests/test_ocupacion_atendido_integration.py`, con `INSERT`/`UPDATE` directos: un turno bloqueante superpuesto a un `atendido` de la misma profesional, o del mismo sillón, lo rechaza el propio EXCLUDE (SQLSTATE 23P01, con el nombre de constraint de siempre); superpuesto a un `ausente` se acepta; uno que empieza exactamente en el `fin` del atendido se acepta; pasar un `reservado` a `atendido` nunca choca. Agregar a la 007 el reemplazo de los dos EXCLUDE (D11). Verificar en verde.
- [x] 1.7 (O19) RED → GREEN, migración: la 007 aborta, sin modificar datos y listando los ids, si existen pares que se solaparían con un `atendido`; sin conflictos aplica; `alembic downgrade -1` restaura el predicado de la 001 (después del downgrade, un solape con un `atendido` vuelve a aceptarse) y `upgrade head` lo vuelve a aplicar. Verificar con la suite completa en verde.
- [x] 1.8 (O19) RED → GREEN, aplicación: con un turno marcado `atendido` antes de su hora, verificar que sigue ocupando hasta `fin`:
  - no figura en `GET /api/public/disponibilidad`;
  - la reserva pública y `POST /api/turnos` responden 409;
  - la reprogramación de C-07 a ese horario responde 409 con alternativas;
  - iniciar la seña de una pre-reserva superpuesta responde 409, y una acreditación posterior la deja `a_reembolsar`.

  Un `ausente` libera el horario en los mismos caminos, y el borde en `fin` se acepta. Actualizar el test existente de "estados liberados", que ya no incluye `atendido`. Implementar sumando `atendido` a `ESTADOS_BLOQUEANTES` de `app/turnos/service.py`. REFACTOR: renombrar la tupla de `app/gestion/service.py` a `ESTADOS_GESTIONABLES`. Verificar `test_public_*`, `test_gestion_*`, `test_sena_*` y `test_turnos_*` en verde.

## 2. Protección de `POST /api/turnos` (O3)

- [x] 2.1 RED: en `backend/tests/test_turnos_auth.py`, cubrir sin token → 401, `odontologo` → 403, refresh como Bearer → 401, recepción y admin → 201, sin turno creado en los rechazos. Verificar que fallan.
- [x] 2.2 GREEN: agregar `require_recepcion_o_admin` en `app/turnos/router.py`. Darle autenticación a las llamadas existentes de `test_turnos_api.py` y `test_sena_acreditacion_integration.py` con una fixture de `conftest.py`. Adaptar `e2e/tests/race.spec.js` con un token o retirarlo, dejando constancia en el acta. Verificar la suite completa en verde.

## 3. Refresh en cookie y logout (O2, CRÍTICA aprobada, D10)

- [x] 3.1 Caracterización: en `backend/tests/test_auth_cookie_integration.py`, con cliente `https://test`, escribir primero el test que reproduce el logout actual: refresh revocado hace 16 min y doble logout. Registrar en el acta el resultado real (se espera 500 por el `UNIQUE`).
- [x] 3.2 RED: en el mismo archivo, cubrir: login sin `refresh_token` en el JSON y cookie con `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth`; refresh con cookie y `X-Panel-Csrf` rota y reemplaza la cookie; sin cabecera → 403 `csrf_requerido` sin rotar; sin cookie, inválida o revocada → 401 y cookie borrada; token por body → 401; segundo uso → 401; dos refresh simultáneos → un 200 y un 401, nunca 500. Actualizar a este contrato `test_login_correcto_devuelve_200_con_tokens` y `test_refresh_rotation_blacklistea_jti_anterior`. Verificar que fallan.
- [x] 3.3 GREEN: en `app/auth/router.py` y `schemas.py`, leer el refresh solo de la cookie, validar la cabecera antes, quitar `RefreshIn` y `refresh_token` de las respuestas, `SameSite=Strict`, borrar la cookie con los mismos atributos, y traducir la colisión de `jti` a 401. Verificar 3.2 en verde.
- [x] 3.4 RED → GREEN: cubrir logout: revoca access y cookie; refresh revocado sigue 401 a los 16 min (reloj o fila con antigüedad); segundo logout 200; `jti` de cookie distinto del access queda revocado; cookie borrada. Implementar el horizonte `refresh_token_expire_minutes` y `blacklist_jti` idempotente. Verificar la suite completa en verde.

## 4. Agenda (`turnos/agenda-panel`)

- [x] 4.1 RED: en `backend/tests/test_panel_agenda_integration.py`, cubrir: vista día y semana ordenadas; límite domingo 23:30 y lunes 00:00 local; parámetros inválidos → 422; `odontologo` ve solo lo suyo, otro `profesional_id` → 403, sin profesional → 403 `sin_profesional_asociado`, sin token → 401; `recepcion` y usuario con dos roles ven todo; `en_espera` vigente con `bloquea_agenda: false`, `atendido` con `bloquea_agenda: true`, vencida sin barrer y `cancelado` ausentes; filtros, combinados y vacíos, id inexistente → 422; teléfono solo para recepción/admin; ningún código de gestión; turno sin contacto; `acciones` en 08:00, 09:09:59 y 09:10:00; número de consultas constante. Verificar que fallan.
- [x] 4.2 GREEN: implementar `app/panel/schemas.py`, `service.py` y `router.py` para `GET /api/panel/agenda` y `/opciones` según D1 y D2, y registrar el router. Verificar 4.1 en verde.

## 5. Alta manual (`turnos/gestion-panel`)

- [x] 5.1 RED: en `backend/tests/test_panel_alta_integration.py`, cubrir: alta feliz con `fin` derivado, `origen` manual, sillón asignado, sin `PagoSena` y código devuelto; sillón ocupado e inactivo; profesional ocupada → 409 con alternativas; fuera de franja, pasado, sin offset, teléfono inválido, `fin` o `estado` enviados → 422; franja justa (12:30 sí, 12:45 no); alta sobre `en_espera` → 201 y después pago `a_reembolsar`; dos altas simultáneas → una 201 y una 409; 23P01 forzado → 409; `odontologo` → 403, sin token → 401; auditoría `alta_manual_panel` sin PII; cancelación por código de un manual sin pago. Verificar que fallan.
- [x] 5.2 GREEN: implementar `crear_turno_manual` y `POST /api/panel/turnos` según D3. Verificar 5.1 en verde.
- [x] 5.3 RED → GREEN (delta `pagos/sena-turno`): el alta manual deja exactamente un registro `alta_manual_panel` en `reservado` y ninguno `acreditacion_sena`. Verificar en verde.

## 6. Atendido, ausente y cancelación

- [x] 6.1 RED: en `backend/tests/test_panel_estados_integration.py`, cubrir por endpoint. **Ausente:** 15 min con seña → `no_reembolsado` (R9); 9:59 → 409 `marcado_no_habilitado`; 10:00 exactos → acepta; sin seña → sin pago; `en_espera` y finales → 409 `transicion_invalida`. **Atendido:** el mismo día antes de la hora → acepta, el pago sigue `acreditado` y el horario sigue ocupado; 23:59:59 del día anterior → 409 `marcado_no_habilitado`; 00:00:00 local → acepta; final → 409; inexistente → 404; doble marcado sin duplicar auditoría. **Ambos:** `odontologo` → 403; auditoría con usuario y origen; ninguna publicación; reintentos agotados → 503. Verificar que fallan.
- [x] 6.2 GREEN: implementar los dos endpoints según D4. Verificar 6.1 en verde.
- [x] 6.3 RED: cubrir cancelar: 48 h → `a_reembolsar` y horario libre; 23 h 59 min → 409 `fuera_de_plazo` con límite; 24 h exactas; `en_espera` → `vencido`; final → 409; `odontologo` → 403; auditoría `cancelacion_panel`; un `turno_cancelado` solo para bloqueantes; publicador que falla → 200. Verificar que fallan.
- [x] 6.4 GREEN: implementar `POST /api/panel/turnos/{id}/cancelar` según D4 y D5. Verificar 6.3 y la suite completa en verde.

## 7. `frontend-panel/` (R1, R2, R3)

- [x] 7.1 Crear `frontend-panel/` con la configuración de `frontend-paciente/`, puerto 5174 y proxy, y copiar tokens, `guardas`, `tiempo` y `formato`. Verificar `npm run typecheck`, `npm run lint`, `npm run build` y un test de humo.
- [x] 7.2 RED → GREEN: en `src/lib/sesion.test.ts` y `src/lib/api.test.ts`: access solo en memoria (nada en `localStorage` ni `sessionStorage`); `X-Panel-Csrf` en refresh; dos 401 simultáneos → un único refresh y dos reintentos; 401 tras renovar → sin bucle; uso de `navigator.locks` y funcionamiento sin él; aviso por `BroadcastChannel`; respuestas validadas sin `any`. Implementar `sesion.ts`, `api.ts` y `tipos.ts`.
- [x] 7.3 RED → GREEN: en `Ingreso.test.tsx` y `App.test.tsx`: restauración al abrir con 200 y con 401 sin error visible; ingreso correcto; mismo mensaje para credenciales inválidas; usuario sin rol; sesión vencida; salir con aviso si falla la red; logout desde otra pestaña; nada de la agenda visible sin sesión.
- [x] 7.4 RED → GREEN: en `Agenda.test.tsx`: agenda y opciones en paralelo (R2); vista día y semana; banda "No ocupan horario"; estado como texto; hora de la clínica; error con reintento; filtros; sin acciones para `odontologo`; "Sin datos del paciente".
- [x] 7.5 RED → GREEN: en `AltaManual.test.tsx`: disponibilidad recién al elegir tratamiento y profesional; 409 con alternativas sin perder datos; validación de teléfono; código de gestión una sola vez.
- [x] 7.6 RED → GREEN: en `AccionesTurno.test.tsx`: solo las acciones que informa el servidor; confirmación con aviso de seña; manejo de `marcado_no_habilitado`, `fuera_de_plazo` y `transicion_invalida`. Verificar `npm test`, `npm run lint`, `npm run typecheck` y `npm run build` en verde.

## 8. E2E Playwright y CI (R7)

- [x] 8.1 Crear `playwright.config.ts` con `chromium-360` y `chromium-1280` (Asia/Tokyo), y `e2e/datos.ts` y `e2e/ayudas.ts` con siembra sintética por `pg` y barrera de base local. Verificar `npm run typecheck`.
- [x] 8.2 Escribir `frontend-panel/e2e/sesion.spec.ts` y verificarlo con `--repeat-each=3`: (a) ingreso, recarga y pestaña nueva sin pedir ingreso; la cookie aparece `HttpOnly`, `Secure` y `Strict` a través del proxy de 5174; (b) ningún token en el almacenamiento; (c) dos pestañas a la vez; (d) salir revoca: al recargar pide ingreso; (e) "atrás" después de salir. Si Chromium rechaza la cookie `Secure` en localhost, frenar y consultar.
- [x] 8.3 Escribir `frontend-panel/e2e/agenda.spec.ts` y verificarlo con `--repeat-each=3`: `en_espera` en la banda; `odontologo` solo su agenda y sin acciones; cambio a semana; sin scroll horizontal y objetivos de 48 px a 360 px.
- [x] 8.4 Escribir `frontend-panel/e2e/gestion.spec.ts` y verificarlo con `--repeat-each=3`: alta manual completa; horario tomado → alternativas; dos `POST` simultáneos → 201 y 409, cerrando el pendiente de C-01; ausente con seña → `no_reembolsado`; ausente antes de la tolerancia, con margen de segundos, sin la acción; atendido el mismo día antes de hora, con su horario sin figurar libre en la reserva pública; cancelar a 24 h + 5 min y rechazo a 23 h 55 min.
- [ ] 8.5 Agregar a `.github/workflows/ci.yml` los jobs `frontend-panel` y `e2e-panel` según D8. Verificar que el YAML parsea y que los jobs quedan en verde en la primera corrida remota; hasta entonces, dejar la tarea abierta.

## 9. Usuarios del panel (O4)

- [x] 9.1 RED → GREEN: en `backend/tests/test_panel_usuarios.py`, testear el comando idempotente: crea usuario con rol y profesional; contraseña desde el entorno; falla sin ella, con rol inexistente o con `odontologo` sin profesional; no la registra en logs; doble corrida sin duplicar. Documentarlo en `README.md`. Verificar en verde.

## 10. KB, reglas duras y roadmap

- [x] 10.1 Agregar a `knowledge-base/05_reglas_de_negocio.md` **RN-TU-12** (decisión 2026-11-09, C-08, O14): `atendido` desde las 00:00 del día local del turno; `ausente` desde el inicio más la tolerancia configurable, 10 minutos por defecto; solo desde `reservado` o `confirmado`, por recepción o admin. Verificar con una lectura que RN-TU-12 sigue siendo el siguiente número libre.
- [x] 10.2 Escribir la excepción de O7 en RN-SN-01 y en R8 de `AGENTS.md` y `CLAUDE.md`, con el mismo texto: el alta manual de recepción o admin nace `reservado` sin seña. Verificar con `diff` que la línea R8 es idéntica en los dos archivos.
- [x] 10.3 Registrar el resto de las decisiones en `09_decisiones_y_supuestos.md` y actualizar `04_modelo_de_datos.md` y `03_actores_y_roles.md` si cambian. Actualizar `README.md` con `frontend-panel/`, los endpoints y el contrato de cookie. Verificar que los enlaces existen.
- [x] 10.4 En `CHANGES.md`, registrar con dependencias y governance **`C-14 panel-catalogo-disponibilidad`** (UI de catálogo y disponibilidad sobre `frontend-panel/`, depende de C-08, MEDIO) y **`C-15 auth-hardening-panel`** (rate limiting, blacklist en `get_current_user`, `is_active`, IP real, límite absoluto y roles frescos; depende de C-03 y C-08, CRÍTICO, antes de producción). Actualizar árbol y gates, y marcar como movida a C-14 la promesa de C-04. Verificar con una lectura de esas secciones.
- [x] 10.5 (O19) Actualizar RN-TU-03 en `05_reglas_de_negocio.md` (los EXCLUDE cubren `reservado`, `confirmado` y `atendido`), las restricciones de Turno en `04_modelo_de_datos.md` y la fila de riesgos de `CHANGES.md` sobre la estrategia A. Verificar con `grep` en `knowledge-base/` y `CHANGES.md` que no queda la definición vieja.
- [x] 10.6 En `CHANGES.md`, corregir C-11 con el siguiente número de migración libre (008 si C-08 tomó la 007), quitar de C-12 el `POST /api/panel/turnos/{id}/ausente` duplicado y actualizar la sección C-08. Verificar con `ls backend/src/alembic/versions` y una lectura.

## 11. Verificación integral

- [x] 11.1 **Escenario 1 (Happy Path):** agenda por rol, alta manual, ausente con seña retenida, sesión restaurada. Verificar con 3.2, 4.1, 5.1, 6.1 y 8.2.
- [x] 11.2 **Escenario 2 (Error de Negocio):** odontóloga pidiendo otra agenda u operando, solape 409, ausente a los 9:59, refresh sin cabecera. Verificar con 3.2, 4.1, 5.1 y 6.1.
- [x] 11.3 **Escenario 3 (Caso de Borde):** semana en el límite de zona horaria, carrera de altas y de refresh, 10:00 exactos, 00:00 local. Verificar con 3.2, 4.1, 5.1, 6.1 y 8.4.
- [x] 11.4 Corrida final: `python -m pytest -q`; `npm run typecheck && npm run lint && npm test && npm run build && npm run e2e` en los dos frontends; `openspec validate c-08-agenda-profesional-panel --strict`. Registrar los conteos en este archivo.

## Workflow follow-up

- Después de la revisión humana, archivar con `/opsx:archive c-08-agenda-profesional-panel` y marcar `[x]` C-08 en `CHANGES.md`.
- Proponer C-14 inmediatamente después y C-15 antes de producción.
- Avisar a C-09 y C-10 (consumir la auditoría `alta_manual_panel` y `turno_cancelado` del panel) y a C-12 (usar `frontend-panel/` y los endpoints ya creados).

## Acta de desvío

- **0.1 / 0.2 (línea base):** backend `python -m pytest -q` 426 passed; `frontend-paciente` typecheck y lint limpios, `npm test` 151 passed, `npm run e2e` 21 passed. La 007 estaba libre (última: `006_sena_pagos`).
- **Entorno:** el backend de Compose se reconstruyó con `docker compose up -d --build backend` y `APP_ENV=e2e MP_GATEWAY=fake JWT_SECRET_KEY=<efímera> MP_WEBHOOK_SECRET=ci-secreto-webhook-sintetico SENA_BARRIDO_SEGUNDOS=3`. Para el E2E de `frontend-paciente` hay que exportar además `E2E_MP_WEBHOOK_SECRET` con ese mismo secreto, si no los webhooks firmados dan 401 (no es un defecto del código).
- **3.1 (caracterización, resultado real):** con el código de C-03, el segundo logout con el mismo access y el refresh revocado hace "16 minutos" (fila vencida) terminan **ambos en `sqlalchemy.exc.IntegrityError`** por el `UNIQUE` de `token_blacklist.jti`, o sea un 500 en producción; coincide con lo que anticipaba el diseño. El test de caracterización se reemplazó por los de 3.2 y 3.4.
- **3.3 / 3.4 (`blacklist_jti`):** deja de devolver la fila y pasa a devolver `bool` (True si esta llamada insertó). Es `INSERT ... ON CONFLICT (jti) DO UPDATE ... WHERE expires_at < nuevo ... RETURNING (xmax = 0)`: idempotente, extiende el horizonte y permite que, con dos refresh simultáneos, el que no inserta reciba 401 (nunca 500). Los 401 de `/refresh` además borran la cookie.
- **Cookie `Secure` en localhost (D10):** Chromium la acepta a través del proxy de 5174; no hizo falta frenar ni relajar `Secure`. El E2E 8.2(a) lo verifica (`httpOnly`, `secure`, `sameSite: Strict`, `path: /api/auth`).
- **2.2 (E2E de C-01):** se **retiró** `e2e/` de la raíz (`race.spec.js`, `package.json`, `package-lock.json`, `playwright.config.js`; nunca corrió en CI). La carrera 201/409 queda cubierta, y ahora sí en CI, por `frontend-panel/e2e/gestion.spec.ts` (dos `POST /api/panel/turnos` simultáneos). `test_turnos_api.py` corre autenticado con el override de fixture `client` → `client_recepcion`.
- **Fixtures nuevas en `conftest.py`:** `crear_usuario_panel`, `token_recepcion`, `token_admin`, `client_recepcion` y `bearer`. Helpers nuevos: `tests/alembic_helpers.py` (Alembic por subproceso) y `tests/panel_helpers.py` (mundo sintético, turnos y pagos).
- **1.2 / 4.2 (nombres):** `ausente_habilitado_desde(inicio, tolerancia: timedelta)` y `atendido_habilitado_desde(inicio, zona)` viven en `app/pagos/estados.py`; `acciones_permitidas` vive en `app/panel/acciones.py` (módulo sin I/O) y `MarcadoNoHabilitadoError` en `app/pagos/errores.py`.
- **4.2 (respuesta de la agenda):** además de lo previsto, cada turno trae `vence_en` (vencimiento de la pre-reserva) y los 403 llevan `motivo` (`sin_acceso_al_panel`, `sin_profesional_asociado`, `agenda_ajena`). Una persona sin ninguno de los tres roles recibe 403 en la agenda.
- **9.1 (comando de usuarios):** `python -m app.panel.usuarios --email --nombre --rol [--profesional-id]` con la contraseña en `PANEL_USUARIO_PASSWORD` (12 a 128 caracteres). Repetirlo actualiza nombre, contraseña y profesional, reactiva al usuario y suma el rol sin quitar otros. Documentado en `README.md` y verificado con `docker compose run`.
- **7.x (frontend):** la semana en escritorio es una grilla de **lunes a domingo con una columna por día y los turnos en orden cronológico**, sin filas por hora como en la captura de Stitch: una celda vacía no significa que la profesional atienda a esa hora (ya descartado en la evidencia). `Sesion` suma `MotivoCierre` (`vencida`, `otra_pestana`, `salida`) para que el ingreso explique por qué se vuelve a pedir; `fijarToken` reemplaza al `ingresarConToken` imaginado en el borrador de los tests. Al volver con "atrás" (`pageshow` con `persisted`) la app vuelve a comprobar la sesión.
- **7.x (decisión de UI sin consulta):** el formulario de alta no permite elegir sillón (el servidor asigna uno libre; el endpoint sí lo admite). Sale de D3, que lo hace opcional.
- **8.2–8.4 (E2E):** `chromium-360` y `chromium-1280`, `--repeat-each=3` sin fallas. El E2E de "atendido el mismo día antes de la hora" necesita un horario futuro del mismo día de la clínica; si se corre entre las 23:28 y las 23:59 hora de Buenos Aires se **saltea** a sí mismo (anotado en el test). Se corrió fuera de esa franja (00:0x) y pasa, 3 veces por proyecto. La siembra usa franja 00:00–23:59 todos los días para no depender de la hora.
- **8.5 (cierre diferido):** la tarea queda `[ ]` a propósito; se cierra con la primera corrida remota de CI en verde tras el push (jobs `frontend-panel` y `e2e-panel`), no antes. El change se archivó con 46/47 tareas completas.
- **8.5 (CI):** `frontend-panel` y `e2e-panel` agregados a `ci.yml` (el YAML parsea y define 5 jobs); **queda abierta** hasta la primera corrida remota en verde, como pedía la tarea.
- **10.x:** RN-TU-12 era el siguiente número libre. `AGENTS.md` y `CLAUDE.md` siguen idénticos (solo cambió R8). No se tocó su línea "Total: 13 changes" ni el "Estado actual": conviene actualizarlos al archivar. `CHANGES.md` registra C-14 y C-15, mueve la promesa de C-04, pasa la migración de C-11 a 008 y deja constancia de que "deshacer un `atendido` marcado por error" queda como seguimiento de C-12.

## Nota de verificación (2026-11-10)

- Backend `python -m pytest -q`: **611 passed** (línea base 426; +185 de 007, ocupación con `atendido`, marcado, settings, auth por cookie, agenda, alta, estados, usuarios y acciones). Exit 0.
- `frontend-paciente`: typecheck y lint limpios, `npm test` **151 passed**, `npm run build` ok, `npm run e2e` **21 passed** (sin regresiones por el cambio de auth ni por `atendido` bloqueante).
- `frontend-panel`: `npm run typecheck` y `npm run lint` limpios; `npm test` **151 passed** (9 archivos; exit 0, sin errores sin manejar); `npm run build` ok; `npm run e2e -- --repeat-each=3`: **111 passed, 3 skipped** (el skip es la verificación específica de 360 px en el proyecto de 1280 px), exit 0.
- `openspec validate c-08-agenda-profesional-panel --strict`: válido.
