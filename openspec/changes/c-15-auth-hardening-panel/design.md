# Design: c-15-auth-hardening-panel

> Governance **CRÍTICO** (Auth/Seguridad): análisis y propuesta solamente. Las decisiones no obvias están en la tabla **O1–O17** al final, cada una con opciones y una recomendada. **Todas fueron APROBADAS por el usuario el 2026-11-13 (opción recomendada)**; los specs y `tasks.md` están escritos con la opción recomendada y se ajustan si alguna cambia. No se escribe código de producción ni tests hasta aprobarlas.

## Context

Motivación en `proposal.md` (Why). Estado actual relevado en el código (rama `feat/c-15-auth-hardening-panel`, desde `c02e507`):

- **`app/auth/rbac.get_current_user`** solo decodifica el JWT (firma, `exp`, claims, `type=access`) y arma `PermissionContext` con los `roles` **del token**. No toca la base. Todos los endpoints del panel lo usan, directo o vía `require_role` / `require_recepcion_o_admin`.
- **`app/auth/router.login`**: busca el usuario por email exacto (sin normalizar), no mira `is_active`, y con email inexistente **no ejecuta bcrypt** (diferencia de tiempo medible). Audita `LOGIN_OK`/`LOGIN_FAILED` con `ip = "testclient"` fijo. `logout` también audita `"testclient"`. `refresh` no audita.
- **`refresh`** copia `roles` y `email` del payload, no consulta al usuario. La rotación es "blacklistear el `jti` viejo con `INSERT ... ON CONFLICT`" (`blacklist_jti` devuelve si insertó): eso da un solo ganador (C-08 D10).
- **Access y refresh comparten `jti`** (un `uuid4` por par). La rotación blacklistea ese `jti` hasta el `exp` del refresh, así que **el access de ese par también quedaría revocado** si alguien consultara la blacklist por access. Con varias pestañas que comparten la cookie, cada rotación invalidaría el access de las demás pestañas (renovaciones en cadena). Por eso "consultar la blacklist en `get_current_user`" no puede hacerse sobre el modelo actual sin más (O1).
- **`token_blacklist`** (003): `jti TEXT UNIQUE` + un índice `ix_token_blacklist_jti` redundante con el UNIQUE + `ix_token_blacklist_expires_at`. Sin purga. Logout revoca hasta `ahora + REFRESH_TOKEN_EXPIRE_MINUTES` (7 días).
- **Sin duración máxima**: cada rotación emite un refresh de 7 días nuevos.
- **`Usuario.is_active`** existe (`ActiveMixin`, `BOOLEAN NOT NULL DEFAULT true`) pero nadie la lee en auth. El comando `app.panel.usuarios` **reactiva silenciosamente** (`usuario.is_active = True`) al actualizar, y no hay forma de desactivar.
- **IP:** `app/catalogo/router._ip` usa `request.client.host` con `"testclient"` por defecto; `catalogo/service.py` tiene `ip="testclient"` como default en tres firmas. Uvicorn arranca sin `--proxy-headers` (Dockerfile). En desarrollo el panel pasa por el proxy de Vite (sin `X-Forwarded-For`), así que la IP vista es la del gateway de Docker; en producción el panel se sirve en el mismo origen que `/api` detrás de un proxy (C-08 D10).
- **Redis:** existe desde C-09 para el worker arq (`redis==5.3.1`, `REDIS_URL`); **la API no lo usa** (C-09 O8) y el backend de Compose no depende de él. El job `backend` de la CI no levanta Redis.
- **Límites:** no hay ninguno. C-03 los listaba en su scope ("rate limiting por IP+email") sin implementarlos; C-09 difirió "rate limiting de endpoints públicos con Redis" a C-15 (O13). Los códigos de gestión son `uuid4` (no adivinables), así que en lo público el riesgo es el abuso (ráfagas de pre-reservas `en_espera`, consultas de disponibilidad), no la fuerza bruta.
- **Tests:** `conftest.crear_usuario_panel` crea un usuario real con sus roles y firma un access a mano (`create_access_token` con roles iguales a los de la base); `test_auth_cookie_integration.py` también firma tokens a mano. Los dos dejan de servir tal cual porque el token nuevo necesita una sesión en la base (tarea 3.x los adapta).
- **Frontend panel:** `Sesion.ingresar` trata 401 como credenciales y cualquier otra cosa como `servidor`; `pedirRefresh` cierra la sesión solo con 401 y trata lo demás como `ErrorDeRed` (un 429 ya no cierra la sesión, falta solo el mensaje del ingreso). `salir()` ante 401 renueva y reintenta; con la sesión ya revocada termina igual en la pantalla de ingreso.
- **E2E del panel:** ~34 logins desde la misma IP en la suite (`agenda`, `gestion`, `sesion`, …), con pocos emails: un límite por IP de producción la rompería.
- **Última migración:** `011_google_calendar`. La siguiente es **`012`** (verificar antes del apply: C-14 puede ir en paralelo).

## Goals / Non-Goals

