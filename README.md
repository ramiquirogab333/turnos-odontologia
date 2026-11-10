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
│   │   └── alembic/                # Entorno + migraciones (001..008: agenda con EXCLUDE, modelos, auth, catálogo, reserva pública, seña/pagos, origen/ocupación del turno y ficha/odontograma/presupuestos)
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
├── frontend-paciente/              # Reserva pública y gestión del turno por el paciente (React + Vite, puerto 5173)
├── frontend-panel/                 # Panel interno de la clínica (C-08): ingreso, agenda, alta manual y acciones (React + Vite, puerto 5174)
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
6. Tests backend desde `backend/`: `cd backend && python -m pytest tests -q`; E2E: `npm --prefix frontend-paciente run e2e` y `npm --prefix frontend-panel run e2e` (desde C-08 la carrera concurrente del mismo horario → un `201` y un `409` se prueba en el E2E del panel, que corre en CI; el viejo `e2e/` de C-01 se retiró). Tip local: si otro proceso escucha en `localhost:8000` por IPv6, apuntá el panel y los E2E a IPv4 con `VITE_BACKEND_URL=http://127.0.0.1:8000` y `E2E_API_URL=http://127.0.0.1:8000`.

### Seña y pagos (C-06)
Un turno reservado por la web nace `en_espera` (no bloquea la agenda) y pasa a `reservado` solo cuando se **acredita la seña** (30 % del precio base por defecto; un tratamiento de precio 0 nace `reservado`). El paciente paga con Mercado Pago o por transferencia; si la pre-reserva vence (30 min con Mercado Pago, 24 h con transferencia) un barrido la cancela.

- **Variables de entorno** (siempre del host, nunca en el repo: R17/R20; ver [`docker-compose.yml`](docker-compose.yml)): `APP_ENV` (`production` por defecto | `development` | `test` | `e2e`), `MP_GATEWAY` (`mercadopago` por defecto | `fake`), `MP_ACCESS_TOKEN` y `MP_WEBHOOK_SECRET` (obligatorias con `MP_GATEWAY=mercadopago`; el backend no arranca si faltan y nunca imprime sus valores). **Los defaults son los seguros:** sin variables el backend arranca como producción con Mercado Pago real. `MP_GATEWAY=fake` solo se acepta con `APP_ENV=test` o `APP_ENV=e2e`, y `docker-compose.yml` no trae ningún secreto de webhook por defecto: `MP_WEBHOOK_SECRET` es obligatoria (para levantar solo Postgres alcanza con exportar cualquier valor), `MP_API_BASE_URL`, `MP_WEBHOOK_TOLERANCIA_SEGUNDOS` (300), `PUBLIC_BASE_URL` (a dónde vuelve el paciente del checkout), `API_PUBLIC_BASE_URL` (base de la `notification_url` del webhook), `SENA_BARRIDO_HABILITADO` y `SENA_BARRIDO_SEGUNDOS` (60). Para desarrollo local sin credenciales: `APP_ENV=e2e MP_GATEWAY=fake MP_WEBHOOK_SECRET=<un-valor-sintetico>`.
- **Pasarela falsa (`MP_GATEWAY=fake`):** es la de tests, CI y E2E; no hace ninguna llamada de red. El checkout devuelve al paciente a `PUBLIC_BASE_URL/?pago=retorno&turno=ID` y el pago se "aprueba" enviando el webhook firmado con `data.id = fake-approved-<referencia_externa>@<monto>@ARS` (sin monto y moneda el pago queda `en_revision`, RN-SN-09). Los E2E firman con el secreto sintético del entorno (`E2E_MP_WEBHOOK_SECRET`, mismo valor que `MP_WEBHOOK_SECRET` del backend).
- **Configurar el webhook en Mercado Pago:** en el panel de desarrolladores, Webhooks, cargar `https://<API_PUBLIC_BASE_URL>/api/webhooks/mercadopago`, marcar el evento *Pagos* y copiar la *clave secreta* a `MP_WEBHOOK_SECRET`. El backend verifica la firma HMAC-SHA256 (`x-signature`, `x-request-id`, tolerancia de 300 s), consulta el pago a la API y es idempotente ante reintentos.
- **Acreditar una transferencia a mano** (recepción o admin; la UI llega con C-12): `POST /api/admin/pagos-sena/{id}/acreditar` con `Authorization: Bearer <token de /api/auth/login>`. El `{id}` es el `pago_id` que devuelve `POST /api/public/turnos/{id}/sena`. La configuración de porcentaje, medios, textos, plazos y datos bancarios se edita con `GET/PUT /api/admin/config/sena`.
- **Migración:** `cd backend && alembic upgrade head` aplica `006_sena_pagos` (el `downgrade` cancela los `en_espera` y borra el historial de señas).
- **E2E de la seña** (Playwright a 360px contra el backend real con la pasarela falsa): levantar el backend con `APP_ENV=e2e MP_GATEWAY=fake MP_WEBHOOK_SECRET=secreto-webhook-sintetico-e2e SENA_BARRIDO_SEGUNDOS=3` (el caso de vencimiento espera al barrido), `docker compose up -d --build backend`, y correr `cd frontend-paciente && npm run e2e`. Si el puerto 5433 del host está ocupado por otro servicio, definir `E2E_PGPORT` con el puerto en el que publicás Postgres.

---

