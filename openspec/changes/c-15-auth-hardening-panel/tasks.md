# Tasks: c-15-auth-hardening-panel

> **Governance CRÍTICO.** Las decisiones **O1–O17** de `design.md` están **PENDIENTES**. Ninguna tarea de código empieza antes de la 0.1. Estas tareas siguen la opción recomendada; si alguna decisión cambia, se ajustan specs, diseño y tareas primero.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR: el test se escribe primero y falla por la razón correcta (no por un import roto). Cada requisito de los specs tiene sus tres escenarios (esperado, error de negocio, caso de borde) y los tests llevan el nombre del escenario. Datos 100 % sintéticos (R19): `recepcion@turnos.test`, `dra.ficticia@turnos.test`, "Paciente Ficticio", `+54911000000xx`, IPs de documentación (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`). Instantes siempre con zona y reloj inyectado (R4), sin `sleep`. Nunca un token, una contraseña ni un email en claro en un assert de log. Sin commits (R11).
>
> Skills a cargar antes de cada grupo: `postgresql-table-design` (grupo 2), `vercel-react-best-practices` y `frontend-design` (grupo 10), `playwright-cli` (grupo 11), `spec-rules-auditor` (12.3).

## 0. Aprobación y línea base

- [x] 0.1 Confirmar con el usuario la tabla O1–O17 de `design.md` y registrar la decisión final de cada fila (con fecha). Si alguna cambia, ajustar specs, diseño y estas tareas antes de seguir. Verificar: ninguna fila PENDIENTE y `openspec validate c-15-auth-hardening-panel --strict` pasa.
- [x] 0.2 Con `docker compose up -d postgres redis` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm test` + `npm run typecheck` en `frontend/paciente` y `frontend/panel`; registrar los conteos en el acta al final de este archivo. Si algo falla, frenar y reportarlo como falla previa.
- [x] 0.3 Verificar con `ls backend/src/alembic/versions` que `012` sigue libre (C-14 puede ir en paralelo); si no, usar el siguiente número y anotarlo en el acta.

## 1. Configuración (D3, D5, D6, D8, O3, O17)

- [x] 1.1 RED → GREEN: `backend/tests/test_settings_auth.py`: `SESION_MAXIMA_HORAS` (default 12, 1–168), cada `RATE_LIMIT_*_MAX` y `_VENTANA_SEG` (defaults de D5, rechazan `0`/`-1`/`abc` nombrando la variable), `RATE_LIMIT_TIMEOUT_MS` (default 200), `TRUSTED_PROXIES` (vacío por defecto; acepta IPs y CIDR separados por comas; rechaza basura y `0.0.0.0/0`/`::/0`), `PURGA_SESIONES_HABILITADO` (true), `PURGA_SESIONES_INTERVALO_SEGUNDOS` (3600, > 0), `PURGA_SESIONES_MARGEN_MINUTOS` (60, ≥ 0). Implementar en `app/shared/settings.py`. Verificar en verde y que los `test_settings_*.py` existentes siguen en verde.
- [x] 1.2 `docker-compose.yml`: backend con `REDIS_URL`, `depends_on: redis: condition: service_healthy` y las variables nuevas con sus defaults (sin secretos, R17); actualizar el comentario "Redis solo lo usa el worker"; worker con las `PURGA_SESIONES_*`. Verificar: `docker compose config` válido y `docker compose up -d --wait postgres redis backend worker` deja los cuatro `healthy`.

## 2. Esquema: migración `012_sesion_panel` (D1, O1, O12) — spec `auth/sesion-panel`

- [x] 2.1 RED: `backend/tests/test_sesion_migracion.py`: tras `upgrade head` existe `sesion_panel` con `sid UUID UNIQUE`, `usuario_id BIGINT` FK con índice cuyo prefijo es la FK (consulta a `pg_index`, R6), instantes `timestamptz` (R4), índice sobre `expira_en`; no existe `token_blacklist`. Invariantes vía ORM: `expira_en <= creada_en` → rechazado; `revocada_en` sin motivo (y al revés) → rechazado; motivo fuera de la lista → rechazado; `ip_inicio` de 46 caracteres → rechazado; borrar el usuario borra sus sesiones. Verificar que falla porque la migración no existe.
- [x] 2.2 GREEN: `backend/src/alembic/versions/012_sesion_panel.py` (`down_revision = "011_google_calendar"`) y modelo `SesionPanel` en `app/models/auth.py` (se quita `TokenBlacklist`), registrado en `app/models/__init__.py` y en la limpieza de `backend/tests/conftest.py`. Verificar: 2.1 en verde y `test_models_metadata.py` en verde.
- [x] 2.3 RED → GREEN: reversibilidad con `alembic_helpers`: `downgrade -1` borra `sesion_panel` y recrea `token_blacklist` idéntica a la 003 (columnas e índices), y `upgrade head` vuelve a pasar. Verificar en verde.
- [x] 2.4 Documentar en `knowledge-base/04_modelo_de_datos.md` la entidad `SesionPanel` (y el ERD) en lugar de `token_blacklist`. Verificar que coincide con la migración.

## 3. Sesiones: creación, verificación por pedido y máximo (D1–D3, O1–O3) — spec `auth/sesion-panel`

- [x] 3.1 RED: `backend/tests/test_sesion_tokens.py` (unit): vencimientos `min(ahora + 15 min, expira_en)` y `min(ahora + refresh, expira_en)`; access y refresh con `jti` distintos y el mismo `sid`; `decode_token` exige `sid`. Verificar que falla.
- [x] 3.2 GREEN: `app/auth/sesiones.py` (crear, rotar por CAS, revocar, revocar todas las de un usuario, cargar contexto) y cambios en `app/auth/service.py` (claims, sin blacklist). Verificar 3.1 en verde.
- [x] 3.3 Adaptar `conftest.crear_usuario_panel` y los tokens firmados a mano de `test_auth_cookie_integration.py` para que creen una sesión real (helper `crear_sesion_sintetica`). Verificar: la suite completa vuelve al conteo de la línea base (0.2) antes de tocar `get_current_user`.
- [x] 3.4 RED: `backend/tests/test_sesion_verificacion_integration.py`: los tres escenarios de "Cada pedido autenticado verifica la sesión…" (vigente → 200; access de sesión cerrada → 401; rol quitado con la sesión abierta → 403 en la caja), más usuario inactivo → 401 y token sin `sid` / `sid` inexistente → 401 ("Un token sin sesión del servidor no se acepta"). Verificar que fallan.
- [x] 3.5 GREEN: `get_current_user` con una sola consulta (D2), `PermissionContext` con roles de la base y `sid`; `me` reutiliza el contexto. Verificar 3.4 en verde, que se emite una única sentencia SQL por pedido (contador de eventos de SQLAlchemy) y que toda la suite sigue en verde (RBAC de C-08, C-11, C-12 incluidos).
- [x] 3.6 RED → GREEN: máximo absoluto con reloj inyectado: renovar a las 19:50 → 200 con vencimientos ≤ 20:00; a las 20:01 → 401 y cookie borrada; a las 20:00:00 exactas → 401. Verificar en verde.

## 4. Login, refresh y logout sobre la sesión (D1, D4, O1, O14) — spec `auth/panel-login`

- [x] 4.1 RED: actualizar `test_auth_integration.py` y `test_auth_cookie_integration.py` a los escenarios MODIFIED (login crea sesión y emite `sid`; refresh rotado invalida `JTI-OLD`; logout revoca refresh y access; refresh revocado sigue 401 tras 16 min; otra pestaña ya rotó → la sesión entera revocada y el access de la otra pestaña 401). Verificar que fallan por la razón correcta.
- [x] 4.2 RED: `backend/tests/test_auth_inactivo_integration.py`: "El login rechaza usuarios inactivos sin revelarlo" (activo 200; inactivo con contraseña correcta → 401 idéntico, sin cookie ni sesión, `LOGIN_FAILED` motivo `usuario_inactivo`; email inexistente → el hash ficticio se verifica, espiando la función de verificación) y "La renovación verifica el usuario y emite roles de la base" (roles sumados aparecen; inactivo por SQL → 401 y cookie borrada; dos renovaciones simultáneas con `asyncio.gather` → exactamente un 200 y un 401, nunca 500, y la sesión sigue para la ganadora). Verificar que fallan.
- [x] 4.3 GREEN: `app/auth/router.py`: login con email normalizado, hash ficticio y bcrypt en hilo (R16); refresh por CAS + usuario + roles; logout revoca las sesiones del access y de la cookie. Verificar 4.1–4.2 en verde y toda la suite en verde.
- [x] 4.4 REFACTOR: quitar `blacklist_jti`, `is_jti_blacklisted` y referencias a `TokenBlacklist`; `rg -n "blacklist|TokenBlacklist" backend/src` sin resultados fuera de la migración 003/012. Verificar suite en verde.

## 5. IP real del cliente y auditoría (D6, D7, O10, O15) — specs `plataforma/limite-de-solicitudes`, `auth/panel-login`

- [x] 5.1 RED: `backend/tests/test_ip_cliente.py` con `ASGITransport(client=...)`: proxy de confianza + `X-Forwarded-For` → IP del cliente; `TRUSTED_PROXIES` vacío + cabecera falsificada → IP del socket; cadena `192.0.2.1, 203.0.113.50` → `203.0.113.50`; sin cliente → `None`. Verificar que falla.
- [x] 5.2 GREEN: `app/shared/red.py` (`ip_cliente`) y `ProxyHeadersMiddleware` en `app/main.py` con `TRUSTED_PROXIES`. Verificar 5.1 en verde.
- [x] 5.3 RED → GREEN: "La auditoría de acceso guarda la IP real del cliente": `LOGIN_OK`/`LOGIN_FAILED`/`LOGOUT` con la IP del socket; sin IP → nulo. Reemplazar `"testclient"` en `auth/router.py`, `catalogo/router.py` y los defaults de `catalogo/service.py`. Verificar en verde y `rg -n testclient backend/src` sin resultados.

## 6. Limitador de solicitudes (D5, O4, O5, O9, O17) — spec `plataforma/limite-de-solicitudes`

- [x] 6.1 RED: `backend/tests/test_limitador_memoria.py` (unit, reloj inyectado): ventana fija, `Retry-After` entre 1 y la ventana, último segundo → 1, ventana vencida → permitido, `reiniciar`, y que la transición permitido → rechazado se informa una sola vez (para `LOGIN_BLOQUEADO`). Verificar que falla.
- [x] 6.2 GREEN: `app/shared/limites.py`: puerto `LimitadorSolicitudes`, adaptador en memoria, respuesta 429 común con el esquema Pydantic `LimiteSuperadoOut` (`motivo: "demasiados_intentos"`, `Retry-After`, declarado en OpenAPI, R15), claves con email hasheado. Verificar 6.1 en verde.
- [x] 6.3 RED → GREEN: `backend/tests/test_limitador_redis_integration.py` (requiere `REDIS_URL`; se salta con motivo explícito si no hay Redis local, nunca en CI): `INCR`/`EXPIRE` atómicos, TTL → `Retry-After`, dos procesos comparten el contador; timeout o Redis caído → permitido y un único aviso de log sin IP ni email por minuto. Adaptador Redis con `redis.asyncio` y pool en el `lifespan`. Verificar en verde con `docker compose up -d redis`.
- [x] 6.4 CI: el job `backend` de `.github/workflows/ci.yml` suma el servicio `redis:7-alpine` con healthcheck y `REDIS_URL`. Verificar: el test 6.3 no se salta en CI (el log lo muestra en `passed`).

## 7. Límites aplicados al login, al refresh y a lo público (D5, O6–O8, O15) — specs `plataforma/limite-de-solicitudes`, `auth/panel-login`

- [x] 7.1 RED: `backend/tests/test_limite_login_integration.py` (adaptador en memoria inyectado): los tres escenarios de "El login se limita…" (4 fallos + éxito reinicia; sexto intento → 429 sin verificar contraseña ni crear sesión; otra IP entra), los de "El 429 no revela si un email existe" (cuerpo idéntico para email registrado e inexistente; mayúsculas y espacios cuentan igual) y `LOGIN_BLOQUEADO` una sola vez por clave y ventana con 30 intentos extra. Verificar que fallan.
- [x] 7.2 GREEN: dependencias de límite en `POST /api/auth/login`. Verificar 7.1 en verde.
- [x] 7.3 RED → GREEN: `backend/tests/test_limite_refresh_integration.py`: 6 renovaciones sin 429; la 61 → 429, cookie intacta y sesión válida; sin `X-Panel-Csrf` → 403 y cuenta para el límite. Implementar en `POST /api/auth/refresh`. Verificar en verde.
- [x] 7.4 RED → GREEN: `backend/tests/test_limite_publico_integration.py`: 15 consultas + 1 reserva sin 429; la escritura 11 → 429 sin crear turno; 200 webhooks firmados de la pasarela falsa sin 429; `GET /api/health` sin límite. Dependencias en `app/public/router.py`, `app/gestion/router.py`, `app/pagos/router_public.py`. Verificar en verde y que `test_public_*`, `test_gestion_*` y `test_sena_*` existentes siguen en verde.
- [x] 7.5 RED → GREEN: "Sin el almacén de contadores la API sigue atendiendo": con un adaptador que lanza o excede el timeout, login válido → 200, lectura pública → 200, y el aviso de log no contiene el email ni la IP. Verificar en verde.

## 8. Desactivar y reactivar usuarios (D9, O13) — specs `auth/sesion-panel`, `auth/panel-acceso-web`

- [x] 8.1 RED: ampliar `backend/tests/test_panel_usuarios.py`: `--desactivar` con dos sesiones → inactivo, ambas revocadas (`usuario_desactivado`), sus tokens 401 y auditoría `SESIONES_REVOCADAS` con `cantidad: 2`; email inexistente → error sin cambios; `--reactivar` → el refresh viejo sigue 401 y el login con contraseña funciona; alta sobre un usuario desactivado → actualiza la contraseña, sigue inactivo y avisa por stderr; `--desactivar` junto con `--rol` → error de uso. Verificar que fallan.
- [x] 8.2 GREEN: `app/panel/usuarios.py` con las dos opciones (sin pedir contraseña) y sin reactivar en el alta. Verificar 8.1 en verde y que los tests previos del comando siguen en verde.

## 9. Purga de sesiones en el worker (D8, O11) — specs `plataforma/trabajos-programados`, `auth/sesion-panel`

- [x] 9.1 RED: `backend/tests/test_purga_sesiones.py`: vencidas hace 2 h se borran y las vigentes quedan; revocada y no vencida se conserva y su refresh sigue 401; dentro del margen se conserva; 1500 vencidas con dos sesiones de DB en paralelo y lotes de 500 → ninguna vencida fuera del margen, ninguna vigente borrada, sin errores; el log solo dice la cantidad. Verificar que falla.
- [x] 9.2 GREEN: función `purgar_sesiones(session, ahora, margen, lote)` y trabajo `purga_sesiones` en `app/jobs/registro.py`, deshabilitable. Verificar 9.1 en verde y que `test_jobs_registro.py` cuenta el trabajo nuevo.

## 10. Frontends (D10, O16) — specs `auth/panel-acceso-web`, `turnos/reserva-publica`, `turnos/gestion-paciente`

- [x] 10.1 RED → GREEN: función pura `minutosDesdeRetryAfter` compartida en cada frontend (`frontend/panel/src/lib/limite.ts`, `frontend/paciente/src/lib/limite.ts`): `600` → 10, `20` → 1, `61` → 2, ausente/`abc`/`0` → 1. Verificar con `npm test` en ambos.
- [x] 10.2 RED → GREEN: panel: `Sesion.ingresar` devuelve `motivo: 'limite'` con minutos ante 429; `Ingreso` muestra "Demasiados intentos. Probá de nuevo en N minutos" (singular con 1) con `role="alert"`; 401 sigue mostrando credenciales incorrectas; test que fija que `renovar()` ante 429 lanza `ErrorDeRed` y no cierra la sesión. Verificar `npm test`, `npm run typecheck`, `npm run lint` en `frontend/panel` (sin `any`, R1).
- [x] 10.3 RED → GREEN: paciente: 429 en reserva, inicio de seña y consulta de horarios → `{ tipo: 'limite' }` con el mensaje "Hiciste muchos pedidos seguidos…", conservando el formulario; 429 en consultar, cancelar, reprogramar y confirmar → mismo mensaje y la operación no se muestra como hecha; 409 y el rechazo de 24 h siguen con sus mensajes. Verificar `npm test`, `npm run typecheck`, `npm run lint` en `frontend/paciente`.

## 11. E2E Playwright (R3, R7)

- [x] 11.1 CI y Compose E2E: los jobs `e2e` y `e2e-panel` exportan `RATE_LIMIT_LOGIN_IP_MAX`, `RATE_LIMIT_REFRESH_IP_MAX`, `RATE_LIMIT_PUBLICO_ESCRITURA_MAX` y `RATE_LIMIT_PUBLICO_LECTURA_MAX` en 1000, y el backend recibe `REDIS_URL`. Verificar que `docker compose --profile e2e up -d --wait postgres redis gcal-falso backend worker` queda sano con esas variables.
- [x] 11.2 `frontend/panel/e2e/sesion.spec.ts`: (f) salir en una pestaña y, en la otra **sin recargar**, el siguiente pedido lleva a la pantalla de ingreso (el access ya no sirve); (g) con un usuario sintético propio, 5 contraseñas incorrectas y una sexta muestra "Demasiados intentos. Probá de nuevo en 15 minutos" a 360 px sin desplazamiento horizontal. Verificar en verde local y en CI.
- [x] 11.3 `frontend/paciente/e2e/limite.spec.ts`: con `page.route` que responde 429 + `Retry-After: 300` a la reserva, el paciente ve el mensaje de 5 minutos en el último paso con sus datos intactos, a 360 px. Verificar en verde.
- [x] 11.4 Correr las suites E2E completas de ambos frontends (C-05…C-12 y C-10 incluidas) con Redis y los umbrales E2E. Verificar: todo en verde, sin tests saltados nuevos.

## 12. Documentación, auditoría y cierre

- [x] 12.1 Actualizar `knowledge-base/08_arquitectura_propuesta.md` (variables `SESION_MAXIMA_HORAS`, `RATE_LIMIT_*`, `TRUSTED_PROXIES`, `PURGA_SESIONES_*`; `REDIS_URL` ahora también de la API), `knowledge-base/03_actores_y_roles.md` (roles leídos de la base en cada pedido; desactivación revoca sesiones) y `README.md` (proxy de confianza, desactivar/reactivar usuarios, re-ingreso al desplegar). Verificar que los comandos del README corren tal como están escritos.
- [x] 12.2 Actualizar `CHANGES.md` §C-15 (scope final, migración `012`, seguimientos) y la nota de C-09 sobre O13. Verificar coherencia con los specs.
- [x] 12.3 Correr `spec-rules-auditor` sobre el código y los specs finales contra `05_reglas_de_negocio.md` y `AGENTS.md`; registrar el dictamen en `design.md` y corregir lo observado. Verificar dictamen APROBADO u OBSERVACIONES sin bloqueos.
- [x] 12.4 Verificación final: `python -m pytest -q` (backend), `npm test` + `npm run typecheck` + `npm run lint` + `npm run build` (ambos frontends), E2E completos, `openspec validate c-15-auth-hardening-panel --strict`. Registrar conteos en el acta.

## Workflow follow-up

- Archivar con `/opsx:archive c-15-auth-hardening-panel` cuando el usuario lo apruebe y marcar `[x]` C-15 en `CHANGES.md`.
- Sin commits ni push salvo pedido explícito (R11); commits en conventional commits (R12).

## Acta

- **Aprobación:** O1–O17 aprobadas por el usuario el 2026-11-13 (opción recomendada); marcadas en `design.md`.
- **Migración:** `012_sesion_panel` (la última en disco era `011_google_calendar`; `012` estaba libre).
- **Línea base (antes):** pytest 1763 passed (HEAD limpio, medido en un worktree aparte con la base en `011`); vitest panel 403, paciente 177; E2E paciente 25 y panel 78 (76 + 2 saltados por diseño, a partir de la lista de tests).
- **Final (después):** pytest **1939 passed** (+176: sesión, límites, purga, usuarios, auditoría, settings, IP; con `REDIS_URL` y los contenedores `backend`/`worker` detenidos para que su barrido no interfiera); vitest panel **424**, paciente **211**; E2E paciente **26 passed**; E2E panel **80 passed, 2 saltados** (los mismos 2 saltados de antes). Typecheck, lint y build limpios en ambos frontends. `openspec validate --strict` válido.
- **Entorno del E2E:** `APP_ENV=e2e`, `RATE_LIMIT_{LOGIN_IP,REFRESH_IP,PUBLICO_ESCRITURA,PUBLICO_LECTURA}_MAX=1000`, `REDIS_URL` en el backend, Google falso (`--profile e2e`). Para correr Compose a mano hace falta `MP_WEBHOOK_SECRET` en el entorno (valor sintético; no se escribe en ningún archivo).
- **Redis desde el host:** Compose publica Redis solo en `127.0.0.1:6379` (mismo criterio que Postgres en 5433) para correr `test_limitador_redis_integration.py`; en CI es un servicio del job `backend` y el test no se salta (falla si falta `REDIS_URL`).
- **Hallazgos al implementar:** (1) los tests de migración de C-08/C-09 fijaban `011_google_calendar` como head: se actualizaron a `012`; (2) `get_reloj` pasó a `app/shared/reloj.py` (se reexporta desde `app.gestion.deps`, el override de los tests sigue funcionando); (3) `test_pacientes_listado` contaba las sentencias del pedido: la verificación de sesión no se cuenta; (4) `frontend/panel/e2e/datos.ts` truncaba `token_blacklist`: ahora `sesion_panel`; (5) un segundo logout con el mismo access responde 401 (la sesión ya está cerrada), nunca 500; (6) el logout revoca también la sesión de la cookie: dos logins en la misma jarra de cookies comparten la última.
- **Pendiente humano:** `.env.example` no se tocó (el agente no pudo leerlo por una regla de denegación); las variables nuevas están en el README y en `knowledge-base/08_arquitectura_propuesta.md`. Confirmar con la clínica `SESION_MAXIMA_HORAS=12` (supuesto de negocio).
