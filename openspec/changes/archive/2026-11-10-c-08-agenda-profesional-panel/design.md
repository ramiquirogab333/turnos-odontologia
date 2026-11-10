# Design: c-08-agenda-profesional-panel

## Context
La motivación está en `proposal.md` y los requisitos en los specs de este change. Esto es lo que se verificó en el código y condiciona el diseño:

**Auth y usuarios**
- **No existe ninguna interfaz de login ni de panel.** `frontend-paciente/` no tiene ninguna pantalla interna; C-03 y C-04 fueron solo backend.
- **La cookie de refresh se emite pero no se usa.** `POST /api/auth/refresh` solo lee el body (`RefreshIn`), contra lo que dice el spec `auth/panel-login`. Login y refresh devuelven además el `refresh_token` en el JSON. La cookie hoy es `Secure`, `SameSite=Lax`, `Path=/api/auth`.
- **Access y refresh comparten `jti`** (un solo `uuid4` por par). El logout blacklistea ese `jti` hasta `ahora + 15 min`. `is_jti_blacklisted` ignora las filas vencidas y `token_blacklist.jti` es `UNIQUE`, sin ningún proceso que purgue. Ver D10.
- **`get_current_user` no consulta la blacklist.** No se cambia en C-08 (C-15).
- **`Usuario.profesional_id` ya existe** (002, FK con índice); el JWT no lo incluye y se lee de la base.
- **`require_recepcion_o_admin` ya existe** en `app/catalogo/router.py`.
- **No hay forma de crear usuarios** y el admin del seed tiene un hash de relleno.
- **`POST /api/turnos` no tiene autenticación** (`app/turnos/router.py`).

**Turnos**
- **La columna `turno.origen` no existe**, aunque `04_modelo_de_datos.md` la define. Última migración: `006_sena_pagos`.
- **`create_turno` de C-01 no sirve tal cual:** no valida disponibilidad, no toma el advisory lock, no guarda contacto ni audita. La garantía real (R5) son los EXCLUDE parciales de la 001 sobre `reservado`/`confirmado`.
- **La reserva pública y la gestión ya resuelven lo mismo** con `_franja_que_contiene`, `_cargar_bloqueos`, `_sillon_libre`, `_alternativas`, `ReservaConflictoError` y `LOCK_RESERVAS`.
- **`cambiar_estado_turno`** aplica los efectos sobre la seña con locks advisory → turno → pago, y audita. **No valida el momento del marcado**, y `test_sena_estados.py` fija ese comportamiento en la función pura.
- **`NotificadorTurnos`** solo modela `turno_cancelado` y `turno_reprogramado`. La acreditación de C-06 no publica por el puerto: deja auditoría `acreditacion_sena`.
- **Estados que ocupan agenda, hoy:** los dos EXCLUDE de la 001 (`turno_no_solape_profesional` y `turno_no_solape_sillon`, `EXCLUDE USING gist (... WITH =, periodo WITH &&) WHERE (estado IN ('reservado', 'confirmado'))`) y la tupla `ESTADOS_BLOQUEANTES` de `app/turnos/service.py`. Esa tupla alimenta `existe_solape` (C-01) y `_cargar_bloqueos` (`public/service.py`), y de ahí la disponibilidad pública, la reserva, las alternativas, la reprogramación de C-07 (`gestion/service.py`) y la revalidación y acreditación de la seña de C-06 (`pagos/service.py`: `_revalidar_horario` y `_acreditar_una_vez`). Por eso `en_espera`, `ausente` y `atendido` pueden coexistir con un turno bloqueante. `gestion/service.py` tiene **otra** tupla con el mismo nombre, que significa "turnos que el paciente puede gestionar", no ocupación.

**Frontend y CI**
- `frontend-paciente/` da el molde: React 19, Vite 8, TS estricto, ESLint con `no-explicit-any`, Vitest, Playwright con backend real en Compose, 360x800, navegador en Asia/Tokyo, sin router.
- El proxy de Vite evita CORS; el backend no configura CORS.
- CI corre `frontend` y `e2e` solo sobre `frontend-paciente/`. `e2e/tests/race.spec.js` (C-01) no corre en CI.

## Goals / Non-Goals