**Goals:**
- Un logout, una desactivación o el vencimiento absoluto cortan el acceso **en el siguiente pedido**, en todas las pestañas, sin depender de que venza el access.
- Una sola consulta indexada por pedido autenticado (sesión + usuario + roles), sin N+1.
- La purga nunca puede reabrir una sesión cerrada (invariante: solo se borra lo que ya no tiene tokens válidos).
- Los límites frenan la adivinación de contraseñas sin permitir que un tercero bloquee la cuenta de la recepción.
- Todo configurable por entorno (R17) y testeable con reloj inyectado, sin dormir.

**Non-Goals:**
- MFA, recuperación de contraseña, complejidad de contraseñas, CAPTCHA.
- UI de gestión de usuarios y sesiones (listar/cerrar sesiones desde el panel).
- Detección de reutilización del refresh con revocación de toda la sesión: rompería el escenario aprobado en C-08 de dos renovaciones simultáneas (una gana y sigue).
- Límites sobre los endpoints autenticados del panel (los cubre la sesión) y sobre webhooks (firmados).
- CORS (si algún día se publica el API con CORS hay que revisar la defensa CSRF de C-08 D10).

## Decisions

### D1. Sesión del panel en el servidor (O1, O12) — migración `012_sesion_panel`

Tabla **`sesion_panel`** (`postgresql-table-design`):

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` PK | |
| `sid` | `UUID NOT NULL UNIQUE` | identificador opaco que viaja en el JWT (claim `sid`); UUID porque es un id opaco expuesto |
| `usuario_id` | `BIGINT NOT NULL` FK `usuario(id) ON DELETE CASCADE` | **índice `ix_sesion_panel_usuario_id`** (R6) |
| `refresh_jti` | `UUID NOT NULL` | `jti` del único refresh vigente de la sesión |
| `creada_en` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | R4 |
| `expira_en` | `TIMESTAMPTZ NOT NULL` | vencimiento absoluto = `creada_en + SESION_MAXIMA_HORAS`; `CHECK (expira_en > creada_en)` |
| `renovada_en` | `TIMESTAMPTZ NULL` | última rotación (diagnóstico) |
| `revocada_en` | `TIMESTAMPTZ NULL` | |
| `motivo_revocacion` | `TEXT NULL` | `CHECK (motivo_revocacion IN ('logout','usuario_desactivado'))` y `CHECK ((revocada_en IS NULL) = (motivo_revocacion IS NULL))` |
| `ip_inicio` | `TEXT NULL` | `CHECK (LENGTH(ip_inicio) <= 45)` (IPv6 máximo) |

Índices: el UNIQUE de `sid` (búsqueda por pedido), `ix_sesion_panel_usuario_id` (FK y "revocar todas las de un usuario"), `ix_sesion_panel_expira_en` (purga).

**Tokens:** cada token tiene **su propio `jti`** (access y refresh dejan de compartirlo) y ambos llevan `sid`. Los claims requeridos pasan a `sub, roles, email, jti, sid, type, iat, exp`. `roles` y `email` siguen en el token (compatibilidad, diagnóstico) pero **no deciden permisos** (D2).

**Login:** crea la sesión (`refresh_jti` = jti del refresh emitido, `expira_en = ahora + máximo`) y emite access con `exp = min(ahora + 15 min, expira_en)` y refresh con `exp = min(ahora + REFRESH_TOKEN_EXPIRE_MINUTES, expira_en)`; la cookie usa ese mismo vencimiento.

**Refresh (compare-and-swap):**
```
UPDATE sesion_panel SET refresh_jti = :nuevo, renovada_en = :ahora
 WHERE sid = :sid AND refresh_jti = :jti_presentado
   AND revocada_en IS NULL AND expira_en > :ahora
 RETURNING usuario_id, expira_en
```
(Con SQLAlchemy Core `update(...).returning(...)`, sin SQL crudo, R14.) Cero filas → 401 + borrar cookie. Dos renovaciones simultáneas: la segunda espera el lock de fila, reevalúa el `WHERE` con el `refresh_jti` ya cambiado y obtiene cero filas → 401, nunca 500. Después, en la misma transacción, lee el usuario (`is_active`) y sus roles; inactivo → rollback y 401. Así se cumple "una sola gana" sin tabla de blacklist.

**Logout:** `UPDATE ... SET revocada_en = ahora, motivo_revocacion = 'logout' WHERE sid IN (:sid_access, :sid_cookie) AND revocada_en IS NULL`. Idempotente por construcción (repetirlo no cambia nada). Como `get_current_user` ahora rechaza un access de sesión revocada, un segundo logout con el mismo access responde 401 (no 500), y el frontend ya maneja ese 401.

**`token_blacklist`** se elimina en la 012 (O12): su único uso era la rotación y el logout, que ahora resuelve `sesion_panel`. El downgrade la recrea vacía con sus índices de la 003 (incluido el redundante, para que el downgrade sea fiel). Al desplegar, todo token viejo (sin `sid`) responde 401: cada usuario ingresa una vez más.

**Por qué no blacklist + claims (O1 b):** funciona, pero necesita dos mecanismos (blacklist por `jti` para la rotación y otra por `sid` para el logout), mezcla dos tipos de clave en una columna, y no permite "revocar todas las sesiones de un usuario" sin conocer sus `sid`. La tabla de sesión da las tres cosas con una fila.

### D2. Verificación en cada pedido (O2)

`get_current_user` pasa a recibir la `AsyncSession` (la misma de la request: FastAPI cachea la dependencia) y hace **una consulta**:

```
SELECT u.id, u.email, u.is_active, s.revocada_en, s.expira_en,
       array_agg(r.nombre) FILTER (WHERE r.nombre IS NOT NULL) AS roles
  FROM sesion_panel s JOIN usuario u ON u.id = s.usuario_id
  LEFT JOIN usuario_rol ur ON ur.usuario_id = u.id LEFT JOIN rol r ON r.id = ur.rol_id
 WHERE s.sid = :sid AND u.id = :sub
 GROUP BY u.id, s.id
