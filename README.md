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
├── AGENTS.md                       # Instrucciones para agentes (stack, KB, skills, roadmap, reglas R1–R19)
├── CLAUDE.md                       # Copia de AGENTS.md (no editar a mano sin re-sincronizar)
├── .agents/skills/                 # Skills de proyecto instaladas (5): vercel-react-best-practices,
│                                   # frontend-design, postgresql-table-design, playwright-cli, gws-calendar-agenda
├── .atl/skill-registry.md          # Registro de skills (trackeado vía excepción en .gitignore; resto de .atl/ ignorado)
├── .gitignore                      # Configuración de exclusiones de Git (incluye .atl/)
├── .opencode/                      # Comandos y habilidades para flujo guiado por agentes IA
│   ├── commands/                   # Comandos /opsx-* para el ciclo spec-driven
│   └── skills/                     # Habilidades integradas de OpenSpec
├── CHANGES.md                      # Índice canónico de changes C-01..C-13 (roadmap, dependencias y gates)
├── backend/                        # Código backend: FastAPI + SQLAlchemy + Alembic + tests
│   ├── src/
│   │   ├── app/                    # `main`, `shared/`, `turnos/` (models, schemas, router, service)
│   │   └── alembic/                # Entorno + migraciones (001 agenda con EXCLUDE)
│   ├── tests/                      # Suite pytest (conftest + 3 archivos; `pythonpath = src`)
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
├── e2e/                            # Playwright: playwright.config.js + tests/race.spec.js (node_modules/ ignorado)
├── knowledge-base/                 # Base de conocimiento (12 archivos: 01..11 + README)
├── openspec/
│   ├── config.yaml                 # Configuración del workflow de especificaciones
│   ├── changes/                    # Cambios propuestos y archivados (C-01 archivado 2026-10-01)
│   └── specs/turnos/               # Specs vigentes (creacion-sin-solape)
├── skills-lock.json                # Lockfile de versions de las skills instaladas
└── README.md                       # Documentación general del repositorio
```

### Base de conocimiento, roadmap y skills
- **Base de conocimiento:** ver [knowledge-base/README.md](knowledge-base/README.md) — visión, actores, modelo de datos (13 entidades), 17 reglas de negocio, funcionalidades US-001..US-012, flujos, arquitectura propuesta, decisiones y preguntas abiertas.
- **Roadmap de implementación:** ver [CHANGES.md](CHANGES.md) — secuencia atómica C-01 (crear-turno-sin-solape, `[x]` archivado 2026-10-01) → C-13 (auditoría), con árbol de dependencias, gates de paralelismo y camino crítico. Leer antes de ejecutar cualquier `/opsx:propose`.
- **Skills de proyecto:** `.agents/skills/` + [skills-lock.json](skills-lock.json), registradas en [.atl/skill-registry.md](.atl/skill-registry.md). Cobertura: booking mobile-first, panel/agenda, modelos Postgres anti-solape, E2E con Playwright y sync con Google Calendar.

### Inicio rápido paso a paso (verificado contra los archivos reales)
1. Clonar: `git clone <url-del-repo> && cd turnos-odontologia`.
2. Crear y activar venv: `python -m venv .venv` → en Windows `cmd /c .venv\Scripts\activate` (nunca commitear el `.env` real — R17).
3. Instalar (ver [`backend/requirements.txt`](backend/requirements.txt)): `pip install -r backend/requirements.txt`.
4. Configurar entorno (ver [`.env.example`](.env.example)): copiar a `.env` (`DATABASE_URL=postgresql+asyncpg://turnos:turnos@localhost:5433/turnos`). **`JWT_SECRET_KEY` es obligatoria** y debe tener al menos 32 caracteres: el backend rechaza una variable ausente, vacía o más corta (R17). Generá una propia y no la commitees, por ejemplo con `python -c "import secrets; print(secrets.token_hex(32))"`. Con Docker Compose exportala en la terminal antes de levantar el backend (`JWT_SECRET_KEY=<TU_SECRETO_DE_32+_CARACTERES>`); `docker compose up -d postgres` funciona aunque no esté definida.
5. Levantar Postgres (servicio `postgres` con healthcheck `pg_isready`, ver [`docker-compose.yml`](docker-compose.yml)): `docker compose up -d postgres` (host `5433` → contenedor `5432`; el backend usa `postgres:5432` dentro de la red Compose).
6. Migrar desde `backend/` (ver [`backend/alembic.ini`](backend/alembic.ini): `script_location = src/alembic`): `cd backend && alembic upgrade head`.
7. Tests backend desde `backend/` (ver [`backend/pytest.ini`](backend/pytest.ini): `testpaths = tests`, `pythonpath = src`): `cd backend && python -m pytest tests -q` (la suite completa necesita Postgres levantado; `JWT_SECRET_KEY` de test la define `backend/tests/conftest.py`).