**Goals:**
- Agenda consultable por rol en una sola consulta SQL, sin N+1.
- Alta manual con la misma garantía anti-solape y el mismo orden de locks que la reserva pública.
- Cambios de estado por `cambiar_estado_turno`, sin duplicar reglas de seña.
- Sesión del panel que sobrevive a recargas y pestañas nuevas sin exponer el refresh a JavaScript.
- Base reutilizable de `frontend-panel/` para C-12 y C-14.

**Non-Goals:**
- El resto del endurecimiento de C-03 (C-15).
- Reprogramar desde el panel, confirmar turnos a mano, deshacer un estado final.
- Pacientes, ocupación, caja, resolución de `a_reembolsar`/`en_revision` (C-12).
- UI de catálogo y disponibilidad (C-14).
- Google Calendar en la vista (Flujo 4, paso 3: C-10).
- Auditar lecturas de la agenda (C-13).

## Decisions

### D1. Módulo `app/panel/` y rutas
Módulo nuevo con `schemas.py` (`extra="forbid"`, R15), `service.py`, `router.py`:

| Ruta | Rol | Respuesta |
|------|-----|-----------|
| `GET /api/panel/agenda?vista&fecha&profesional_id&sillon_id` | los tres | `AgendaResponse` |
| `GET /api/panel/agenda/opciones` | los tres | profesionales visibles, sillones activos, tratamientos |
| `POST /api/panel/turnos` | recepción, admin | `TurnoManualCreado` |
| `POST /api/panel/turnos/{id}/ausente` | recepción, admin | `CambioEstadoResponse` |
| `POST /api/panel/turnos/{id}/atendido` | recepción, admin | `CambioEstadoResponse` |
| `POST /api/panel/turnos/{id}/cancelar` | recepción, admin | `CambioEstadoResponse` |

`require_panel` valida que tenga alguno de los tres roles. `get_reloj` y `get_notificador` se reutilizan de `app/gestion/deps.py`. `/opciones` existe porque `/api/admin/*` rechaza a `odontologo`, y una sola llamada evita pedir tres recursos.

### D2. Consulta de la agenda
- Período en hora de la clínica: `[00:00 del día, +1 día)` o `[00:00 del lunes, +7 días)`, convertido a UTC. Un turno pertenece al día en que empieza.
- Un `SELECT` con joins a profesional, sillón y tratamiento, y `LEFT JOIN` al último `PagoSena` por turno.
- Filtro: `estado <> 'cancelado' AND NOT (estado = 'en_espera' AND en_espera_vence_en <= ahora)`.
- Alcance: `odontologo` puro → su `profesional_id` (otro → 403; sin asociar → 403 `sin_profesional_asociado`). Con `recepcion` o `admin`, sin restricción.
- `acciones` lo calcula la función pura `acciones_permitidas(estado, inicio, ahora, puede_escribir, zona, tolerancia)`, sobre las reglas de D4 y `dentro_de_ventana`.
- El teléfono se devuelve solo a recepción y admin (O6).

### D3. Alta manual
`crear_turno_manual(session, data, usuario_id, ahora)`, en una transacción, con el patrón de `reservar_turno_publico`:
1. Valida profesional y tratamiento; `fin = inicio + duracion_minutos` vigente (RN-TU-04/05).
2. `inicio <= ahora` → 422. `_franja_que_contiene` → si no entra, 422 `fuera_de_disponibilidad` (RN-TU-07).
3. `pg_advisory_xact_lock(LOCK_RESERVAS)` y `_cargar_bloqueos`.
4. Profesional ocupada → 409 con alternativas. Sillón: el indicado, activo y libre (si no, 409 `sillon`), o `_sillon_libre`.
5. Inserta `reservado`, `origen='manual'`, `contacto_*`, `codigo_gestion=uuid4()`, sin `PagoSena`, con la auditoría en la misma transacción.
6. `23P01`/`40P01` → rollback y 409 con alternativas, nunca 500 (R5).

No se reutiliza `create_turno` porque habría que cambiarle el contrato; se comparten los helpers de `public/service.py`, como hizo C-07. El alta sobre una `en_espera` se acepta; si después se paga, C-06 la deja `a_reembolsar` (RN-SN-05).

