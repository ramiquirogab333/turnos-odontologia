# Proposal: c-15-auth-hardening-panel

## Why
La auth del panel (C-03, con la cookie de refresh y el logout corregidos en C-08 D10) es **obligatoria de endurecer antes de producción** (CHANGES.md, C-15, O17 de C-08). Hoy, relevado en el código:
- No hay **ningún límite de intentos**: el scope de C-03 lo prometía ("rate limiting por IP+email") y nunca se implementó; tampoco en los endpoints públicos (diferido por C-09, O13).
- `get_current_user` solo decodifica el JWT: **un access sigue sirviendo hasta 15 min después del logout**, y la odontóloga desactivada o degradada conserva sus permisos.
- El **login no mira `usuario.is_active`** y el **refresh copia los roles del token**: un usuario desactivado puede ingresar y renovar indefinidamente.
- La auditoría guarda la IP literal `"testclient"` (login, logout y catálogo).
- No hay **duración máxima de sesión**: la rotación del refresh la extiende para siempre.
- `token_blacklist` crece sin purga, y una purga ingenua volvería ineficaz el logout (C-08 D10).
- Access y refresh **comparten `jti`**: si se consultara la blacklist en cada pedido tal como está, la rotación de una pestaña invalidaría el access de las otras (renovaciones en cadena).

## What Changes
- **Sesión del panel en el servidor (O1):** cada login crea una fila `sesion_panel` con un `sid` opaco que viaja en el JWT. Logout, desactivación y vencimiento revocan la sesión entera (todas las pestañas). Reemplaza a `token_blacklist` (O12). **BREAKING (operativo):** al desplegar, las sesiones vigentes dejan de valer y cada usuario ingresa una vez más.
- **Verificación en cada pedido autenticado (O2):** `get_current_user` comprueba en una sola consulta que la sesión no esté revocada ni vencida, que el usuario esté activo, y toma **los roles de la base** (no del token).
- **Refresh endurecido:** rotación con compare-and-swap sobre la sesión (una sola gana, la otra 401, nunca 500), rechaza usuario inactivo o sesión vencida, emite roles frescos.
- **Duración máxima absoluta de sesión (O3):** `SESION_MAXIMA_HORAS` (12 h recomendado); ni el refresh ni el access vencen después de ese límite.
- **Login:** rechaza usuarios inactivos con el mismo 401 genérico (sin revelar el motivo) y tiempo igualado con un hash ficticio (O14).
- **Límite de solicitudes con Redis (O4–O9, O17):** login por IP+email, por IP y por email; refresh por IP; endpoints públicos `/api/public/*` en dos niveles (escritura estricta, lectura generosa); webhooks excluidos. Responde **429** con `motivo: "demasiados_intentos"` y `Retry-After`. Umbrales por entorno. Con Redis caído, deja pasar y registra un aviso (O5). La API pasa a depender de Redis en Compose (healthcheck, R18).
- **IP real del cliente (O10):** `ProxyHeadersMiddleware` con `TRUSTED_PROXIES` (vacío = IP del socket); una sola función `ip_cliente(request)` para la auditoría y los límites; desaparece `"testclient"`.
- **Auditoría (O15, RN-GL-01):** IP real en `LOGIN_OK`/`LOGIN_FAILED`/`LOGOUT`; `LOGIN_BLOQUEADO` una vez por ventana; `SESIONES_REVOCADAS` al desactivar un usuario.
- **Purga (O11):** trabajo `purga_sesiones` en el worker que borra, en lotes, las sesiones vencidas hace más de un margen; nunca una sesión que todavía puede tener tokens válidos.
- **Desactivar usuarios (O13):** el comando `python -m app.panel.usuarios` suma `--desactivar` / `--reactivar`; desactivar revoca todas las sesiones del usuario.
- **Frontends (O16), 360 px (R3):** el panel muestra "Demasiados intentos…" con los minutos de espera ante un 429 del login, y un 429 del refresh no cierra la sesión; el sitio del paciente muestra un mensaje claro ante un 429 de la reserva o la gestión.
- **Migración `012_sesion_panel`** (reversible, R14): crea `sesion_panel` y elimina `token_blacklist` (el downgrade la recrea).
- **Decisiones abiertas O1–O17** en `design.md`, cada una con opciones y una recomendada. **Todas PENDIENTES** de aprobación del usuario (governance CRÍTICO: no se escribe código hasta aprobarlas).