```
(ORM/Core, no SQL crudo.) 401 si no hay fila, `revocada_en` no nula, `expira_en <= ahora` o `is_active` falso. El `detail` es genérico ("Sesión inválida o vencida") para no distinguir causas. `PermissionContext` recibe los **roles de la base** y suma `sid`. Firma pública igual (`Depends(get_current_user)`), así que ningún router cambia.

Costo: un lookup por UNIQUE + un join por índice de FK por pedido; despreciable para el volumen de una clínica. Se evita el N+1 y la doble consulta (`me` sigue leyendo `nombre_completo`, puede reutilizar el contexto).

### D3. Duración máxima (O3)
`SESION_MAXIMA_HORAS` (default 12, rango 1–168). El vencimiento es **exclusivo** (`expira_en > ahora` para aceptar). `REFRESH_TOKEN_EXPIRE_MINUTES` sigue existiendo como tope de inactividad, pero en la práctica queda acotado por el máximo. Validación en `Settings` con mensaje que nombra la variable.

### D4. Login endurecido (O14)
- Email normalizado (`strip().lower()`) para la búsqueda y para la clave del límite (el comando de usuarios ya guarda en minúsculas).
- Si el usuario no existe o está inactivo, se ejecuta `bcrypt.checkpw` contra un **hash ficticio** generado una vez por proceso con el mismo costo que los reales, y se responde el mismo 401. Inactivo audita `LOGIN_FAILED` con `datos_despues = {"motivo": "usuario_inactivo"}`.
- bcrypt es CPU: se ejecuta con `asyncio.to_thread` / `run_in_threadpool` para no bloquear el loop (R16). Hoy corre en el loop; se corrige de paso porque D4 suma una verificación más por intento fallido.

### D5. Límite de solicitudes (O4–O9, O17) — `app/shared/limites.py`
- **Puerto** `LimitadorSolicitudes.consumir(clave, maximo, ventana) -> Resultado(permitido, reintentar_en_segundos)` y `reiniciar(clave)`. Adaptadores: **Redis** (producción) y **en memoria** con reloj inyectable (pytest). El dominio no conoce Redis.
- **Algoritmo (O9): ventana fija** por clave: `INCR` + `EXPIRE NX` en un pipeline atómico (o script Lua de 3 líneas), `TTL` para `Retry-After`. Simple, O(1) y suficiente; el pico de hasta 2× en el borde de ventana es aceptable para estos umbrales.
- **Claves** (prefijo `rl:` y versión): `rl:v1:login:ipemail:<ip>:<sha256(email)>`, `rl:v1:login:ip:<ip>`, `rl:v1:login:email:<sha256(email)>`, `rl:v1:refresh:ip:<ip>`, `rl:v1:pub:w:<ip>`, `rl:v1:pub:r:<ip>`. El email va **hasheado** (no queda PII en Redis, R19). IPv6 se usa completa (ver Riesgos).
- **Login (O6):** antes de verificar la contraseña se consultan las tres claves sin incrementar las de fallos; si alguna está llena → 429. Se incrementa `login:ip` en cada intento; `ipemail` y `email` **solo en fallos**; el éxito reinicia `ipemail`. Defaults: par IP+email 5 fallos / 15 min; IP 30 intentos / 15 min; email 20 fallos / 60 min.
- **Refresh (O7):** `refresh:ip` 60 / 15 min, contado antes de validar la cabecera CSRF (un atacante sin cabecera también consume).
- **Públicos (O8):** dependencia `limitar_publico_escritura` en `POST /api/public/turnos`, `POST /api/public/turnos/{id}/sena`, `POST /api/public/gestion/{cancelar,reprogramar,confirmar}` (10 / 10 min); `limitar_publico_lectura` en los `GET` de `/api/public/*` (120 / 1 min). `/api/webhooks/*` y `/api/health` sin límite.
- **429:** `JSONResponse(429, {"detail": "...", "motivo": "demasiados_intentos"}, headers={"Retry-After": str(max(1, ceil(ttl)))})`, con el cuerpo definido por el esquema Pydantic `LimiteSuperadoOut` (`extra="forbid"`) y declarado en `responses={429: ...}` de cada endpoint limitado, para que figure en OpenAPI (R15).
- **Fallo del almacén (O5):** timeout corto (`RATE_LIMIT_TIMEOUT_MS`, 200 ms); ante error o timeout se permite el pedido y se loguea `WARNING "limite no aplicado: <clase de error>"` sin IP ni email, con un rate-limit del propio log (una vez por minuto) para no inundarlo.
- **Configuración:** `RATE_LIMIT_LOGIN_IP_EMAIL_MAX/_VENTANA_SEG`, `RATE_LIMIT_LOGIN_IP_MAX/_VENTANA_SEG`, `RATE_LIMIT_LOGIN_EMAIL_MAX/_VENTANA_SEG`, `RATE_LIMIT_REFRESH_IP_MAX/_VENTANA_SEG`, `RATE_LIMIT_PUBLICO_ESCRITURA_MAX/_VENTANA_SEG`, `RATE_LIMIT_PUBLICO_LECTURA_MAX/_VENTANA_SEG`, `RATE_LIMIT_TIMEOUT_MS`; todos `Field(gt=0)`. **No hay interruptor para apagar el limitador** (O17): en E2E se suben los umbrales de IP.
- **Cliente Redis en la API:** `redis.asyncio` (ya instalado, `redis==5.3.1`), un pool creado en el `lifespan` y cerrado al apagar; la dependencia lo toma de `app.state`. Sin Redis configurado en tests se inyecta el adaptador en memoria por `dependency_overrides`.

### D6. IP real del cliente (O10) — `app/shared/red.py`
- `app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)` (el de `uvicorn.middleware.proxy_headers`, que toma de `X-Forwarded-For` la **última dirección no confiable** desde la derecha cuando el par es de confianza). `TRUSTED_PROXIES`: lista separada por comas de IPs o CIDR; **vacío por defecto** → el middleware no confía en nadie y se usa la IP del socket. Montarlo en la app (no por flag de uvicorn) lo hace testeable con `ASGITransport`.
- `ip_cliente(request) -> str | None`: `request.client.host` validado con `ipaddress.ip_address`; si no hay cliente o no parsea → `None` (nunca un texto inventado). La usan auth, catálogo (se borran los `"testclient"` por defecto de `catalogo/service.py`) y el limitador.
- Sin IP conocida, el limitador usa la clave `desconocida` (todas comparten ventana: es conservador).

### D7. Auditoría (O15, RN-GL-01)
- `LOGIN_OK`, `LOGIN_FAILED` (con `motivo` en `datos_despues`: `credenciales` o `usuario_inactivo`), `LOGOUT`: con `ip_cliente`.
- `LOGIN_BLOQUEADO`: solo cuando un `consumir` pasa de permitido a rechazado (el contador llega exactamente a `maximo + 1`), es decir, una vez por clave y ventana; `entidad = "usuario"`, `entidad_id = NULL` (no se revela ni guarda el email en claro), `datos_despues = {"limite": "ipemail"|"ip"|"email"}`, `ip`.
- `SESIONES_REVOCADAS` desde el comando de desactivación, con `datos_despues = {"cantidad": n}`.
- Los 429 públicos no se auditan (no hay usuario ni acción de gestión interna); solo el aviso de log si el almacén falla.

### D8. Purga (O11)
Trabajo `purga_sesiones` en `app/jobs/registro.py` (`PURGA_SESIONES_HABILITADO`, `PURGA_SESIONES_INTERVALO_SEGUNDOS=3600`, `PURGA_SESIONES_MARGEN_MINUTOS=60`, lotes de 500): `DELETE FROM sesion_panel WHERE id IN (SELECT id ... WHERE expira_en < :ahora - margen ORDER BY id LIMIT 500 FOR UPDATE SKIP LOCKED)` en bucle hasta borrar menos de un lote (ORM/Core). **Invariante:** todo token de una sesión vence a más tardar en `expira_en` (D1), así que borrar con `expira_en < ahora - margen` nunca reabre nada; el margen cubre desfases de reloj. `SKIP LOCKED` hace a dos workers cooperar sin chocar. Usa el índice `ix_sesion_panel_expira_en`.

### D9. Desactivar y reactivar (O13)
`python -m app.panel.usuarios --email X --desactivar` / `--reactivar` (mutuamente excluyentes con el alta; no piden contraseña). Desactivar: `is_active = false` + `UPDATE sesion_panel SET revocada_en, motivo_revocacion='usuario_desactivado' WHERE usuario_id = X AND revocada_en IS NULL` + auditoría, en una transacción. El alta sobre un usuario existente **deja de reactivar** (avisa por stderr). D2 ya rechaza a un inactivo aunque alguien lo desactive por SQL sin revocar sesiones.

### D10. Frontends (O16)
- **Panel:** `ResultadoIngreso` suma `{ ok: false, motivo: 'limite', minutos: number }`; `Ingreso` muestra "Demasiados intentos. Probá de nuevo en N minutos" (singular en 1), `role="alert"`. Función pura `minutosDesdeRetryAfter(cabecera)` (ausente/no numérico/≤60 → 1; redondeo hacia arriba). `pedirRefresh` ya trata 429 como `ErrorDeRed`: se agrega un test que lo fija. Sin `any` (R1), 360 px (R3).
- **Paciente:** `interpretarRespuestaError` y los intérpretes de seña y gestión suman `{ tipo: 'limite', mensaje }` para 429, reutilizando la misma función pura; el wizard conserva el formulario (el estado ya vive en el componente). Sin fetches nuevos (R2 intacta).

### D11. Infra y CI
- `docker-compose.yml`: backend con `REDIS_URL: redis://redis:6379/0`, `depends_on: redis: condition: service_healthy`, y las variables nuevas con defaults seguros (ningún secreto). Se actualiza el comentario "Redis solo lo usa el worker".
- CI: el job `backend` suma un servicio `redis:7-alpine` con healthcheck y `REDIS_URL`, para los tests de integración del adaptador Redis (los demás usan el adaptador en memoria). Los jobs `e2e` y `e2e-panel` exportan `RATE_LIMIT_LOGIN_IP_MAX=1000`, `RATE_LIMIT_REFRESH_IP_MAX=1000`, `RATE_LIMIT_PUBLICO_*_MAX=1000`; el par IP+email queda en su default para que el E2E del bloqueo lo ejercite con un email propio.

### D12. Estrategia de pruebas (Strict TDD)
- **Unit:** `minutosDesdeRetryAfter`, cálculo de vencimientos (`min(...)`), limitador en memoria (ventana, `Retry-After` ≥ 1, reinicio), parseo de `TRUSTED_PROXIES`, `Settings` (rangos y mensajes).
- **Integración (pytest + PostgreSQL real, reloj inyectado):** migración 012 (tipos, CHECK, índices de FK vía `pg_index`, reversibilidad), login/refresh/logout sobre la sesión, CAS concurrente (dos `asyncio.gather`), máximo exclusivo, roles frescos, inactivo, tokens sin `sid`, purga con dos sesiones de DB en paralelo, comando desactivar/reactivar, auditoría con IP y `LOGIN_BLOQUEADO` único, middleware de proxy con `ASGITransport(client=(...))`.
- **Integración Redis (servicio en CI):** adaptador real: `INCR`/`EXPIRE`, TTL, timeout → permitido + aviso.
- **E2E Playwright:** panel (`sesion.spec.ts`): logout invalida el access en la otra pestaña sin recargar; bloqueo tras 6 fallos con un email sintético propio y su mensaje a 360 px. Paciente: mensaje de 429 en la reserva interceptando la respuesta con `page.route` (el comportamiento del backend ya lo prueba pytest). La suite completa de turnos sigue en verde con los umbrales E2E (R7).

## Risks / Trade-offs

- [Todos re-ingresan al desplegar] → Es un único re-login; se avisa en el README y en el acta de despliegue. Alternativa (aceptar tokens sin `sid` hasta que venzan) mantendría vivo justo lo que se quiere cerrar.
- [La API pasa a depender de Redis] → Fail-open (O5) y `depends_on` con healthcheck; Redis no se expone fuera de la red de Compose. Mientras Redis esté caído no hay límites: queda en el log.
- [Una consulta a la base por pedido] → Lookup por UNIQUE + índices de FK; si alguna vez pesa, se puede cachear el resultado por `sid` unos segundos (no hace falta hoy).
- [IP compartida (NAT de la clínica)] → El límite por IP es generoso (30 / 15 min) y el bloqueo fuerte es por IP+email; la recepción no se bloquea por los fallos de otra persona salvo en el email propio.
- [IPv6: un atacante rota direcciones dentro de su /64] → El límite por email (20 fallos/h, desde cualquier IP) cubre la adivinación distribuida. Agrupar por /64 queda como mejora si se observa abuso.
- [Bloqueo del email de la recepción por un tercero] → Solo el límite por email afecta a todas las IPs, con umbral alto y ventana de 1 h, sin bloqueo permanente: es un retraso acotado, no un DoS de la cuenta.
- [Ventana fija permite 2× en el borde] → Aceptado por simplicidad; con 5 fallos son 10 en el peor caso cada 15 min.
- [`TRUSTED_PROXIES` mal configurado en producción] → Vacío por defecto es seguro (no se confía en cabeceras); el README documenta el valor para el proxy real. Una lista demasiado amplia (`0.0.0.0/0`) se rechaza en `Settings`.
- [El access revocado devuelve 401 y el frontend intenta renovar] → Esa renovación también da 401 y se muestra el ingreso: es el comportamiento aprobado en C-08 ("Reintento después de renovar").

## Migration Plan

1. Aprobar O1–O17; ajustar specs y tareas si alguna cambia.
2. `012_sesion_panel` (`down_revision = "011_google_calendar"`): crear `sesion_panel` con índices y CHECK; `DROP TABLE token_blacklist`. Downgrade: recrear `token_blacklist` exactamente como en la 003 (vacía) y borrar `sesion_panel`.
3. Desplegar backend + worker juntos (el backend ya necesita Redis sano). Las sesiones viejas dejan de valer: avisar al personal que ingrese de nuevo.
4. Configurar `TRUSTED_PROXIES` con la IP del proxy de producción y verificar en la auditoría que `LOGIN_OK` guarda la IP pública del equipo.
5. **Rollback:** `alembic downgrade -1` + volver a la imagen anterior; los tokens emitidos con `sid` no sirven en la versión vieja (claims extra no rompen el decode, pero la blacklist vacía los aceptaría hasta su vencimiento) → tras el rollback conviene rotar `JWT_SECRET_KEY` para forzar re-login.

## Auditoría de reglas de negocio (`spec-rules-auditor`, 2026-11-13, sobre la propuesta)

**Dictamen: OBSERVACIONES** (sin bloqueos; una observación corregida en el acto, una queda como supuesto a confirmar).

| Regla | Descripción breve | Estado | Observación |
|---|---|---|---|
| RN-GL-01 | Acciones del panel auditadas (quién, qué, cuándo) | CUBIERTA | IP real en login/logout/catálogo; `LOGIN_BLOQUEADO` único por ventana; `SESIONES_REVOCADAS` al desactivar (O15). El refresh no se audita: no es una acción de gestión. |
| RN-GL-03 / R3 | Mobile-first, 360 px | CUBIERTA | Mensajes de 429 del panel y del paciente con escenario a 360 px y E2E (11.2, 11.3). |
| RN-TU-06 | Reserva pública sin login | CUBIERTA | El límite es por IP; no agrega registro ni login. |
| RN-TU-08 / RN-TU-11 | Gestión solo con código; ventana de 24 h | CUBIERTA | El 429 no cambia el turno y al reintentar rigen las mismas reglas (spec `turnos/gestion-paciente`). |
| R8 / RN-SN-01 | `en_espera` no bloquea agenda | NO AFECTADA | Una reserva rechazada por 429 no crea turno; el límite reduce el abuso de pre-reservas. |
| Matriz RBAC (03) | Permisos por rol; "vale el permiso más amplio" | CUBIERTA | Roles leídos de la base en cada pedido (O2); escenario de rol quitado → 403. |
| R4 / R6 / R14 | Timestamptz, FK indexada, migración reversible sin SQL crudo fuera | CUBIERTA | `sesion_panel` con FK indexada, CHECK, downgrade fiel (tareas 2.1–2.3); CAS y purga con Core. |
| R13 / R15 | Type hints; Pydantic en el borde | OBSERVADA → CORREGIDA | El 429 se definía como `JSONResponse` suelto: se agregó el esquema `LimiteSuperadoOut` declarado en OpenAPI (D5, tarea 6.2). |
| R16 | No bloquear el loop | CUBIERTA | bcrypt a un hilo (D4); Redis asíncrono con timeout. |
| R17 / R18 / R20 | Secretos y config por entorno; Compose con healthchecks; sin `.env` | CUBIERTA | Variables nuevas sin secretos; backend `depends_on` Redis sano; sin interruptor de apagado (O17). |
| R19 / Ley 25.326 | Datos sintéticos; sin PII en logs | CUBIERTA | Emails hasheados en las claves de Redis; avisos de log sin IP ni email; IPs de rangos de documentación en los escenarios. |
| R1 / R2 | TS estricto; sin cascadas | CUBIERTA | Sin fetches nuevos; tipos discriminados para `limite`. |
| R7 | E2E de flujos de turnos | CUBIERTA | Suite completa con umbrales E2E (11.4) + E2E del mensaje de 429 en la reserva. |
| R11 / R12 | Sin commits; conventional commits | CUBIERTA | Workflow follow-up. |

**Supuestos marcados:** `[SUPUESTO / ABIERTO]` O3 — la duración máxima de 12 h es una decisión de negocio (jornada de la clínica) a confirmar con el usuario. Los umbrales de O6–O8 son valores técnicos por defecto, configurables.

**Terna de escenarios:** cada requisito ADDED/MODIFIED de los siete deltas tiene Happy Path, Error de Negocio y Caso de Borde, deterministas y traducibles a pytest/Vitest/Playwright con reloj inyectado.

## Auditoría final de reglas (`spec-rules-auditor`, 2026-11-13, sobre el código y los specs implementados)

**Dictamen: APROBADO** (sin bloqueos). Fuente: `knowledge-base/05_reglas_de_negocio.md` y las reglas duras R1-R21 de `CLAUDE.md`/`AGENTS.md`.

| Regla | Estado | Evidencia en el código y las pruebas |
|---|---|---|
| RN-GL-01 (acciones del panel auditadas) | CUBIERTA | `LOGIN_OK`, `LOGIN_FAILED` (motivo), `LOGOUT`, `LOGIN_BLOQUEADO` (una vez por clave y ventana) y `SESIONES_REVOCADAS` con la IP real (`test_auditoria_ip_integration.py`, `test_limite_login_integration.py`, `test_panel_usuarios.py`); ningún registro guarda `testclient` |
| RN-TU-06 / RN-TU-08 / RN-TU-11 | CUBIERTA | El límite público es por IP y no agrega login; un 429 no cambia el turno y al reintentar rigen las mismas reglas (`test_limite_login_integration.py::test_la_escritura_numero_11_es_429_y_no_crea_turno`) |
| R8 / RN-SN-01 / R9 | NO AFECTADA | Ningún cambio en estados de turno ni de seña |
| Matriz RBAC (03) | CUBIERTA | Roles leídos de la base en cada pedido (`test_rol_quitado_con_la_sesion_abierta_da_403_en_la_caja`) |
| R3 (360 px) | CUBIERTA | E2E `sesion.spec.ts` (g) y `limite.spec.ts` verifican el mensaje de 429 sin scroll horizontal |
| R4 / R6 / R14 | CUBIERTA | `012_sesion_panel`: `TIMESTAMPTZ`, FK con índice, CHECK, downgrade reversible probado (`test_sesion_migracion.py`); CAS, revocación y purga con Core/ORM |
| R13 / R15 / R16 | CUBIERTA | Firmas tipadas; el 429 usa `LimiteSuperadoOut` declarado en OpenAPI (`RESPUESTA_429_OPENAPI`); bcrypt con `run_in_threadpool`; Redis asíncrono con timeout y fail-open |
| R17 / R18 / R20 | CUBIERTA | Variables por entorno sin secretos; backend `depends_on` Redis sano; Redis publicado solo en `127.0.0.1`; ningún `.env` versionado |
| R19 / Ley 25.326 | CUBIERTA | Emails hasheados en las claves de Redis; avisos de log sin IP ni email; datos y IPs sintéticos |
| R1 / R2 | CUBIERTA | Tipos discriminados `limite`, sin `any`; sin fetches nuevos |
| R7 | CUBIERTA | E2E completos de ambos frontends con los umbrales E2E (ver acta) |
| R11 / R12 / R21 | CUBIERTA | Sin commits; frontends solo en `frontend/` |

**Observaciones menores (sin bloqueo):** (1) `SESION_MAXIMA_HORAS=12` sigue siendo un supuesto de negocio a confirmar con la clínica; (2) Compose publica Redis en `127.0.0.1:6379` para correr localmente el test del adaptador real (mismo criterio que Postgres en 5433); (3) `.env.example` no se tocó (el agente no pudo leerlo): las variables nuevas están documentadas en el README y en `knowledge-base/08_arquitectura_propuesta.md`.

**Terna de escenarios:** cada requisito de los siete deltas tiene sus tres escenarios traducidos a pytest, Vitest o Playwright con reloj inyectado (ver tabla de evidencia en el acta de `tasks.md`).

## Decisiones (O1–O17) — APROBADAS (2026-11-13)

| # | Decisión | Opciones | Recomendación (default de specs y tasks) | Estado |
|---|---|---|---|---|
| O1 | Modelo de sesión y revocación | (a) tabla `sesion_panel` en el servidor con `sid` en el JWT: revocación por sesión, máximo absoluto, rotación por compare-and-swap; (b) seguir sin estado: `token_blacklist` + claims `sid`/`auth_time` + `jti` separados, el logout blacklistea el `sid`; (c) mínimo: consultar la blacklist actual en `get_current_user` con el `jti` compartido | **(a)** una fila resuelve revocación, máximo, usuario y "cerrar todas las sesiones"; (c) haría que cada rotación de una pestaña invalide el access de las otras (renovaciones en cadena). | APROBADO (2026-11-13, recomendada) |
| O2 | Qué se verifica en cada pedido autenticado | (a) solo que la sesión no esté revocada; usuario activo y roles solo al renovar (hasta 15 min de desfase); (b) sesión + usuario activo + roles de la base en una consulta por pedido; (c) (a) y además bajar el access a 5 min | **(b)** corte inmediato al desactivar o quitar un rol, con una sola consulta indexada; (c) triplica las renovaciones sin cerrar el hueco. | APROBADO (2026-11-13, recomendada) |
| O3 | Duración máxima absoluta de la sesión | (a) 12 h (`SESION_MAXIMA_HORAS`, una jornada); (b) 24 h; (c) 7 días (igual al refresh actual) | **(a)** una jornada de la clínica; obliga a ingresar cada día y acota un equipo olvidado abierto. **Supuesto de negocio** (confirmar con la clínica). | APROBADO (2026-11-13, recomendada) |
| O4 | Almacén de los contadores de límite | (a) Redis (ya está en el stack; la API pasa a depender de él); (b) tabla de contadores en PostgreSQL; (c) memoria del proceso | **(a)** es lo que C-09 dejó diferido (O13) y no carga la base con escrituras por pedido; (c) no sirve con varios procesos ni sobrevive reinicios. | APROBADO (2026-11-13, recomendada) |
| O5 | Qué pasa si Redis no responde | (a) dejar pasar (sin límite) y loguear un aviso sin PII; (b) cerrar login y refresh con 503 y dejar pasar lo público; (c) cerrar todo con 503 | **(a)** Redis es interno y con healthcheck; (b)/(c) convierten una caída de Redis en "nadie puede ingresar al panel". | APROBADO (2026-11-13, recomendada) |
| O6 | Política de límite del login | (a) por IP+email 5 fallos/15 min + por IP 30 intentos/15 min + por email 20 fallos/60 min, el éxito reinicia el par, sin bloqueo permanente; (b) bloqueo de la cuenta tras N fallos hasta que un admin la libere; (c) solo por IP | **(a)** frena la adivinación local y la distribuida sin que un tercero pueda dejar a la recepción sin acceso; (b) es un DoS servido; (c) no frena botnets ni protege detrás de NAT. | APROBADO (2026-11-13, recomendada) |
| O7 | Límite del refresh | (a) por IP 60/15 min; (b) por sesión 10/min; (c) sin límite (la rotación ya lo acota) | **(a)** corta ráfagas sin molestar a varias pestañas; la rotación por CAS ya impide reutilizar un refresh. | APROBADO (2026-11-13, recomendada) |
| O8 | Endpoints públicos en alcance (diferido de C-09 O13) | (a) todos los `/api/public/*` en dos niveles: escritura 10/10 min por IP, lectura 120/min por IP; webhooks y health excluidos; (b) solo los de escritura; (c) fuera de C-15 (otro change) | **(a)** C-15 es el último paso antes de producción y el limitador ya existe; los códigos de gestión son `uuid4`, el riesgo es abuso, no fuerza bruta. | APROBADO (2026-11-13, recomendada) |
| O9 | Algoritmo de ventana | (a) ventana fija (`INCR` + `EXPIRE`); (b) ventana deslizante con registro (sorted set); (c) token bucket | **(a)** atómico, O(1) y fácil de testear; el pico 2× en el borde es aceptable con estos umbrales. | APROBADO (2026-11-13, recomendada) |
| O10 | IP real detrás de un proxy | (a) `ProxyHeadersMiddleware` de uvicorn montado en la app con `TRUSTED_PROXIES` (vacío = IP del socket); (b) parseo propio de `X-Forwarded-For`; (c) confiar siempre en `X-Forwarded-For` | **(a)** estándar, toma la última dirección no confiable y es testeable; (c) es falsificable por cualquiera (descartada). | APROBADO (2026-11-13, recomendada) |
| O11 | Purga de sesiones vencidas | (a) trabajo `purga_sesiones` en el worker cada hora, borra en lotes de 500 con `SKIP LOCKED` lo vencido hace más de 60 min; (b) borrar al vuelo en cada login; (c) `pg_cron`/particionado | **(a)** usa la base de trabajos de C-09, no suma latencia al login y nunca borra una sesión con tokens válidos (invariante D8). | APROBADO (2026-11-13, recomendada) |
| O12 | Destino de `token_blacklist` | (a) eliminarla en la 012 (el downgrade la recrea vacía); todos re-ingresan una vez; (b) conservarla para la rotación además de la sesión; (c) dejarla sin uso | **(a)** la sesión cubre rotación y logout; mantener dos fuentes de verdad invita a que diverjan. | APROBADO (2026-11-13, recomendada) |
| O13 | Desactivar usuarios | (a) `--desactivar`/`--reactivar` en `app.panel.usuarios`; desactivar revoca todas las sesiones; el alta deja de reactivar en silencio; (b) solo por SQL operativo; (c) endpoint y pantalla de admin | **(a)** sin forma de desactivar, verificar `is_active` no sirve en la práctica; (c) es UI nueva (fuera de alcance, podría ir con C-14). | APROBADO (2026-11-13, recomendada) |
| O14 | Enumeración de emails por tiempo en el login | (a) verificar contra un hash bcrypt ficticio si el email no existe o el usuario está inactivo, y correr bcrypt fuera del loop; (b) dejarlo como está | **(a)** cuesta una línea y cierra la diferencia de tiempo que hoy delata qué emails existen. | APROBADO (2026-11-13, recomendada) |
| O15 | Qué se audita | (a) IP real en `LOGIN_OK`/`LOGIN_FAILED`/`LOGOUT`; `LOGIN_FAILED` con motivo; `LOGIN_BLOQUEADO` una vez por clave y ventana; `SESIONES_REVOCADAS` al desactivar; los 429 públicos no; (b) auditar cada 429; (c) no auditar los límites | **(a)** deja rastro del ataque sin que el propio ataque inunde la auditoría (RN-GL-01). | APROBADO (2026-11-13, recomendada) |
| O16 | Cambios en los frontends | (a) panel: mensaje de bloqueo con minutos desde `Retry-After`, refresh 429 sin cerrar sesión; paciente: mensaje de 429 en reserva, seña y gestión conservando lo cargado; (b) solo el mensaje genérico de error de servidor que ya existe | **(a)** sin el mensaje, la recepción bloqueada ve "el servidor no pudo procesar el ingreso" y reintenta, alargando el bloqueo. | APROBADO (2026-11-13, recomendada) |
| O17 | Límites en tests y E2E | (a) umbrales por entorno sin interruptor de apagado: pytest con adaptador en memoria inyectado + integración contra Redis real (CI suma Redis); E2E con umbrales de IP altos y el par IP+email en su default; (b) `RATE_LIMIT_HABILITADO=false` fuera de producción; (c) limpiar Redis entre tests E2E | **(a)** un interruptor de apagado puede quedar apagado en producción (mismo criterio que `Secure` en C-08 D10). | APROBADO (2026-11-13, recomendada) |