### D4. Cambios de estado y momento del marcado (O14, RN-TU-12)
- Los tres endpoints llaman a `cambiar_estado_turno(..., usuario_id=context.usuario_id, ahora=ahora, origen=...)`. Mapeo: `TurnoInexistenteError` → 404; `TransicionInvalidaError` → 409 `transicion_invalida`; `CancelacionFueraDePlazoError` → 409 `fuera_de_plazo` con `limite_cambios`; `OperacionReintentableError` → 503.
- **Funciones puras nuevas en `estados.py`:**
  - `ausente_habilitado_desde(inicio, tolerancia) = inicio + tolerancia`.
  - `atendido_habilitado_desde(inicio, zona) = 00:00 de la fecha local de inicio en zona`.
- **Aplicación:** parámetro nuevo `habilitado_desde: Callable[[datetime], datetime] | None = None`, evaluado **bajo lock** con el `inicio` real del turno; si `ahora` es anterior, lanza `MarcadoNoHabilitadoError` (409 `marcado_no_habilitado`, con el instante en hora de la clínica). El default `None` deja igual a C-06 y C-07. No va en `aplicar_transicion` porque rompería su contrato probado.
- El orden importa: primero la transición (estados inválidos → `transicion_invalida`), después el momento.
- **Tolerancia:** `Settings.ausente_tolerancia_minutos: int = Field(10, ge=0)`, variable `AUSENTE_TOLERANCIA_MINUTOS`, expuesta en `docker-compose.yml`. Va en settings y no en `configuracion_sena` porque no hay UI de configuración hasta C-14 y evita una migración.
- **`atendido` sigue ocupando el horario hasta su `fin`** (O19, D11).

### D5. Eventos (O15)
La cancelación usa `publicar_sin_romper` con `turno_cancelado`, solo si el estado anterior bloqueaba agenda. Ausente y atendido no publican. El alta manual deja la auditoría `alta_manual_panel`, como la acreditación deja `acreditacion_sena`; C-09 y C-10 consumen ambos orígenes.

### D6. Migración `007_turno_origen_ocupacion` (O10, O19)
- `ALTER TABLE turno ADD COLUMN origen TEXT NOT NULL DEFAULT 'web'` con `CHECK (origen IN ('web','manual','whatsapp'))`. Backfill: `codigo_gestion IS NULL` → `manual`. Sin FK nueva ni índice.
- Reemplaza los dos EXCLUDE: ver D11.
- Reversible (R14). El número se verifica antes de crearla, porque C-11 corre en paralelo.

### D7. Frontend `frontend-panel/`
- **Paquete propio** con la configuración de `frontend-paciente/`, puerto 5174 y proxy `/api`. Se copian `guardas.ts`, `tiempo.ts`, `formato.ts` y los tokens, para no tocar `frontend-paciente/` con workspaces.
- **Sin router:** `App` decide entre `Restaurando`, `Ingreso` y `Agenda`.
- **Sesión:** ver D10.
- **Carga (R2):** al abrir, `refresh` → `me` es secuencial por dependencia real. Después, `Promise.all` de agenda y opciones con `Suspense`. La disponibilidad se pide solo al elegir tratamiento y profesional, con `GET /api/public/disponibilidad`.
- **Vistas:** menos de 768 px, lista por día; desde 1024 px, grilla de lunes a domingo. Las pre-reservas van siempre en una banda aparte (O16).
- **Diseño:** Stitch, tokens existentes, 48 px, foco visible, `prefers-reduced-motion`, estados como texto (`frontend-design`). Sin `any` (R1).
- **Stitch (2026-11-09):** vista día a 360 px y semanal de escritorio con datos 100 % sintéticos. Capturas, prompts y qué se descartó: [`docs/skills-mcp/evidencia-stitch/c-08/README.md`](../../../docs/skills-mcp/evidencia-stitch/c-08/README.md). El HTML queda en Stitch, no en el repo.

### D8. CI y E2E (R7)
- `ci.yml` suma `frontend-panel` y `e2e-panel`, copia de `e2e` con `working-directory: frontend-panel`.
- Playwright con `chromium-360` y `chromium-1280` contra el backend real, navegador en Asia/Tokyo.
- `frontend-panel/e2e/` siembra por `pg` usuarios sintéticos y turnos con el horario deseado.
- La carrera 201/409 de C-01 se cubre con dos `POST /api/panel/turnos` simultáneos en un E2E que sí corre en CI.