## Capabilities

### New Capabilities
- `auth/sesion-panel`: ciclo de vida de la sesión del panel en el servidor (creación, verificación en cada pedido, revocación, duración máxima, usuario activo y roles frescos, purga y desactivación de usuarios).
- `plataforma/limite-de-solicitudes`: límites de solicitudes por IP / IP+email / email para login, refresh y endpoints públicos, contrato del 429, comportamiento sin Redis, y resolución de la IP real del cliente detrás de un proxy de confianza.

### Modified Capabilities
- `auth/panel-login`: el login rechaza usuarios inactivos y audita la IP real; la rotación del refresh opera sobre la sesión y toma roles de la base; el logout revoca la sesión entera.
- `auth/panel-acceso-web`: el ingreso informa el bloqueo por demasiados intentos; la renovación no cierra la sesión ante un 429; el alta de usuarios suma desactivar y reactivar.
- `plataforma/trabajos-programados`: el backend también depende de Redis sano en Compose (y sigue atendiendo si Redis cae después); se suma el trabajo periódico de purga de sesiones vencidas.
- `turnos/reserva-publica`: la reserva, la seña y la consulta de horarios informan el 429 sin perder los datos cargados.
- `turnos/gestion-paciente`: consultar, cancelar, reprogramar y confirmar informan el 429 sin cambiar el turno.

## Impact
- **Backend:** `app/auth/` (`rbac.get_current_user` con consulta a la base, `router` de login/refresh/logout, `service` sin blacklist, nuevo `sesiones.py`), nuevo `app/shared/limites.py` (puerto `LimitadorSolicitudes`, adaptador Redis y falso en memoria), `app/shared/red.py` (`ip_cliente`), `app/main.py` (middleware de proxy), `app/catalogo/router.py` y `service.py` (sin `"testclient"`), `app/public/`, `app/gestion/`, `app/pagos/router_public.py` (dependencias de límite), `app/panel/usuarios.py` (desactivar/reactivar), `app/jobs/registro.py` (`purga_sesiones`), `app/models/auth.py`, `app/shared/settings.py`.
- **API:** `POST /api/auth/login`, `POST /api/auth/refresh` y los `/api/public/*` pueden responder 429; todos los endpoints autenticados responden 401 con una sesión revocada, vencida o de un usuario inactivo. Sin cambios de forma en las respuestas exitosas.
- **Base de datos:** migración `012_sesion_panel` (verificar el número antes del apply: C-14 puede ir en paralelo).
- **Infra:** `docker-compose.yml` (backend con `REDIS_URL` y `depends_on: redis service_healthy`; variables `RATE_LIMIT_*`, `SESION_MAXIMA_HORAS`, `TRUSTED_PROXIES`, `PURGA_SESIONES_*`); CI (job `backend` suma un servicio Redis; los E2E fijan umbrales de IP altos).
- **Frontend:** `frontend/panel` (mensaje de 429 en el ingreso; refresh 429 sin cerrar sesión); `frontend/paciente` (mensaje de 429 en reserva, seña y gestión).
- **Docs/KB:** `08_arquitectura_propuesta.md` (variables nuevas, `REDIS_URL` ya no es solo del worker), `04_modelo_de_datos.md` (`sesion_panel` en lugar de `token_blacklist`), `03_actores_y_roles.md` (roles leídos de la base en cada pedido; desactivación), README (proxy de confianza y operación de usuarios).
- **Fuera de alcance:** MFA, recuperación de contraseña, política de complejidad de contraseñas, UI de gestión de usuarios, CAPTCHA, detección de reutilización del refresh con revocación de la familia (rompería el escenario aprobado de dos renovaciones simultáneas), CORS.
