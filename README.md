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
- Documento Markdown: [docs/discovery/discovery.md](docs/discovery/discovery.md)
- Documento PDF: [docs/discovery/discovery.pdf](docs/discovery/discovery.pdf)
- Reporte de Validación: [docs/discovery/Validación Discovery.md](docs/discovery/Validaci%C3%B3n%20Discovery.md)

---

## 5. Estructura del Repositorio

```text
turnos-odontologia/
├── .active-orchestrator-state.json # Estado estructurado del proceso (fase actual: done)
├── AGENTS.md                       # Instrucciones para agentes (stack, KB, skills, roadmap, reglas R1–R18)
├── CLAUDE.md                       # Copia de AGENTS.md (no editar a mano sin re-sincronizar)
├── .agents/skills/                 # Skills de proyecto instaladas (5): vercel-react-best-practices,
│                                   # frontend-design, postgresql-table-design, playwright-cli, gws-calendar-agenda
├── .atl/skill-registry.md          # Registro de skills (versionado con `git add -f`; resto de .atl/ ignorado)
├── .gitignore                      # Configuración de exclusiones de Git (incluye .atl/)
├── .opencode/                      # Comandos y habilidades para flujo guiado por agentes IA
│   ├── commands/                   # Comandos /opsx-* para el ciclo spec-driven
│   └── skills/                     # Habilidades integradas de OpenSpec
├── CHANGES.md                      # Índice canónico de changes C-01..C-13 (roadmap, dependencias y gates)
├── backend/                        # C-01 vertical slice: FastAPI + SQLAlchemy + Alembic (app/, tests/, Dockerfile)
├── discovery/                      # Prompt de estudio de mercado (raíz; distinto de docs/discovery/)
├── docker-compose.yml              # postgres:16 + backend con healthcheck (host 5433→5432)
├── .env.example                    # Plantilla de env (copiar a .env; nunca commitear .env)
├── docs/
│   └── discovery/
│       ├── discovery.md            # Informe detallado de relevamiento de requerimientos y competidores
│       ├── discovery.pdf           # Versión compilada en PDF del estudio de mercado
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

### Cómo levantar (C-01)
1. Copiar `.env.example` a `.env` (nunca commitear el `.env` real — R17).
2. `docker compose up --build` — levanta `postgres` (host `5433`) y `backend` (`:8000`).
3. Backend: `GET /api/health`; crear turno: `POST /api/turnos` (solape por profesional o sillón → `409`).
4. Tests backend: `pytest` en `backend/`; E2E: `npm --prefix e2e install && npm --prefix e2e test` (carrera concurrente mismo slot → un `201` y un `409`).

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
- [x] **Skills — Capacidades de proyecto:** 5 skills instaladas en `.agents/skills/` (`vercel-react-best-practices`, `frontend-design`, `postgresql-table-design`, `playwright-cli`, `gws-calendar-agenda`) + `skills-lock.json` y `.atl/skill-registry.md`.
- [x] **Agents — Instrucciones para agentes:** `AGENTS.md` + copia `CLAUDE.md` (stack decidido, KB, skills por rol, roadmap C-01..C-13, reglas duras R1–R18). Es lo primero que lee todo agente al entrar al repo.
- [x] **Preguntas Alta resueltas (2026-09-30):** multi-odontólogo/multi-sillón día 1, WhatsApp manual v1 (`wa.me/`), entidad Tratamientos con duración, stack congelado (ver `knowledge-base/10_preguntas_abiertas.md`).
- [x] **C-01 — crear-turno-sin-solape (archivado 2026-10-01):** `POST /api/turnos` con anti-solape por profesional Y sillón (`EXCLUDE USING gist`, migración 001), `backend/` + `docker-compose.yml` + spec en `openspec/specs/turnos/` + E2E de carrera (E2E 4.1 diferido, ver archive record).
- [ ] **Fase 2 — Arquitectura y resto del core (C-02..C-03):** Stack decidido — Backend Python + FastAPI + SQLAlchemy (+Alembic) + PostgreSQL + Redis + JWT + Docker Compose; Frontend React + TypeScript + Vite; E2E Playwright (ver `AGENTS.md`). Siguiente: resto de modelos (C-02) y auth/RBAC del panel (C-03).
- [ ] **Fase 3 — Diseño UX/UI (C-04..C-05):** Catálogo/tratamientos, disponibilidad y reserva pública mobile-first sin registro obligatorio.
- [ ] **Fase 4 — Implementación del MVP (C-06..C-08, C-11):** Seña/pagos (GAP `en_espera` sin bloqueo), cancelación/reprogramación 24 hs, agenda profesional y ficha/odontograma.
- [ ] **Fase 5 — Integraciones y admin (C-09..C-10, C-12..C-13):** WhatsApp, Google Calendar sync, caja/ausentismo y auditoría/exportación.