### D9. Estrategia de pruebas (Strict TDD)
- **Unit:** rango de fechas, `acciones_permitidas`, habilitación del marcado, sesión con renovación única, componentes.
- **Integración (pytest + PostgreSQL real):** roles, filtros, límites de día y semana con `reloj`, pre-reservas, 23P01 y carrera, cada endpoint de estado, auditoría, notificador espía, y el contrato de cookie de auth.
- **Cookies en pytest:** `http.cookiejar` no reenvía una cookie `Secure` por `http://test`. Los tests de auth usan un cliente con `base_url="https://test"`.
- **E2E:** grupo 8 de tareas.

### D11. `atendido` ocupa la agenda hasta su `fin` (O19)
**Por qué:** recepción marca `atendido` cuando la persona entra al consultorio, a veces antes de su hora (RN-TU-12). Si `atendido` liberara el horario, el sillón quedaría reservable online con la persona sentada. `ausente` sí libera el horario.

**Una sola definición de "ocupa":** `reservado`, `confirmado` y `atendido`. Tiene que coincidir en dos lugares:
1. **Base de datos (garantía, R5):** en la 007, `DROP CONSTRAINT` y `ADD CONSTRAINT` con el mismo nombre de los dos EXCLUDE y el predicado `WHERE (estado IN ('reservado', 'confirmado', 'atendido'))`. Se conservan los nombres porque `motivo_desde_mensaje` los usa para elegir el motivo del 409.
2. **Aplicación (fast-fail):** `ESTADOS_BLOQUEANTES` de `app/turnos/service.py` suma `atendido`. Como todos los cálculos derivan de esa tupla, cambian juntos y sin tocar su código: `existe_solape` (alta interna), `_cargar_bloqueos` (disponibilidad pública, reserva pública, alternativas, alta manual, reprogramación de C-07, revalidación al iniciar la seña y acreditación de C-06) y `bloquea_agenda` de la agenda del panel.

**Lo que no cambia:**
- La tupla homónima de `gestion/service.py` (estados que el paciente puede cancelar o reprogramar, y que publican eventos): un `atendido` sigue sin gestionarse. Se renombra a `ESTADOS_GESTIONABLES` para que nadie las confunda (refactor sin cambio de comportamiento).
- `aplicar_transicion` y la máquina de estados.
- Ninguna transición mete un turno nuevo en el EXCLUDE: `reservado` y `confirmado` → `atendido` ya estaban cubiertos, así que marcar atendido nunca choca.

**Efectos:**
- Una pre-reserva `en_espera` sobre el horario de un atendido, si se paga, queda `a_reembolsar` (RN-SN-05, ya cubierto por C-06).
- Un turno nuevo que empieza exactamente en el `fin` del atendido se acepta (rango `[)`).

**Datos existentes:** hoy se pueden crear turnos sobre un `atendido`. Antes de recrear los EXCLUDE, la 007 busca pares que pasarían a solaparse. Si hay alguno, **aborta con un mensaje que lista los ids**, sin modificar datos; corregirlos es una decisión humana. El `downgrade` vuelve al predicado de la 001, que es más chico y nunca falla.

**Costo:** recrear los EXCLUDE reconstruye el índice GiST con lock exclusivo sobre `turno`, aceptable por el volumen de una clínica.

### D10. Refresh en cookie HttpOnly (O2, CRÍTICA aprobada)
**Contrato**
- La cookie es la única vía del refresh. **El refresh por body se elimina**: `RefreshIn` se borra, y `LoginOut`/`RefreshOut` dejan de tener `refresh_token`. Dejarlo convivir mantendría el token expuesto a JavaScript, que es lo que se quiere evitar. Nadie más lo consume: `frontend-paciente/e2e/ayudas.ts` solo usa `access_token`. Cambian dos tests de `test_auth_integration.py` (`test_login_correcto...` y `test_refresh_rotation...`).
- **Atributos:** `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth`, sin `Domain`, con vencimiento a 7 días (`REFRESH_TOKEN_EXPIRE_MINUTES`). Pasa de `Lax` a `Strict` porque la renovación siempre es un `fetch` desde la propia página. Borrar la cookie repite los mismos atributos.
- `Secure` no se vuelve configurable: un interruptor así podría quedar apagado en producción.

