# Sistema de Gestión y Reserva de Turnos Odontológicos

> **Proyecto Académico**  
> **Cátedra:** Metodología de Sistemas — 2° Año, Semestre 1  
> **Autor:** Ramiro Quiroga ([@ramiquirogab333](https://github.com/ramiquirogab333))

---

## 1. Visión y Problema que Resuelve

En consultorios y clínicas odontológicas pequeñas y medianas, la coordinación de turnos suele realizarse de forma fragmentada y manual: mensajes dispersos de WhatsApp, llamadas telefónicas, planillas en papel y calendarios no sincronizados (como Google Calendar).

Esta falta de centralización genera:
- **Ausentismo elevado** por olvido de turnos o falta de recordatorios oportunos.
- **Dobles reservas y superposición** de horarios entre profesionales o por disponibilidad de sillones.
- **Pérdida de tiempo operativo** en recepción confirmando turnos uno por uno.
- **Dificultad para auditar y gestionar** la caja diaria, historias clínicas y coberturas de obras sociales.

El presente proyecto tiene como propósito desarrollar una plataforma integral, moderna y orientada a dispositivos móviles (mobile-first) que automatice la reserva, confirmación y gestión de turnos odontológicos, adaptada a las particularidades operativas de Argentina.

---

## 2. Usuarios y Roles del Sistema

| Rol | Responsabilidad y Casos de Uso Clave |
|---|---|
| **Paciente** | - Visualizar disponibilidad horaria en tiempo real.<br>- Reservar turnos online sin registro obligatorio previo (nombre y teléfono).<br>- Recibir recordatorios y confirmaciones automáticas por WhatsApp.<br>- Cancelar o reprogramar turnos con anticipación mínima de 24 horas. |
| **Odontólogo/a** | - Consultar agenda diaria y semanal por profesional.<br>- Registrar evolución de tratamientos en ficha del paciente.<br>- Evitar solapamiento de consultas y sobreturnos descontrolados. |
| **Recepción / Administración** | - Gestionar disponibilidad de agendas y asignación de sillones de atención.<br>- Administrar pacientes, inasistencias y lista de espera / recupero.<br>- Registrar cobros (Mercado Pago, efectivo, transferencia) y cierres de caja.<br>- Configurar nomenclador y aranceles según obras sociales o particulares. |

---

## 3. Alcance del MVP y Reglas de Negocio

### Funcionalidades Núcleo (MVP)
1. **Reserva online para pacientes:** Flujo ágil en pocos pasos, optimizado para celulares, sin fricción de contraseñas obligatorias.
2. **Políticas de cancelación y reprogramación:** Regla de negocio estricta de **24 horas de anticipación mínima** para liberar el turno y habilitarlo a otros pacientes.
3. **Notificaciones y recordatorios por WhatsApp:** Alertas automáticas previas a la cita con botones de confirmación rápida.
4. **Agenda multi-profesional y sillones con anti-solape:** Control de concurrencia que impide reservar si el profesional o el sillón asignado ya están ocupados.
5. **Panel administrativo:** Monitoreo de ocupación, ausentismo, caja diaria y gestión básica de historias clínicas y odontograma.

### Reglas de Negocio Fundamentales
- **Anticipación de cancelación:** Ningún turno puede ser cancelado o modificado por el paciente con menos de 24 horas de anticipación.
- **Anti-solape estricto:** Un profesional no puede tener dos turnos en el mismo horario, ni dos profesionales pueden compartir el mismo sillón físico en forma simultánea.
- **Duración parametrizable:** La duración de cada turno se calcula según el tipo de tratamiento o consulta programada.

---

## 4. Relevamiento y Estudio de Mercado (Discovery)

Como parte de la fase inicial de análisis, se realizó un relevamiento exhaustivo de más de 18 plataformas nacionales e internacionales del sector odontológico y de salud:

- **Nacionales (Argentina):** DentalSoft Argentina, Bilog, DentalSaaS/DelRioTech, Dentiqa.
- **Latinoamérica:** Dentalink (Chile), DentiDesk (Chile), Doctocliq (Perú), AgendaPro (Chile), Doctoralia (AR/ES), SaludTools (Colombia), Simples Dental (Brasil).
- **Internacionales de referencia:** Open Dental (USA), Curve Dental (USA), tab32 (USA), CareStack / Dentrix Ascend (USA/UK).

### Oportunidad y Diferenciación Local
La mayoría de las herramientas internacionales o genéricas fallan en cubrir la realidad del consultorio en Argentina:
- Integración directa con **Mercado Pago** y transferencias bancarias.
- Nomenclador odontológico argentino y liquidación de **Obras Sociales y Prepagas**.
- Costo y canal de comunicación prioritario a través de **WhatsApp** automatizado.
- Restricción física de **sillones odontológicos** compartidos entre varios especialistas.

El informe completo de relevamiento y la matriz comparativa detallada pueden consultarse en:
- Documento Markdown: [docs/discovery/informe-discovery.md](docs/discovery/informe-discovery.md)
- Reporte de Validación: [docs/discovery/Validación Discovery.md](docs/discovery/Validaci%C3%B3n%20Discovery.md)

---

## 5. Estructura del Repositorio

```text
turnos-odontologia/
├── .active-orchestrator-state.json # Estado estructurado del proceso (fase actual: done)
├── AGENTS.md                       # Instrucciones para agentes (stack, KB, skills, roadmap, reglas R1–R20)
├── CLAUDE.md                       # Copia de AGENTS.md (no editar a mano sin re-sincronizar)
├── .agents/skills/                 # Skills de proyecto instaladas (5): vercel-react-best-practices,
│                                   # frontend-design, postgresql-table-design, playwright-cli, gws-calendar-agenda
├── .atl/skill-registry.md          # Registro de skills (trackeado vía excepción en .gitignore; resto de .atl/ ignorado)
├── .gitignore                      # Configuración de exclusiones de Git (incluye .atl/)
├── .opencode/                      # Comandos y habilidades para flujo guiado por agentes IA
│   ├── commands/                   # Comandos /opsx-* para el ciclo spec-driven
│   └── skills/                     # Habilidades integradas de OpenSpec
├── CHANGES.md                      # Índice canónico de changes C-01..C-16 (roadmap, dependencias y gates)
├── backend/                        # Código backend: FastAPI + SQLAlchemy + Alembic + tests
│   ├── src/
│   │   ├── app/                    # `main` y módulos por dominio: `turnos/`, `auth/`, `catalogo/`, `public/`, `pagos/`, `panel/`, `pacientes/`, `clinica/`, `gestion/`, `models/`, `repositories/`, `db/`, `shared/`
│   │   └── alembic/                # Entorno + migraciones (001..011: agenda con EXCLUDE, modelos, auth, catálogo, reserva pública, seña/pagos, origen/ocupación del turno, ficha/odontograma/presupuestos caja/cierres/devoluciones, recordatorios y Google Calendar)
│   ├── tests/                      # Suite pytest (`conftest.py`, helpers y tests unitarios e integración por change; `pythonpath = src`)
│   ├── pytest.ini                  # `asyncio_mode = auto`, `testpaths = tests`, `pythonpath = src`
│   ├── requirements.txt            # Pins del backend
│   ├── alembic.ini                 # `script_location = src/alembic` (correr desde `backend/`)
│   └── Dockerfile                  # Build con contexto `./backend` (`COPY src/`, `PYTHONPATH=/code/src`)
├── docker-compose.yml              # postgres:16 + backend con healthcheck (host 5433→5432)
├── .env.example                    # Plantilla de env (copiar a .env; nunca commitear .env)
├── docs/
│   └── discovery/
│       ├── informe-discovery.md    # Informe detallado de relevamiento de requerimientos y competidores
│       └── Validación Discovery.md # Reporte de auditoría y validación de fuentes de competidores
├── frontend/                       # Todos los clientes web (R21: todo frontend nuevo va en frontend/<nombre>)
│   ├── paciente/                   # Reserva pública y gestión del turno por el paciente (React + Vite, puerto 5173)
│   └── panel/                      # Panel interno de la clínica (C-08): ingreso, agenda, alta manual y acciones (React + Vite, puerto 5174)
├── knowledge-base/                 # Base de conocimiento (12 archivos: 01..11 + README)
├── openspec/
│   ├── config.yaml                 # Configuración del workflow de especificaciones
│   ├── changes/                    # Cambios propuestos y archivados (los changes archivados están en `archive/`: C-01..C-08 y C-11)
│   └── specs/                      # Specs vigentes por capacidad (`turnos/`, `auth/`, etc.)
├── skills-lock.json                # Lockfile de versions de las skills instaladas
└── README.md                       # Documentación general del repositorio
```

### Base de conocimiento, roadmap y skills
- **Base de conocimiento:** ver [knowledge-base/README.md](knowledge-base/README.md) — visión, actores, modelo de datos (13 entidades), 17 reglas de negocio, funcionalidades US-001..US-012, flujos, arquitectura propuesta, decisiones y preguntas abiertas.
- **Roadmap de implementación:** ver [CHANGES.md](CHANGES.md) — secuencia atómica C-01 (crear-turno-sin-solape, `[x]` archivado 2026-10-01) → C-16 (UI de ficha y presupuestos; C-13 es auditoría y exportación), con árbol de dependencias, gates de paralelismo y camino crítico. Leer antes de ejecutar cualquier `/opsx:propose`.
- **Skills de proyecto:** `.agents/skills/` + [skills-lock.json](skills-lock.json), registradas en [.atl/skill-registry.md](.atl/skill-registry.md). Cobertura: booking mobile-first, panel/agenda, modelos Postgres anti-solape, E2E con Playwright y sync con Google Calendar.

### Inicio rápido paso a paso (verificado contra los archivos reales)
1. Clonar: `git clone <url-del-repo> && cd turnos-odontologia`.
2. Crear y activar venv: `python -m venv .venv` → en Windows `cmd /c .venv\Scripts\activate` (nunca commitear el `.env` real — R17).
3. Instalar (ver [`backend/requirements.txt`](backend/requirements.txt)): `pip install -r backend/requirements.txt`.
4. Configurar entorno (ver [`.env.example`](.env.example)): copiar a `.env` (`DATABASE_URL=postgresql+asyncpg://turnos:turnos@localhost:5433/turnos`). **`JWT_SECRET_KEY` es obligatoria** y debe tener al menos 32 caracteres: el backend rechaza una variable ausente, vacía o más corta (R17). Generá una propia y no la commitees, por ejemplo con `python -c "import secrets; print(secrets.token_hex(32))"`. Con Docker Compose exportala en la terminal antes de levantar el backend (`JWT_SECRET_KEY=<TU_SECRETO_DE_32+_CARACTERES>`); `docker compose up -d postgres` funciona aunque no esté definida. `MP_WEBHOOK_SECRET` sí es obligatoria para cualquier `docker compose` (no hay `.env` en la raíz, R20).
5. Levantar Postgres (servicio `postgres` con healthcheck `pg_isready`, ver [`docker-compose.yml`](docker-compose.yml)): `MP_WEBHOOK_SECRET=dev-secreto-local docker compose up -d --wait postgres` (host `5433` → contenedor `5432`; el backend usa `postgres:5432` dentro de la red Compose).
6. Migrar desde `backend/` (ver [`backend/alembic.ini`](backend/alembic.ini): `script_location = src/alembic`): `cd backend && alembic upgrade head`.
7. Tests backend desde `backend/` (ver [`backend/pytest.ini`](backend/pytest.ini): `testpaths = tests`, `pythonpath = src`): `cd backend && python -m pytest tests -q` (la suite completa necesita Postgres levantado; `JWT_SECRET_KEY` de test la define `backend/tests/conftest.py`).

### Cómo levantar (C-01)
1. Crear y activar un venv, e instalar dependencias (desde la raíz):
   `python -m venv .venv` → activar → `pip install -r backend/requirements.txt` (nunca commitear el `.env` real — R17).
2. Copiar `.env.example` a `.env`.
3. Levantar Postgres vía compose: `MP_WEBHOOK_SECRET=dev-secreto-local docker compose up -d --wait postgres` (host `5433` → contenedor `5432`; el backend usa `postgres:5432` dentro de la red Compose).
4. Aplicar migraciones desde `backend/`: `cd backend && alembic upgrade head`.
5. Levantar el backend (con `JWT_SECRET_KEY` y `MP_WEBHOOK_SECRET` exportadas, 32+ caracteres; sin ella el backend arranca pero falla con un error claro al usar la configuración): `docker compose up --build` (o local: `uvicorn app.main:app` con `PYTHONPATH=src` desde `backend/`) — `GET /api/health`; crear turno: `POST /api/turnos` (solape por profesional o sillón → `409`).
6. Tests backend desde `backend/`: `cd backend && python -m pytest tests -q`; E2E: `npm --prefix frontend/paciente run e2e` y `npm --prefix frontend/panel run e2e` (desde C-08 la carrera concurrente del mismo horario → un `201` y un `409` se prueba en el E2E del panel, que corre en CI; el viejo `e2e/` de C-01 se retiró). Tip local: si otro proceso escucha en `localhost:8000` por IPv6, apuntá el panel y los E2E a IPv4 con `VITE_BACKEND_URL=http://127.0.0.1:8000` y `E2E_API_URL=http://127.0.0.1:8000`.

### Seña y pagos (C-06)
Un turno reservado por la web nace `en_espera` (no bloquea la agenda) y pasa a `reservado` solo cuando se **acredita la seña** (30 % del precio base por defecto; un tratamiento de precio 0 nace `reservado`). El paciente paga con Mercado Pago o por transferencia; si la pre-reserva vence (30 min con Mercado Pago, 24 h con transferencia) un barrido la cancela.

- **Variables de entorno** (siempre del host, nunca en el repo: R17/R20; ver [`docker-compose.yml`](docker-compose.yml)): `APP_ENV` (`production` por defecto | `development` | `test` | `e2e`), `MP_GATEWAY` (`mercadopago` por defecto | `fake`), `MP_ACCESS_TOKEN` y `MP_WEBHOOK_SECRET` (obligatorias con `MP_GATEWAY=mercadopago`; el backend no arranca si faltan y nunca imprime sus valores). **Los defaults son los seguros:** sin variables el backend arranca como producción con Mercado Pago real. `MP_GATEWAY=fake` solo se acepta con `APP_ENV=test` o `APP_ENV=e2e`, y `docker-compose.yml` no trae ningún secreto de webhook por defecto: `MP_WEBHOOK_SECRET` es obligatoria (para levantar solo Postgres alcanza con exportar cualquier valor), `MP_API_BASE_URL`, `MP_WEBHOOK_TOLERANCIA_SEGUNDOS` (300), `PUBLIC_BASE_URL` (a dónde vuelve el paciente del checkout), `API_PUBLIC_BASE_URL` (base de la `notification_url` del webhook), `SENA_BARRIDO_HABILITADO` y `SENA_BARRIDO_SEGUNDOS` (60). Para desarrollo local sin credenciales: `APP_ENV=e2e MP_GATEWAY=fake MP_WEBHOOK_SECRET=<un-valor-sintetico>`.
- **Pasarela falsa (`MP_GATEWAY=fake`):** es la de tests, CI y E2E; no hace ninguna llamada de red. El checkout devuelve al paciente a `PUBLIC_BASE_URL/?pago=retorno&turno=ID` y el pago se "aprueba" enviando el webhook firmado con `data.id = fake-approved-<referencia_externa>@<monto>@ARS` (sin monto y moneda el pago queda `en_revision`, RN-SN-09). Los E2E firman con el secreto sintético del entorno (`E2E_MP_WEBHOOK_SECRET`, mismo valor que `MP_WEBHOOK_SECRET` del backend).
- **Configurar el webhook en Mercado Pago:** en el panel de desarrolladores, Webhooks, cargar `https://<API_PUBLIC_BASE_URL>/api/webhooks/mercadopago`, marcar el evento *Pagos* y copiar la *clave secreta* a `MP_WEBHOOK_SECRET`. El backend verifica la firma HMAC-SHA256 (`x-signature`, `x-request-id`, tolerancia de 300 s), consulta el pago a la API y es idempotente ante reintentos.
- **Acreditar una transferencia a mano** (recepción o admin; la UI llega con C-12): `POST /api/admin/pagos-sena/{id}/acreditar` con `Authorization: Bearer <token de /api/auth/login>`. El `{id}` es el `pago_id` que devuelve `POST /api/public/turnos/{id}/sena`. La configuración de porcentaje, medios, textos, plazos y datos bancarios se edita con `GET/PUT /api/admin/config/sena`.
- **Migración:** `cd backend && alembic upgrade head` aplica `006_sena_pagos` (el `downgrade` cancela los `en_espera` y borra el historial de señas).
- **E2E de la seña** (Playwright a 360px contra el backend real con la pasarela falsa): levantar el backend con `APP_ENV=e2e MP_GATEWAY=fake MP_WEBHOOK_SECRET=secreto-webhook-sintetico-e2e SENA_BARRIDO_SEGUNDOS=3` (el caso de vencimiento espera al barrido), `docker compose up -d --build backend`, y correr `cd frontend/paciente && npm run e2e`. Si el puerto 5433 del host está ocupado por otro servicio, definir `E2E_PGPORT` con el puerto en el que publicás Postgres.

---

### Gestión del turno por el paciente (C-07)
El paciente cancela o cambia el horario de su turno sin cuenta, solo con el código de gestión que recibió al reservar. Enlace: `/gestionar#<código>` (desde la confirmación, "Gestionar mi turno"); el código va en el fragmento de la URL, así que no llega a los logs del servidor.

- `GET /api/public/gestion`: datos del turno, límite para hacer cambios (inicio menos 24 h) y qué acciones están permitidas.
- `POST /api/public/gestion/cancelar`: cancela. Con seña acreditada se acepta con 24 h o más de anticipación (la seña queda `a_reembolsar`, devolución manual); una pre-reserva `en_espera` se cancela en cualquier momento, sin cobro.
- `POST /api/public/gestion/reprogramar` con `{ "inicio": "<fecha-hora con zona>" }`: mueve el turno (mismo tratamiento y profesional, con 24 h o más de anticipación) conservando id, código y seña. Si el horario está ocupado, 409 con alternativas.

Todas leen el código de la cabecera `X-Codigo-Gestion`; un código desconocido responde siempre el mismo 404. Menos de 24 h: 409 `fuera_de_plazo`.

### Panel de la clínica (C-08)
`frontend/panel/` es el panel interno (puerto 5174, mismo origen que `/api` gracias al proxy de Vite): pantalla de ingreso, agenda por día o semana con filtros, alta manual de turnos y las acciones de recepción sobre cada turno. Recepción y admin ven todas las agendas y operan; la odontóloga ve solo la suya, sin teléfonos, y desde C-11 solo puede marcar `atendido` sus propios turnos (ver más abajo).

- **Crear usuarios del panel** (comando idempotente; la contraseña va por entorno, nunca por argumento ni en el repo): `PANEL_USUARIO_PASSWORD='<contraseña de 12 a 128 caracteres>' docker compose run --rm -e PANEL_USUARIO_PASSWORD backend python -m app.panel.usuarios --email recepcion@clinica.test --nombre "Rita Recepción" --rol recepcion`. Un `odontologo` necesita además `--profesional-id <id>`. Repetirlo no duplica nada: actualiza nombre, contraseña y profesional, y suma el rol si faltaba.
- **Endpoints** (todos con `Authorization: Bearer <access>`): `GET /api/panel/agenda?vista=dia|semana&fecha=YYYY-MM-DD[&profesional_id][&sillon_id]`, `GET /api/panel/agenda/opciones`, `POST /api/panel/turnos` (alta manual, nace `reservado` y sin seña), `POST /api/panel/turnos/{id}/ausente`, `.../atendido` y `.../cancelar`. `atendido` se habilita desde las 00:00 del día local del turno; `ausente`, desde el inicio más `AUSENTE_TOLERANCIA_MINUTOS` (10 por defecto, RN-TU-12); cancelar respeta la ventana de 24 h (los `en_espera` se cancelan siempre). Un `atendido` sigue ocupando el horario hasta su `fin`. `POST /api/turnos` exige ahora recepción o admin.
- **Contrato de cookie de `/api/auth` (cambio incompatible):** el login y el refresh devuelven solo `access_token`; el refresh viaja en la cookie `refresh_token` (`HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth`, 7 días). `POST /api/auth/refresh` lee únicamente la cookie y exige la cabecera `X-Panel-Csrf: 1` (sin ella, 403 `csrf_requerido`). `POST /api/auth/logout` revoca la sesión (desde C-15, en el servidor: ver la sección siguiente). Si algún día el API se publica con CORS, hay que revisar esta defensa CSRF.
- **Migración:** `cd backend && alembic upgrade head` aplica `007_turno_origen_ocupacion` (columna `turno.origen` y EXCLUDE ampliados a `atendido`). Si ya hay turnos superpuestos con un `atendido`, aborta sin tocar datos y lista los ids: corregilos a mano y reintentá.
- **Desarrollo y pruebas:** `cd frontend/panel && npm install && npm run dev` (con el backend en `localhost:8000`); `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`. E2E (backend real con `APP_ENV=e2e MP_GATEWAY=fake` y la base local de Compose): `npm run e2e` (360 px y 1280 px).
- **Pendiente antes de producción:** UI de catálogo y disponibilidad (C-14); el endurecimiento de la auth (C-15) está descrito en la sección siguiente; ver `CHANGES.md`.

### Sesión del panel y límites de solicitudes (C-15)

- **Sesión en el servidor:** cada login crea una fila de `sesion_panel`; el `sid` viaja en el access y en el refresh. En **cada pedido** autenticado el servidor verifica que la sesión no esté revocada ni vencida, que el usuario esté activo y lee sus **roles de la base** (si se le quita un rol, rige en el siguiente pedido; el access emitido no decide permisos). Salir, desactivar o el máximo absoluto cortan el acceso en el siguiente pedido, en todas las pestañas. Un segundo logout con el mismo access responde 401 (la sesión ya está cerrada).
- **Migración:** `cd backend && alembic upgrade head` aplica `012_sesion_panel` (tabla `sesion_panel`) y **elimina `token_blacklist`**. Todos los tokens emitidos antes no tienen `sid`: **cada persona del panel tiene que ingresar una vez más** al desplegar (avisar al personal). Rollback: `alembic downgrade -1` y rotar `JWT_SECRET_KEY` para forzar un nuevo ingreso.
- **Variables** (por entorno, sin secretos; backend por Docker Compose): `SESION_MAXIMA_HORAS` (`12`, 1 a 168: duración absoluta de la sesión, sin importar cuántas veces se renueve; es un supuesto de negocio, ajustalo a la jornada de la clínica); `RATE_LIMIT_LOGIN_IP_EMAIL_MAX/_VENTANA_SEG` (`5` fallos / `900` s por IP + email), `RATE_LIMIT_LOGIN_IP_MAX/_VENTANA_SEG` (`30` / `900`), `RATE_LIMIT_LOGIN_EMAIL_MAX/_VENTANA_SEG` (`20` fallos / `3600`), `RATE_LIMIT_REFRESH_IP_MAX/_VENTANA_SEG` (`60` / `900`), `RATE_LIMIT_PUBLICO_ESCRITURA_MAX/_VENTANA_SEG` (`10` / `600`), `RATE_LIMIT_PUBLICO_LECTURA_MAX/_VENTANA_SEG` (`120` / `60`), `RATE_LIMIT_TIMEOUT_MS` (`200`); `TRUSTED_PROXIES` (vacío); `PURGA_SESIONES_HABILITADO` (`true`), `PURGA_SESIONES_INTERVALO_SEGUNDOS` (`3600`) y `PURGA_SESIONES_MARGEN_MINUTOS` (`60`) en el worker. Cualquier valor `0`, negativo o no numérico hace fallar el arranque nombrando la variable. **No hay interruptor para apagar los límites** (para los E2E se suben los umbrales de IP).
- **Redis ahora también lo usa la API** (contadores de los límites): el backend de Compose depende de Redis sano. Si Redis no responde, la API **deja pasar** los pedidos (sin límite) y avisa por log sin IP ni email, una vez por minuto.
- **IP real detrás de un proxy:** por defecto (`TRUSTED_PROXIES` vacío) se usa la IP del socket y se ignora `X-Forwarded-For`. En producción poné la IP (o CIDR) del proxy de confianza, separadas por comas, p. ej. `TRUSTED_PROXIES=10.0.0.5`; entonces se toma la última dirección no confiable de la cabecera. `0.0.0.0/0` y `::/0` se rechazan. Verificá en la auditoría que `LOGIN_OK` guarda la IP pública del equipo.
- **Desactivar y reactivar usuarios** (sin pedir contraseña): `docker compose run --rm backend python -m app.panel.usuarios --email dra.ficticia@clinica.test --desactivar` (queda inactivo, se revocan todas sus sesiones y se audita `SESIONES_REVOCADAS`) y `--reactivar` (no revive sesiones: tiene que ingresar de nuevo). El alta sobre un usuario desactivado **ya no lo reactiva** (avisa por stderr). `--desactivar` no se combina con `--rol`, `--nombre` ni `--reactivar`.
- **Qué ve la persona bloqueada:** al 429 el panel muestra «Demasiados intentos. Probá de nuevo en N minutos» y el sitio del paciente «Hiciste muchos pedidos seguidos. Probá de nuevo en N minutos» (N sale de `Retry-After`, mínimo 1).
- **Tests:** `cd backend && python -m pytest tests/test_settings_auth.py tests/test_sesion_*.py tests/test_auth_*.py tests/test_limit*.py tests/test_ip_cliente.py tests/test_purga_sesiones.py -q`. El de Redis real (`test_limitador_redis_integration.py`) necesita `REDIS_URL` (Compose publica Redis solo en `127.0.0.1:6379`; en CI el job `backend` levanta Redis y ese test no se salta).

### Ficha, odontograma, presupuestos y pagos de presupuesto (C-11)
Solo API por ahora (la UI es C-16). Todo bajo `/api/panel` con `Authorization: Bearer <access>`; datos de ejemplo 100 % sintéticos.

- **Acceso por rol:**

  | Ruta | Recepción / admin | Odontóloga con acceso completo | Odontóloga solo lectura (atención de hace más de 12 meses) | Odontóloga ajena |
  |---|---|---|---|---|
  | `POST /pacientes`, `GET /pacientes?dni=`, `PUT /pacientes/{id}`, `PUT /turnos/{id}/paciente` | sí | 403 | 403 | 403 |
  | `GET /pacientes/{id}` | completo | sin teléfono ni email | sin teléfono ni email | 403 `paciente_ajeno` |
  | `GET`/`PUT /pacientes/{id}/ficha` | lee y escribe | lee y escribe | lee; escribir da 403 `acceso_clinico_vencido` | 403 |
  | `GET /pacientes/{id}/odontograma[/historial]`, `POST …/odontograma` | lee y escribe | lee y escribe | lee; escribir da 403 `acceso_clinico_vencido` | 403 |
  | `GET /pacientes/{id}/presupuestos[/{pid}]` | completo | sin pagos ni saldo | sin pagos ni saldo | 403 |
  | `POST`/`PUT` de presupuestos, `…/presentar`, `…/aceptar`, `…/rechazar`, `…/anular` | sí | 403 | 403 | 403 |
  | `GET`/`POST …/presupuestos/{pid}/pagos`, `POST …/pagos/{id}/anular` | sí | 403 | 403 | 403 |
  | `POST /turnos/{id}/atendido` | cualquier turno | solo sus turnos (`turno_ajeno` si no) | ídem | ídem |

  "Sus pacientes" = al menos un turno `atendido` con su profesional. **Ventana de 12 meses (O16):** la odontóloga escribe ficha y odontograma solo si atendió al paciente en los últimos 365 días (constante `VENTANA_ACCESO_CLINICO`) o tiene con él un turno `reservado`/`confirmado` pendiente; si no, solo lee y la escritura responde 403 `acceso_clinico_vencido`. Un turno futuro sin una atención previa no da acceso.
- **Primera visita:** registrar o buscar al paciente por DNI → vincular el turno (`PUT /turnos/{id}/paciente`) → la odontóloga o recepción marca `atendido` al ingresar (desde las 00:00 del día del turno). Desde ahí la odontóloga accede a la ficha y al odontograma. Sin vínculo no hay acceso, aunque el turno se marque `atendido`.
- **Ejemplos** (`API=http://localhost:8000`, `TOKEN=<access de POST /api/auth/login>`):

  ```bash
  # Alta de paciente y búsqueda exacta por DNI
  curl -s -X POST $API/api/panel/pacientes -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"nombre":"Lucía","apellido":"Ejemplo","dni":"99000001","telefono":"+5491100000001"}'
  curl -s "$API/api/panel/pacientes?dni=99000001" -H "Authorization: Bearer $TOKEN"

  # Ficha: se edita enviando la versión leída (0 si todavía no existe); una versión vieja da 409 version_desactualizada
  curl -s -X PUT $API/api/panel/pacientes/1/ficha -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"alergias":"penicilina (dato sintético)","medicacion":"","antecedentes_medicos":"","observaciones":"","version":0}'

  # Odontograma: lote de 1 a 64 hallazgos, solo de alta
  curl -s -X POST $API/api/panel/pacientes/1/odontograma -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"registros":[{"pieza":16,"cara":"O","estado":"caries"},{"pieza":36,"estado":"ausente"}]}'

  # Presupuesto con cobertura de la obra social (los importes los calcula el servidor), presentar, aceptar y cobrar
  curl -s -X POST $API/api/panel/pacientes/1/presupuestos -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"lineas":[{"tratamiento_id":1,"cantidad":1}]}'
  curl -s -X POST $API/api/panel/pacientes/1/presupuestos/1/presentar -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
  curl -s -X POST $API/api/panel/pacientes/1/presupuestos/1/aceptar -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
  curl -s -X POST $API/api/panel/pacientes/1/presupuestos/1/pagos -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"medio":"transferencia","monto":"1500.00","referencia":"TRF-SINT-0001"}'
  ```
- **Reglas:** la cobertura es el porcentaje del nomenclador sobre el bruto (half-up a centavos por línea; `arancel_diferencial` es un copago por unidad a cargo del paciente, supuesto de O9); al presentar, el presupuesto queda congelado; los pagos solo se registran sobre presupuestos aceptados, nunca superan el total a cargo (409 `monto_excede_saldo`, con el saldo) y se anulan sin borrarlos; no hay facturación electrónica (RN-PG-03). Toda lectura y escritura de datos de salud queda auditada sin su contenido (RN-CL-03).
- **Migración:** `cd backend && alembic upgrade head` aplica `008_ficha_odonto_presup` (cinco tablas nuevas, sin tocar las existentes; el `downgrade` las borra).
- **Tests nuevos:** `cd backend && python -m pytest tests/test_clinica_*.py tests/test_pacientes_*.py tests/test_ficha_integration.py tests/test_odontograma_integration.py tests/test_presupuestos_integration.py tests/test_pagos_presupuesto_integration.py -q`; la matriz completa ruta × actor está en `tests/test_clinica_rbac_matriz.py`. E2E del marcado de `atendido` por la odontóloga: `cd frontend/panel && npm run e2e`.

### Caja, cierres, pendientes de la seña, indicadores y pacientes (C-12)
Todo bajo `/api/panel` con `Authorization: Bearer <access>`, solo para recepción y admin (la odontóloga recibe 403); anular un cierre es solo de admin. Importes como texto decimal (`"3000.00"`); el día es el calendario de la clínica (`APP_TZ`). Datos de ejemplo 100 % sintéticos.

- **Caja del día** (`GET /caja?dia=AAAA-MM-DD`, sin `dia` = hoy en la clínica): ingresos y egresos por concepto (`sena`, `pago_presupuesto`, `devolucion_sena`) y medio, `total_ingresos`, `total_egresos`, `total_neto`, `senas_retenidas`, el detalle del día y si el día está `abierto` o `cerrado`.

  ```bash
  curl -s "$API/api/panel/caja?dia=2026-11-17" -H "Authorization: Bearer $TOKEN"
  ```
- **Qué es ingreso y egreso:** una seña es ingreso el día en que la clínica recibió el dinero (`acreditado_en`), por el importe recibido, sin importar si después se canceló, faltó o se devolvió; un cobro de presupuesto `registrado` es ingreso por su `fecha_cobro` (uno `anulado` no cuenta); una devolución de seña registrada es egreso el día de la devolución. `pendiente`, `vencido`, `en_revision` y los pagos excedentes de Mercado Pago no entran en los totales. La seña de un ausente (`no_reembolsado`, R9) sigue siendo ingreso y se informa en `senas_retenidas`. La consulta queda auditada como `lectura_caja`.

- **Cierre de caja** (`POST /caja/cierres`, `GET /caja/cierres?desde=&hasta=`, `GET /caja/cierres/{id}`, `POST /caja/cierres/{id}/anular` solo admin): un cierre vigente por día terminado (desde las 00:15 del día siguiente, 409 `dia_no_terminado`); el cliente solo envía el día (y observaciones), los importes los calcula el servidor; el cierre no se edita ni se borra (405) y `GET …/{id}` informa `cuadra` y las diferencias. Con el día cerrado, registrar o anular un cobro de presupuesto con fecha de ese día responde 409 `caja_cerrada`.

  ```bash
  curl -s -X POST $API/api/panel/caja/cierres -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"     -d '{"dia":"2026-11-17","observaciones":"cierre de ejemplo"}'
  curl -s "$API/api/panel/caja/cierres?desde=2026-11-01&hasta=2026-11-30" -H "Authorization: Bearer $TOKEN"
  curl -s $API/api/panel/caja/cierres/1 -H "Authorization: Bearer $TOKEN"
  curl -s -X POST $API/api/panel/caja/cierres/1/anular -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json"     -d '{"motivo":"cobro cargado en el presupuesto equivocado"}'
  ```
- **Procedimiento "anular el cierre → corregir → volver a cerrar":** (1) un admin anula el cierre del día con motivo; (2) recepción anula o registra el cobro o la devolución con fecha de ese día; (3) recepción vuelve a cerrar el día y el nuevo cierre refleja la corrección (el anulado queda en el historial).
- **Liquidación** (`GET /caja/liquidacion?desde=&hasta=`, hasta 366 días): consolidado por medio de pago de los cierres vigentes (ingresos, egresos, neto y detalle por concepto) y los días del rango sin cierre vigente; sirve para conciliar con Mercado Pago y el banco. No calcula honorarios ni obras sociales.

  ```bash
  curl -s "$API/api/panel/caja/liquidacion?desde=2026-11-16&hasta=2026-11-17" -H "Authorization: Bearer $TOKEN"
  ```

- **Pendientes de la seña** (`GET /caja/pendientes`, `POST /caja/revisiones/{pago_id}/rechazar`, `POST /caja/devoluciones/senas/{pago_id}`, `POST /caja/devoluciones/excedentes/{id}`): lista del más antiguo al más nuevo con tipo `revision`, `sena` o `excedente_mp`. Aceptar una revisión sigue siendo `POST /api/admin/pagos-sena/{id}/acreditar`. El sistema no devuelve dinero: la devolución se hace por Mercado Pago o el banco y acá se registra con su referencia (3 a 64 caracteres) y una fecha opcional (no futura, no anterior a la recepción, en un día de caja abierto). El importe lo fija el sistema.

  | Qué hay que hacer con cada pago pendiente | Acción |
  |---|---|
  | `revision` (la pasarela informó otro importe) | Acreditar a mano o rechazar (queda a devolver; el turno no se cancela) |
  | `sena` (cancelación con 24 h, pago tardío o horario perdido) | Devolver por fuera y registrar la devolución con la referencia |
  | `excedente_mp` (pago de más o duplicado) | Devolver por Mercado Pago y registrar la devolución del excedente |
  | seña de un ausente (`no_reembolsado`) | Nada: se retiene (R9) |

  ```bash
  curl -s $API/api/panel/caja/pendientes -H "Authorization: Bearer $TOKEN"
  curl -s -X POST $API/api/panel/caja/revisiones/1/rechazar -H "Authorization: Bearer $TOKEN"
  curl -s -X POST $API/api/panel/caja/devoluciones/senas/1 -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"     -d '{"referencia":"DEV-SINT-0001"}'
  curl -s -X POST $API/api/panel/caja/devoluciones/excedentes/1 -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"     -d '{"referencia":"DEV-SINT-0002","fecha":"2026-11-19T10:00:00-03:00"}'
  ```

- **Deshacer un `atendido`** (`POST /turnos/{id}/deshacer-atendido`, solo recepción y admin; la odontóloga recibe 403 aun sobre sus turnos): vuelve a `reservado` hasta 7 días después del inicio (409 `plazo_vencido` con `limite_correccion`), con `motivo` del catálogo `turno_equivocado`, `paciente_no_asistio` u `otro`; la seña y el horario no cambian, queda auditado (origen `deshacer_atendido_panel`) y no se avisa a nadie. La agenda informa la acción `deshacer_atendido` solo donde corresponde.

  ```bash
  curl -s -X POST $API/api/panel/turnos/1/deshacer-atendido -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"     -d '{"motivo":"turno_equivocado"}'
  ```

- **Indicadores** (`GET /ocupacion?desde=&hasta=&sillon_id=`, hasta 31 días; `GET /ausentismo?desde=&hasta=`, hasta 366 días): la ocupación trae, por sillón y día, `minutos_ocupados`, `minutos_atencion`, `porcentaje` (vacío sin atención), `turnos` y `minutos_perdidos` (ausentes); una pre-reserva `en_espera` no ocupa nada (R8). El ausentismo trae atendidos, ausentes, `tasa`, `sin_marcar`, el desglose por profesional y el `recupero` (señas retenidas: cantidad, importe y porcentaje). Solo cantidades, minutos, importes y nombres de sillones y profesionales.

  ```bash
  curl -s "$API/api/panel/ocupacion?desde=2026-11-17&hasta=2026-11-23" -H "Authorization: Bearer $TOKEN"
  curl -s "$API/api/panel/ausentismo?desde=2026-11-01&hasta=2026-11-30" -H "Authorization: Bearer $TOKEN"
  ```

- **Listado de pacientes** (`GET /pacientes/listado`, solo recepción y admin): paginado (`pagina` desde 1, `por_pagina` de 1 a 50, 20 por defecto) y ordenado por apellido y nombre (o `orden=ausencias`, de más a menos). `q` (2 a 60 caracteres) busca en nombre y apellido sin distinguir mayúsculas ni acentos (extensión `unaccent`) y, si son dígitos, en el comienzo del DNI; los comodines se escapan y el texto buscado no se audita ni se loguea. Cada paciente trae `atendidos`, `ausentes` y `ultimo_turno` de sus turnos vinculados (`reservado`/`confirmado`/`atendido`/`ausente`; `en_espera`, `cancelado` y turnos sin vincular no cuentan); `con_ausencias=true` deja solo a quienes faltaron. La búsqueda exacta `GET /pacientes?dni=` no cambia.

  ```bash
  curl -s "$API/api/panel/pacientes/listado?q=lucia&con_ausencias=false&pagina=1" -H "Authorization: Bearer $TOKEN"
  ```
- **Migración:** `cd backend && alembic upgrade head` aplica `009_caja_cierres_devol` (tablas `cierre_caja` y `cierre_caja_linea` con triggers de inmutabilidad, estado `reembolsado` de la seña y extensión `unaccent`); el `downgrade` es completo pero **pierde los cierres y los datos de devolución** (los `reembolsado` vuelven a `a_reembolsar`): avisar antes de producción.
- **Tests nuevos:** `cd backend && python -m pytest tests/test_caja_*.py tests/test_cierre_caja_integration.py tests/test_devoluciones_*.py tests/test_panel_deshacer_integration.py tests/test_ocupacion_integration.py tests/test_ausentismo_integration.py tests/test_indicadores_calculo.py tests/test_pacientes_listado_integration.py -q`.

### Auditoría y exportación de datos (C-13)

- **Auditoría (`GET /api/panel/auditoria`, solo admin):** cada acción del panel deja un registro en la misma transacción (quién, qué, sobre qué entidad, cuándo y desde qué IP real, con los datos de antes y después). Es **de solo agregado**: la base rechaza `UPDATE` y `DELETE` (migración `013_auditoria_exportacion`) y un usuario con registros no se borra (se desactiva). Filtros por fechas (por defecto los últimos 7 días, máximo 366), usuario, tipo, entidad e id, paginados con «Ver más». También quedan auditadas las lecturas del listado de pacientes, la búsqueda por DNI y los datos de un paciente, el alta interna de turnos y el inicio de la conexión con Google. Nunca se guardan datos personales, clínicos ni secretos.
- **Cobertura verificada:** cada ruta autenticada declara su política (`app/plataforma/politica_auditoria.py`) y `tests/test_politica_auditoria_contrato.py` falla si se agrega una ruta sin política.
- **Exportación (`GET /api/panel/export?entidad=turnos|pacientes|cierres_caja&formato=csv`):** turnos y cierres de caja, recepción y admin; **pacientes, solo el admin**; la odontóloga no exporta. Filtros opcionales `desde` y `hasta` (por fecha de inicio del turno o día del cierre) e `incluir_inactivos` (pacientes). Se entrega por partes, sobre una foto consistente de los datos, y cada exportación queda auditada **antes** del primer byte (usuario, IP, entidad, filtros y cantidad de filas, nunca el contenido). Límites por usuario: una exportación en curso y `EXPORT_MAX_POR_HORA` (`20`) por hora; `EXPORT_TIMEOUT_SEGUNDOS` (`300`) acota cada exportación. Superado el límite responde 429 con `Retry-After`.
- **Columnas de cada CSV** (en este orden): **turnos** `id, inicio, fin, estado, origen, profesional_id, profesional, sillon_id, sillon, tratamiento_id, tratamiento, paciente_id, contacto_nombre, contacto_telefono`; **pacientes** `id, nombre, apellido, dni, telefono, email, obra_social, numero_afiliado, activo, creado_en`; **cierres_caja** `id, dia, estado, total_ingresos, total_egresos, total_neto, cerrado_por, cerrado_en, anulado_por, anulado_en, anulado_motivo, observaciones`. Nunca incluye el código de gestión, identificadores de la pasarela ni datos clínicos (ficha, odontograma, presupuestos).
- **Formato:** CSV RFC 4180 con comas, UTF-8 con BOM, fin de línea CRLF, decimales con punto y dos posiciones, instantes ISO-8601 con el desfase de la clínica (`-03:00`), fechas `AAAA-MM-DD`. Las celdas de texto libre que empiezan con `=`, `+`, `-`, `@`, tabulación o retorno de carro llevan un apóstrofo delante para que la planilla no las ejecute como fórmula.
- **Cómo abrirlo en Excel:** usá **Datos → Desde texto/CSV** (origen UTF-8) y marcá las columnas de teléfono y DNI como **texto**: si se abre con doble clic, Excel muestra los teléfonos `+549…` como número científico. La coma es el separador (no el punto y coma).
- **Aviso de datos personales (Ley 25.326):** el archivo de pacientes y turnos contiene nombres, DNI y teléfonos. Guardalo cifrado, no lo compartas por canales sin protección y borralo cuando termines. La pantalla lo recuerda.
- **Pantalla «Datos» del panel** (recepción y admin; la odontóloga no la ve): pestaña **Exportar** (entidad según el rol, rango opcional, descarga con la sesión vigente) y pestaña **Auditoría** (solo admin). Funciona a 360 px.
- **Retención:** la auditoría se conserva sin purga (supuesto abierto: el plazo legal se confirma con la clínica; referencia, la historia clínica a 10 años, Ley 26.529).
- **Tests nuevos:** `cd backend && python -m pytest tests/test_auditoria_*.py tests/test_plataforma_auditoria.py tests/test_politica_auditoria_contrato.py tests/test_tipos_auditoria.py tests/test_exportacion_*.py tests/test_pacientes_lecturas_auditadas_integration.py tests/test_turnos_alta_auditada_integration.py tests/test_usuarios_directorio_integration.py tests/test_settings_exportacion.py -q` (la prueba de 100 000 filas está marcada `slow`; `-m "not slow"` la omite). E2E: `cd frontend/panel && npx playwright test datos.spec.ts`.

### Recordatorios de WhatsApp, confirmación y worker (C-09)

- **Levantar redis y worker** (Docker Compose, con healthchecks; la API NO depende de Redis): `MP_WEBHOOK_SECRET=dev-secreto-local JWT_SECRET_KEY=<32+ caracteres> docker compose up -d --build --wait postgres redis worker backend` (antes, `cd backend && alembic upgrade head`: aplica `010_recordatorios`). El worker (`arq app.jobs.worker.WorkerSettings`) corre el trabajo de **recordatorios** y el **barrido de pre-reservas vencidas** (que antes corría dentro de la API). Sin Redis, para desarrollo: `SENA_BARRIDO_EN_API=true` hace que la API barra sola (los recordatorios sí necesitan el worker).
- **Variables nuevas** (sin secretos): `REDIS_URL` (`redis://redis:6379/0`), `REMINDER_LEAD_TIME` (48 h), `RECORDATORIOS_HABILITADO`, `RECORDATORIOS_INTERVALO_SEGUNDOS` (300), `WHATSAPP_PROVEEDOR` (`manual`), `CLINICA_NOMBRE`, `SENA_BARRIDO_EN_API` (`false`). Un intervalo que no divide la unidad (p. ej. 7 s) se redondea al divisor de 60 más cercano hacia abajo.
- **Operación para recepción** (sección **Recordatorios** del panel, solo recepción y admin): lista los turnos `reservado` que empiezan dentro de 48 h; **Abrir WhatsApp** abre el link `wa.me` con el mensaje armado (día y hora de la clínica, profesional, tratamiento y los enlaces de confirmar y gestionar) y marca el recordatorio como *Enviado* (queda quién y cuándo); **No se pudo enviar** lo deja *fallido* con motivo (número inválido, sin WhatsApp, otro). Un turno sin teléfono queda *fallido* (`sin_telefono`). Cancelar o reprogramar el turno quita el recordatorio de la lista.
- **Confirmación del paciente:** `/confirmar#<código>` muestra el turno y solo al tocar **Confirmar asistencia** envía `POST /api/public/gestion/confirmar` (cabecera `X-Codigo-Gestion`); no exige 24 h; una pre-reserva `en_espera` responde 409 `sena_pendiente`. `GET /api/public/gestion` suma `puede_confirmar` y `motivo_no_confirmable`.
- **E2E:** levantar `postgres redis backend worker` con `APP_ENV=e2e MP_GATEWAY=fake MP_WEBHOOK_SECRET=secreto-webhook-sintetico-e2e SENA_BARRIDO_SEGUNDOS=3 RECORDATORIOS_INTERVALO_SEGUNDOS=3` y correr `npm run e2e` en `frontend/paciente` y `frontend/panel` (los E2E de vencimiento de la seña ahora dependen del worker).
- **Rollback:** bajar `worker` y `redis`, `SENA_BARRIDO_EN_API=true` en la API y `alembic downgrade 009_caja_cierres_devol` (borra la tabla `recordatorio`; los turnos no se tocan).
- **Tests nuevos:** `cd backend && python -m pytest tests/test_recordatorios_*.py tests/test_jobs_*.py tests/test_settings_jobs.py tests/test_gestion_confirmacion_integration.py -q`.

### Google Calendar (C-10)

- **Migración:** `cd backend && alembic upgrade head` aplica `011_google_calendar` (tablas `gcal_conexion`, `evento_calendar` y `gcal_conflicto`). El `downgrade` las borra: se pierde el vínculo con Google (los eventos ya creados quedan en los calendarios; desconectar antes si se quieren dejar desvinculados).
- **Crear el cliente OAuth** en Google Cloud: habilitar la *Google Calendar API*, pantalla de consentimiento «Externa» en modo prueba y cargar como **usuarias de prueba** las cuentas de las profesionales (el permiso `calendar.events` es sensible: sin verificar la app Google muestra un aviso y limita a 100 usuarios), y crear un cliente OAuth de tipo **«Aplicación web»** con la URI de redirección `http://localhost:8000/api/panel/google-calendar/oauth/callback` (o la de tu despliegue = `GCAL_REDIRECT_URI`).
- **Variables** (siempre por entorno, nunca en el repo, R17/R20): `GCAL_CLIENT_ID`, `GCAL_CLIENT_SECRET`, `GCAL_TOKEN_CLAVE` (generala con `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`), `GCAL_REDIRECT_URI`, `PUBLIC_PANEL_URL`, y opcionales `GCAL_SYNC_HABILITADO` (`true`), `GCAL_SYNC_INTERVALO_SEGUNDOS` (`60`), `GCAL_HORIZONTE_DIAS` (`60`). Backend y worker las reciben por Docker Compose. Sin ellas todo sigue como antes: la API arranca, `POST /api/panel/google-calendar/conexion/iniciar` responde 503 `gcal_no_configurado` y el worker no registra `gcal_sync`.
- **Operación:** cada odontóloga entra a **Google Calendar** en el panel y toca *Conectar Google Calendar*. Los turnos `reservado`/`confirmado` de los próximos 60 días aparecen como eventos «Turno · <tratamiento>» **sin datos del paciente**; los eventos ocupados de su Google se traen como franjas ocupadas (solo horario) que la reserva pública no ofrece. Si mueve o borra un evento en Google, el turno NO cambia: queda un conflicto con el horario del sistema y el de Google para que recepción o admin elija *Restaurar en Google*, *Desvincular* o *Marcar como revisado*. La API nunca llama a Google (salvo el canje OAuth del regreso): sincroniza el worker cada `GCAL_SYNC_INTERVALO_SEGUNDOS`.
- **Rollback:** `GCAL_SYNC_HABILITADO=false` detiene la sincronía al instante; `alembic downgrade 010_recordatorios` borra las tablas.
- **Google falso para desarrollo y E2E** (perfil `e2e` de Compose, solo con `APP_ENV=e2e`): `docker compose --profile e2e up -d --build --wait postgres redis gcal-falso` y luego backend y worker con `GCAL_OAUTH_BASE_URL=http://localhost:8090 GCAL_TOKEN_BASE_URL=http://gcal-falso:8090 GCAL_API_BASE_URL=http://gcal-falso:8090 GCAL_SYNC_INTERVALO_SEGUNDOS=3` además de las credenciales sintéticas y `GCAL_TOKEN_CLAVE`. El E2E (`npm run e2e` en `frontend/panel` y `frontend/paciente`) simula lo que hace la profesional en Google con los endpoints `/_control/*` del falso.
- **Tests nuevos:** `cd backend && python -m pytest tests/test_gcal_*.py tests/test_settings_gcal.py -q`.

---

## 6. Metodología de Trabajo

El proyecto utiliza un enfoque **Spec-Driven Development** gobernado por **OpenSpec**:
1. **Discovery:** Identificación del problema, usuarios, reglas de negocio y benchmarking competitivo.
2. **Proposals y Specs:** Redacción formal de propuestas (`proposal.md`), especificaciones del comportamiento del sistema (`spec.md`), arquitectura técnica (`design.md`) y desglose de tareas (`tasks.md`).
3. **Apply e Implementación:** Implementación guiada por especificaciones validadas y pruebas de aceptación.
4. **Archive y Sync:** Sincronización del estado de las especificaciones y archivo de cambios completados.

---

## 7. Estado del Proyecto y Próximos Pasos

- [x] **Fase 1 — Discovery y Relevamiento:** Requerimientos, casos de uso, estudio de competidores y definición de reglas iniciales.
- [x] **KB — Base de conocimiento:** 12 archivos en `knowledge-base/` generados desde discovery (visión, modelo de datos, reglas, funcionalidades, arquitectura, decisiones y preguntas abiertas).
- [x] **Roadmap — Secuencia de implementación:** `CHANGES.md` con 16 changes atómicos (C-01..C-16), dependencias, gates de paralelismo y camino crítico.
- [x] **Skills — Capacidades de proyecto:** 6 skills en `.agents/skills/` (`vercel-react-best-practices`, `frontend-design`, `postgresql-table-design`, `playwright-cli`, `gws-calendar-agenda`, y la skill propia `spec-rules-auditor`) + `skills-lock.json` y `.atl/skill-registry.md`.
- [x] **Agents — Instrucciones para agentes:** `AGENTS.md` + copia `CLAUDE.md` (stack decidido, KB, skills por rol, integración MCP, roadmap C-01..C-16, reglas duras R1–R20). Es lo primero que lee todo agente al entrar al repo.
- [x] **Preguntas Alta resueltas (2026-09-30):** multi-odontólogo/multi-sillón día 1, WhatsApp manual v1 (`wa.me/`), entidad Tratamientos con duración, stack congelado (ver `knowledge-base/10_preguntas_abiertas.md`).
- [x] **C-01 — crear-turno-sin-solape (archivado 2026-10-01):** `POST /api/turnos` con anti-solape por profesional Y sillón (`EXCLUDE USING gist`, migración 001), `backend/src/` + `backend/tests/` + `docker-compose.yml` + spec en `openspec/specs/turnos/` + E2E de carrera (E2E 4.1 diferido, ver archive record).
- [x] **C-02 — core-models (archivado 2026-11-02):** resto de los modelos del dominio.
- [x] **C-03 — auth-panel-rbac (archivado 2026-11-02):** autenticación JWT y RBAC del panel.
- [x] **C-04 — catalogo-tratamientos-disponibilidad (archivado 2026-11-02):** catálogo administrable y cálculo de disponibilidad.
- [x] **C-05 — reserva-publica-horarios (archivado 2026-11-03):** reserva pública mobile-first sin registro obligatorio (`frontend/paciente/`).
- [x] **C-06 — sena-pagos-turno (archivado 2026-11-06):** seña y pagos (`en_espera` sin bloqueo de agenda; la seña acreditada bloquea).
- [x] **C-07 — cancelacion-reprogramacion-24h (archivado 2026-11-06):** cancelación y reprogramación con ventana de 24 hs.
- [x] **C-08 — agenda-profesional-panel (archivado 2026-11-10):** panel de recepción y profesionales (`frontend/panel/`).
- [x] **C-11 — ficha-odontograma-presupuestos-os (archivado 2026-11-10):** ficha del paciente, odontograma, presupuestos y pagos de presupuesto (solo API).
- [ ] **Pendientes (ver `CHANGES.md`):** C-09 (whatsapp-recordatorios-confirmacion), C-10 (google-calendar-sync), C-12 (panel-admin-caja-ausentismo), C-13 (auditoria-exportacion), C-14 (panel-catalogo-disponibilidad), C-15 (auth-hardening-panel, obligatorio antes de producción) y C-16 (panel-ficha-presupuestos-ui).

---

## 8. Video de Defensa del Proyecto

Estado del proyecto al momento de la grabación (fundación + C-01) presentado en video:

[![Video de defensa — turnos-odontologia](https://img.youtube.com/vi/1k6zfgvAfZs/0.jpg)](https://youtu.be/1k6zfgvAfZs)

Ver en YouTube: [https://youtu.be/1k6zfgvAfZs](https://youtu.be/1k6zfgvAfZs)

---

## 9. Integración de Herramientas del Agente (Skill Propia y Servidor MCP)

Como parte de la evolución metodológica del entorno de desarrollo (TP Metodología I), se incorporaron herramientas especializadas para potenciar el flujo **Spec-Driven Development (SDD)**:

### 9.1. Skill Propia: `spec-rules-auditor`
* **Ubicación:** [`.agents/skills/spec-rules-auditor/SKILL.md`](.agents/skills/spec-rules-auditor/SKILL.md)
* **Registro:** [`.atl/skill-registry.md`](.atl/skill-registry.md) y [`skills-lock.json`](skills-lock.json).
* **Propósito:** Audita sistemáticamente especificaciones, propuestas y diseños técnicos (`spec.md`, `proposal.md`, `design.md`) contra las reglas de negocio e invariantes documentadas en [`knowledge-base/05_reglas_de_negocio.md`](knowledge-base/05_reglas_de_negocio.md) y [`AGENTS.md`](AGENTS.md).
* **Entregable clave:** Genera la **Terna Canónica de Escenarios Verificables** (Comportamiento Esperado, Error de Negocio y Caso de Borde) en formato BDD/Gherkin y emite un dictamen formal con matriz de trazabilidad.

### 9.2. Servidor MCP: Google Stitch (`@_davideast/stitch-mcp`)
* **Propósito:** Conectar al agente con la plataforma de diseño visual Google Stitch (Google Labs) para explorar proyectos, generar pantallas mobile-first, obtener su HTML y capturas y los tokens de diseño para los documentos `design.md` (garantizando la regla **R3** de diseño funcional a 360px).
* **Estado de uso:** Stitch se conectó y se usó de verdad por primera vez el 2026-11-03 (tres pantallas generadas con `generate_screen_from_text`; evidencia en [`docs/skills-mcp/evidencia-stitch/`](docs/skills-mcp/evidencia-stitch/README.md)). Antes de esa fecha el repositorio solo conserva un `--help` de la herramienta, que no produce diseños; ver la corrección en [`docs/skills-mcp/aplicacion.md`](docs/skills-mcp/aplicacion.md).
* **Configuración reproducible en el cliente MCP (Windows).** El paquete `stitch-mcp@0.9.0` en modo `proxy` solo le pasa `STITCH_API_KEY` al proxy: la autenticación OAuth no funciona directamente con esa configuración. Se resolvió con un script de arranque local, **fuera del repo**, que exporta un `STITCH_ACCESS_TOKEN` de vida corta antes de lanzar el servidor. El token dura alrededor de una hora; para renovarlo hay que reiniciar el cliente. Estructura (solo placeholders, nunca credenciales en el repo):
  ```json
  {
    "mcpServers": {
      "stitch": {
        "command": "<RUTA_AL_SCRIPT_LOCAL_DE_ARRANQUE_FUERA_DEL_REPO>",
        "args": [],
        "env": {
          "GOOGLE_CLOUD_PROJECT": "<TU_GOOGLE_CLOUD_PROJECT_ID>"
        }
      }
    }
  }
  ```
  El script solo debe exportar `STITCH_ACCESS_TOKEN` (sin escribirlo en un archivo versionado) y luego lanzar `npx.cmd -y @_davideast/stitch-mcp proxy`. El proxy sí acepta `STITCH_API_KEY=<TU_API_KEY>` en `env`; esa vía no se probó en este proyecto.
* **Pasos previos de configuración:**
  1. Un proyecto de Google Cloud propio: `npx.cmd -y @_davideast/stitch-mcp init` lo necesita.
  2. Habilitar la API de Stitch en ese proyecto: `gcloud services enable stitch.googleapis.com --project <TU_GOOGLE_CLOUD_PROJECT_ID>`. Sin este paso, las llamadas de generación devuelven `403`.
* **Comprobación de conexión y ejecución de herramientas:**
  * `npx.cmd -y @_davideast/stitch-mcp --help` y `npx.cmd -y @_davideast/stitch-mcp tool --help` solo prueban que el paquete corre. **Listar las herramientas del servidor también funciona con la API deshabilitada, así que no prueba que la API sea utilizable.**
  * La prueba real es generar una pantalla: invocar `generate_screen_from_text` (con `projectId`, `prompt` y `deviceType`) y recuperar el resultado con `get_screen` y `download_file`. Otras herramientas disponibles: `list_screens`, `list_projects`, `create_project`, `generate_variants`, `edit_screens`, `list_design_systems`.
* **Resolución de problemas comunes detectados:**
  * *Error de política de ejecución en Windows (`PSSecurityException / UnauthorizedAccess`):* Node instala wrappers `.ps1` que Windows bloquea por defecto. Solución: invocar explícitamente `npx.cmd` en lugar de `npx`.
  * *`403` al generar pantallas:* la API de Stitch no está habilitada en el proyecto de Google Cloud (ver paso 2).
  * *`Authentication failed. Provide either apiKey OR accessToken + projectId` o `401` tras un rato de uso:* el modo `proxy` no usa OAuth por sí solo; hace falta `STITCH_API_KEY` o el script con `STITCH_ACCESS_TOKEN`, y el token vence en aproximadamente una hora (reiniciar el cliente para renovarlo).
* **Privacidad y Seguridad (Ley 25.326 y R19):**
  * El servidor MCP opera exclusivamente en la capa de presentación y prototipado visual. No accede a bases de datos ni manipula datos de pacientes; todos los prototipos usan información 100% sintética.