### Cómo levantar (C-01)
1. Crear y activar un venv, e instalar dependencias (desde la raíz):
   `python -m venv .venv` → activar → `pip install -r backend/requirements.txt` (nunca commitear el `.env` real — R17).
2. Copiar `.env.example` a `.env`.
3. Levantar Postgres vía compose: `docker compose up -d postgres` (host `5433` → contenedor `5432`; el backend usa `postgres:5432` dentro de la red Compose).
4. Aplicar migraciones desde `backend/`: `cd backend && alembic upgrade head`.
5. Levantar el backend (con `JWT_SECRET_KEY` exportada, 32+ caracteres; sin ella el backend arranca pero falla con un error claro al usar la configuración): `docker compose up --build` (o local: `uvicorn app.main:app` con `PYTHONPATH=src` desde `backend/`) — `GET /api/health`; crear turno: `POST /api/turnos` (solape por profesional o sillón → `409`).
6. Tests backend desde `backend/`: `cd backend && python -m pytest tests -q`; E2E: `npm --prefix e2e install && npm --prefix e2e test` (carrera concurrente mismo slot → un `201` y un `409`).

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
- [x] **Roadmap — Secuencia de implementación:** `CHANGES.md` con 13 changes atómicos (C-01..C-13), dependencias, gates de paralelismo y camino crítico.
- [x] **Skills — Capacidades de proyecto:** 6 skills en `.agents/skills/` (`vercel-react-best-practices`, `frontend-design`, `postgresql-table-design`, `playwright-cli`, `gws-calendar-agenda`, y la skill propia `spec-rules-auditor`) + `skills-lock.json` y `.atl/skill-registry.md`.
- [x] **Agents — Instrucciones para agentes:** `AGENTS.md` + copia `CLAUDE.md` (stack decidido, KB, skills por rol, integración MCP, roadmap C-01..C-13, reglas duras R1–R19). Es lo primero que lee todo agente al entrar al repo.
- [x] **Preguntas Alta resueltas (2026-09-30):** multi-odontólogo/multi-sillón día 1, WhatsApp manual v1 (`wa.me/`), entidad Tratamientos con duración, stack congelado (ver `knowledge-base/10_preguntas_abiertas.md`).
- [x] **C-01 — crear-turno-sin-solape (archivado 2026-10-01):** `POST /api/turnos` con anti-solape por profesional Y sillón (`EXCLUDE USING gist`, migración 001), `backend/src/` + `backend/tests/` + `docker-compose.yml` + spec en `openspec/specs/turnos/` + E2E de carrera (E2E 4.1 diferido, ver archive record).
- [ ] **Fase 2 — Arquitectura y resto del core (C-02..C-03):** Stack decidido — Backend Python + FastAPI + SQLAlchemy (+Alembic) + PostgreSQL + Redis + JWT + Docker Compose; Frontend React + TypeScript + Vite; E2E Playwright (ver `AGENTS.md`). Siguiente: resto de modelos (C-02) y auth/RBAC del panel (C-03).
- [ ] **Fase 3 — Diseño UX/UI (C-04..C-05):** Catálogo/tratamientos, disponibilidad y reserva pública mobile-first sin registro obligatorio.
- [ ] **Fase 4 — Implementación del MVP (C-06..C-08, C-11):** Seña/pagos (GAP `en_espera` sin bloqueo), cancelación/reprogramación 24 hs, agenda profesional y ficha/odontograma.
- [ ] **Fase 5 — Integraciones y admin (C-09..C-10, C-12..C-13):** WhatsApp, Google Calendar sync, caja/ausentismo y auditoría/exportación.

---

## 8. Video de Defensa del Proyecto

Estado actual del proyecto (fundación + C-01) presentado en video:

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