**Restauración:** al cargar, `POST /api/auth/refresh`. Si responde 200, `me` y agenda; si responde 401, pantalla de ingreso sin error. Como el refresh se rota, la cookie se renueva en cada uso.

**CSRF.** Solo `POST /api/auth/refresh` autentica por cookie. Defensas:
1. `SameSite=Strict`: un sitio ajeno no hace viajar la cookie.
2. Cabecera obligatoria `X-Panel-Csrf: 1`, validada antes de leer la cookie (403 `csrf_requerido`). Una cabecera propia dispara preflight y el backend no tiene CORS, así que un origen ajeno no puede enviarla.
- Se descartó el double-submit token: necesita otra cookie legible por JS, sin ganancia frente a esta combinación en un API sin CORS.
- `POST /api/auth/logout` autentica por Bearer, que un sitio ajeno no puede adjuntar, así que no es atacable por CSRF.
- **Si en el futuro el API se publica con CORS, hay que revisar esta defensa.**

**Puerto 5174 y CORS.** El navegador solo habla con `http://localhost:5174` y el proxy de Vite reenvía `/api`, con `Set-Cookie` sin `Domain`. Es mismo origen, así que **no hace falta CORS ni `credentials: 'include'`**. Chromium y Firefox aceptan `Secure` en `localhost`; el E2E lo verifica, y si fallara se frena y se consulta en vez de relajar `Secure`. En producción el panel se sirve en el mismo origen que `/api`.

**Pestañas.** La rotación vuelve peligrosas las renovaciones simultáneas: el perdedor recibiría 401 y cerraría la sesión.
- En cada pestaña, una sola renovación compartida.
- Entre pestañas, `navigator.locks.request('panel-refresh', ...)`: la segunda espera y usa la cookie ya rotada. Sin `navigator.locks`, queda solo la renovación por pestaña.
- En el servidor, la unicidad de `jti` es la garantía: la inserción que pierde se traduce a 401, nunca 500.
- `BroadcastChannel('panel-sesion')` avisa el logout a las demás pestañas.

**Logout (se mueve a C-08 la parte que afecta al refresh).** Revisando el código:
- La revocación vence a los 15 min, pero el refresh dura 7 días. Pasados los 15 min, `is_jti_blacklisted` da falso y el refresh avanza hasta el `INSERT` que choca con el `UNIQUE`: hoy el resultado sería un **500**, no una sesión nueva. O sea que el logout resiste de casualidad, y una purga futura de filas vencidas lo volvería ineficaz. No se ejecutó; la tarea 3.1 lo fija con un test.
- Un segundo logout con el mismo access también chocaría con el `UNIQUE`.
- Con varias pestañas aparece un hueco nuevo: una pestaña con un access viejo revocaría un `jti` distinto del de la cookie, y **el refresh real quedaría vigente 7 días** en el servidor.

Cambios: el logout revoca el `jti` del access y el del refresh de la cookie (si decodifica), hasta `ahora + refresh_token_expire_minutes`; `blacklist_jti` es idempotente; la colisión en refresh responde 401. Con eso, O2 no deja el logout ineficaz.

**Se queda en C-15:** consultar la blacklist en `get_current_user` (el access sigue válido hasta 15 min tras el logout), rate limiting, `is_active`, IP real, y límite absoluto de sesión y roles frescos en cada refresh.