### Gestión del turno por el paciente (C-07)
El paciente cancela o cambia el horario de su turno sin cuenta, solo con el código de gestión que recibió al reservar. Enlace: `/gestionar#<código>` (desde la confirmación, "Gestionar mi turno"); el código va en el fragmento de la URL, así que no llega a los logs del servidor.

- `GET /api/public/gestion`: datos del turno, límite para hacer cambios (inicio menos 24 h) y qué acciones están permitidas.
- `POST /api/public/gestion/cancelar`: cancela. Con seña acreditada se acepta con 24 h o más de anticipación (la seña queda `a_reembolsar`, devolución manual); una pre-reserva `en_espera` se cancela en cualquier momento, sin cobro.
- `POST /api/public/gestion/reprogramar` con `{ "inicio": "<fecha-hora con zona>" }`: mueve el turno (mismo tratamiento y profesional, con 24 h o más de anticipación) conservando id, código y seña. Si el horario está ocupado, 409 con alternativas.

Todas leen el código de la cabecera `X-Codigo-Gestion`; un código desconocido responde siempre el mismo 404. Menos de 24 h: 409 `fuera_de_plazo`.

### Panel de la clínica (C-08)
`frontend-panel/` es el panel interno (puerto 5174, mismo origen que `/api` gracias al proxy de Vite): pantalla de ingreso, agenda por día o semana con filtros, alta manual de turnos y las acciones de recepción sobre cada turno. Recepción y admin ven todas las agendas y operan; la odontóloga ve solo la suya, sin teléfonos, y desde C-11 solo puede marcar `atendido` sus propios turnos (ver más abajo).

- **Crear usuarios del panel** (comando idempotente; la contraseña va por entorno, nunca por argumento ni en el repo): `PANEL_USUARIO_PASSWORD='<contraseña de 12 a 128 caracteres>' docker compose run --rm -e PANEL_USUARIO_PASSWORD backend python -m app.panel.usuarios --email recepcion@clinica.test --nombre "Rita Recepción" --rol recepcion`. Un `odontologo` necesita además `--profesional-id <id>`. Repetirlo no duplica nada: actualiza nombre, contraseña y profesional, y suma el rol si faltaba.
- **Endpoints** (todos con `Authorization: Bearer <access>`): `GET /api/panel/agenda?vista=dia|semana&fecha=YYYY-MM-DD[&profesional_id][&sillon_id]`, `GET /api/panel/agenda/opciones`, `POST /api/panel/turnos` (alta manual, nace `reservado` y sin seña), `POST /api/panel/turnos/{id}/ausente`, `.../atendido` y `.../cancelar`. `atendido` se habilita desde las 00:00 del día local del turno; `ausente`, desde el inicio más `AUSENTE_TOLERANCIA_MINUTOS` (10 por defecto, RN-TU-12); cancelar respeta la ventana de 24 h (los `en_espera` se cancelan siempre). Un `atendido` sigue ocupando el horario hasta su `fin`. `POST /api/turnos` exige ahora recepción o admin.
- **Contrato de cookie de `/api/auth` (cambio incompatible):** el login y el refresh devuelven solo `access_token`; el refresh viaja en la cookie `refresh_token` (`HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth`, 7 días). `POST /api/auth/refresh` lee únicamente la cookie y exige la cabecera `X-Panel-Csrf: 1` (sin ella, 403 `csrf_requerido`). `POST /api/auth/logout` revoca el access y el refresh de la cookie por 7 días. Si algún día el API se publica con CORS, hay que revisar esta defensa CSRF.
- **Migración:** `cd backend && alembic upgrade head` aplica `007_turno_origen_ocupacion` (columna `turno.origen` y EXCLUDE ampliados a `atendido`). Si ya hay turnos superpuestos con un `atendido`, aborta sin tocar datos y lista los ids: corregilos a mano y reintentá.
- **Desarrollo y pruebas:** `cd frontend-panel && npm install && npm run dev` (con el backend en `localhost:8000`); `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`. E2E (backend real con `APP_ENV=e2e MP_GATEWAY=fake` y la base local de Compose): `npm run e2e` (360 px y 1280 px).
- **Pendiente antes de producción:** endurecimiento restante de la auth (C-15) y UI de catálogo y disponibilidad (C-14); ver `CHANGES.md`.

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
- **Tests nuevos:** `cd backend && python -m pytest tests/test_clinica_*.py tests/test_pacientes_*.py tests/test_ficha_integration.py tests/test_odontograma_integration.py tests/test_presupuestos_integration.py tests/test_pagos_presupuesto_integration.py -q`; la matriz completa ruta × actor está en `tests/test_clinica_rbac_matriz.py`. E2E del marcado de `atendido` por la odontóloga: `cd frontend-panel && npm run e2e`.

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
- [x] **C-05 — reserva-publica-horarios (archivado 2026-11-03):** reserva pública mobile-first sin registro obligatorio (`frontend-paciente/`).
- [x] **C-06 — sena-pagos-turno (archivado 2026-11-06):** seña y pagos (`en_espera` sin bloqueo de agenda; la seña acreditada bloquea).
- [x] **C-07 — cancelacion-reprogramacion-24h (archivado 2026-11-06):** cancelación y reprogramación con ventana de 24 hs.
- [x] **C-08 — agenda-profesional-panel (archivado 2026-11-10):** panel de recepción y profesionales (`frontend-panel/`).
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