## Risks / Trade-offs
- **[Sesión deslizante de 7 días en una computadora compartida]** → "Salir" revoca de verdad; el límite absoluto queda en C-15.
- **[Un usuario desactivado o con roles nuevos sigue con sus permisos al renovar]** → hoy el refresh copia los roles del token y no revisa `is_active`. La sesión persistente lo hace más visible. Queda en C-15, antes de producción.
- **[Logout sin conexión deja la cookie viva]** → JavaScript no puede borrar una cookie HttpOnly: la pantalla lo avisa y ofrece reintentar.
- **[XSS]** → el refresh no es legible desde JS, pero un XSS podría pedir renovaciones mientras la página esté abierta. Mitigación: sin HTML inyectado y dependencias fijadas.
- **[`ausente` y `atendido` son finales]** → diálogo de confirmación.
- **[La 007 falla si ya hay turnos superpuestos con un `atendido`]** → aborta sin tocar datos y lista los ids, para que se corrijan a mano antes de reintentar.
- **[Un `atendido` marcado por error no se puede deshacer y sigue ocupando el horario]** → corregirlo queda fuera de C-08.
- **[Alta manual sobre una `en_espera` que después se paga]** → C-06 deja el pago `a_reembolsar`; la pre-reserva se ve en la banda.
- **[Turnos manuales sin seña aumentan el riesgo de ausentismo]** → se ven como "Alta manual, sin seña".
- **[Código duplicado entre los dos frontends]** → aceptado hasta que C-12 o C-14 lo justifiquen.
- **[El advisory lock global también serializa las altas manuales]** → trade-off ya aceptado en C-06.

## Migration Plan
1. `alembic upgrade head` aplica la 007. Si aborta por solapes con un `atendido`, corregir esos turnos y reintentar.
2. Deploy del backend. **Cambio incompatible en `/api/auth` y `POST /api/turnos`:** no hay otros clientes.
3. Publicar `frontend-panel/` en el mismo origen que `/api`. Crear usuarios con el comando de O4.
4. **Rollback:** volver al build anterior y `alembic downgrade -1`. Las sesiones abiertas requieren un nuevo ingreso.

## Decisiones resueltas (usuario, 2026-11-09)

| # | Criticidad | Decisión | Elegida | Motivo |
|---|-----------|----------|---------|--------|
| O1 | CRÍTICA | Pantalla de ingreso | **(a)** mínima en C-08 | Sin ella el panel no se puede usar |
| O2 | CRÍTICA | Tokens en el navegador | **(c)** refresh en cookie HttpOnly, dentro de C-08; access en memoria | Cambió respecto del default: recargar, cerrar o abrir pestañas no debe pedir ingreso. Diseño en D10 |
| O3 | CRÍTICA | `POST /api/turnos` sin auth | **(b)** exigir recepción/admin | Hoy permite bloquear agenda sin seña y sin login |
| O4 | CRÍTICA | Alta de usuarios | **(a)** comando idempotente con contraseña por entorno | Mínimo que hace usable el panel (R17) |
| O5 | CRÍTICA | ¿La odontóloga escribe? | **(a)** solo lectura | Matriz RBAC |
| O6 | CRÍTICA | Teléfono para `odontologo` | **(a)** solo recepción/admin | Minimización de datos (Ley 25.326) |
| O7 | CRÍTICA | Seña del turno manual | **(a)** `reservado` sin seña | Excepción aprobada a R8/RN-SN-01; se escribe en el apply |
| O8 | Media | Datos del paciente | **(a)** contacto del turno | `Paciente` exige DNI y su alta llega en C-12 |
| O9 | Media | Alta fuera de franja | **(a)** rechazar | RN-TU-07 es contrato |
| O10 | Media | `Turno.origen` | **(a)** migración 007 | La KB la define |
| O11 | Media | Código de gestión manual | **(a)** se genera y se muestra una vez | C-09 lo necesita |
| O12 | Media | Cancelar desde el panel | **(b)** con ventana de 24 h | Sin esto un alta equivocada no se corrige |
| O13 | Media | Reprogramar desde el panel | **(a)** fuera | No está en el roadmap |
| O14 | CRÍTICA | Momento del marcado | **Nueva:** `atendido` desde las 00:00 del día local del turno; `ausente` desde inicio + tolerancia configurable (10 min) | Cambió respecto del default: la persona puede entrar antes de su hora. Regla nueva RN-TU-12 |
| O15 | Media | Notificaciones | **(a)** | Igual que C-06 |
| O16 | Media | Pre-reservas y cancelados | **(a)** banda aparte, cancelados ocultos | Evita el solape visible |
| O17 | CRÍTICA | Huecos de C-03 | **(a)** change aparte antes de producción (C-15) | Salvo la cookie de refresh y la revocación del logout, que entran por O2 (D10) |
| O18 | Media | UI de catálogo y disponibilidad | **Nueva (c):** change propio justo después de C-08 (C-14), sobre `frontend-panel/` | Fuera de C-08 |
| O19 | Media | ¿`atendido` ocupa la agenda? | **Sí, hasta su `fin`**; `ausente` libera | Recepción lo marca al entrar la persona: liberar el horario dejaría el sillón reservable con alguien sentado. Diseño en D11. Reemplaza la observación previa de que el atendido temprano liberaba el horario |

**Changes nuevos a registrar en el apply:** `C-14 panel-catalogo-disponibilidad` (depende de C-08, governance MEDIO) y `C-15 auth-hardening-panel` (depende de C-03 y C-08, antes de producción, governance CRÍTICO).

## Audit & Compliance Note (spec-rules-auditor)
Re-auditado el 2026-11-09, después de O19, sobre `proposal.md`, este `design.md` y los siete deltas, contra `knowledge-base/05_reglas_de_negocio.md` y R1–R20. **Dictamen: APROBADO.** Todas las reglas afectadas están cubiertas y cada requisito tiene la terna de escenarios. Los cambios de texto en la KB y en las reglas duras quedan como tareas del apply (grupo 10).

| Regla | Estado | Dónde / observación |
|-------|--------|---------------------|
| RN-TU-01 (no cancelar < 24 h) | CUBIERTA | "Cancelar desde el panel" (48 h, 23 h 59 min, 24 h exactas) |
| RN-TU-02, 08, 09, 10, 11 | FUERA DE ALCANCE | Gestión por el paciente; reprogramar fuera (O13) |
| RN-TU-03 / R5 | CUBIERTA | "Sin turnos superpuestos"; alta con concurrencia y 23P01. Con O19, `atendido` entra en el EXCLUDE y en el pre-chequeo: deltas `creacion-sin-solape` y `reserva-publica` (atendido temprano ocupa, ausente libera, borde en `fin`). Texto de RN-TU-03 a actualizar en la tarea 10.5 |
| RN-TU-04 / 05 | CUBIERTA | `fin` derivado, duración vigente |
| RN-TU-06 | NO AFECTADA | La reserva pública no cambia |
| RN-TU-07 | CUBIERTA | "El alta manual respeta la disponibilidad" |
| **RN-TU-12 (nueva, O14)** | CUBIERTA | Atendido: mismo día antes de hora, 23:59:59 del día anterior, 00:00 local. Ausente: 9:59 rechazado, 10:00 aceptado, tolerancia configurable. Ya no es un supuesto: decisión del usuario, redacción en tarea 10.1 |
| RN-SN-01 / R8 | CUBIERTA | `en_espera` no ocupa. El turno manual sin seña es una excepción aprobada (O7), tarea 10.2 |
| RN-SN-02 / R9 | CUBIERTA | "Marcar ausente retiene la seña" |
| RN-SN-04, 05 | CUBIERTAS | Cancelación y pago posterior sobre horario ocupado |
| RN-SN-03, 06–10 | NO AFECTADAS | Sin cambios en cobro, vencimiento o acreditación |
| RN-WA-01 | CUBIERTA POR ENGANCHE | Auditoría `alta_manual_panel` para C-09 |
| RN-GC-01 | FUERA DE ALCANCE | C-10 |
| RN-GL-01 | CUBIERTA | Auditoría con usuario y origen, sin PII |
| RN-GL-03 / R3 | CUBIERTA | El panel adopta 360 px igual |
| R1, R2, R13–R16, R18 | CUBIERTAS | D1, D7, D8 |
| R4, R6, R14 | CUBIERTAS | D6 |
| R7 | CUBIERTA | Grupo 8 de tareas |
| R17 | CUBIERTA | Refresh fuera de JS (D10); contraseña por entorno; tolerancia por entorno |
| R19, R20 | CUBIERTAS | Datos sintéticos; sin archivos en la raíz |
| Matriz RBAC | CUBIERTA | Aislamiento por rol; O3, O5, O6 |
| C-03 `auth/panel-login` | CUBIERTA | Delta alinea código y spec: cookie, CSRF, logout |

**Observaciones sin bloqueo:** las sesiones persistentes aumentan la urgencia de C-15; la 007 puede abortar si ya existen solapes con un `atendido` (D11).
