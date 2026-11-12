# turnos-odontologia — Instrucciones para Agentes

> Este archivo (y su copia `CLAUDE.md`) es lo PRIMERO que todo agente lee al entrar al repo.
> Generado a partir de `knowledge-base/` y `CHANGES.md`. No editar a mano sin re-sincronizar ambos archivos.

---

## Stack Tecnológico

Stack decidido en la fase de fundación (cierra la pregunta abierta nº1 de la KB):

| Capa | Tecnología | Versión |
|------|------------|---------|
| Backend | Python + FastAPI + SQLAlchemy (+ Alembic) | fijar en C-01 |
| Base de datos | PostgreSQL | fijar en C-01 |
| Colas / async | Redis (workers p/ jobs pesados) | — |
| Auth | JWT (expiración corta + refresh) | — |
| Frontend | React + TypeScript + Vite | fijar en C-01 |
| E2E | Playwright | — |
| Integraciones | WhatsApp · Google Calendar · Mercado Pago | — |
| Contenedores | Docker / Docker Compose (healthchecks) | — |

Detalle completo: [knowledge-base/02_descripcion_general.md](knowledge-base/02_descripcion_general.md)

---

## Base de Conocimiento

La fuente de verdad del dominio vive en `knowledge-base/`. **Leé el archivo relevante ANTES de implementar.**

| Archivo | Cuándo leerlo |
|---------|---------------|
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Entender propósito y alcance |
| [02_descripcion_general.md](knowledge-base/02_descripcion_general.md) | Stack, arquitectura, integraciones |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | Auth, RBAC, permisos |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Entidades, ERD, migraciones |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | Reglas codificadas (RN-XX) |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Historias de usuario por épica |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Flujos E2E |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Patrones, estructura, env vars |
| [09_decisiones_y_supuestos.md](knowledge-base/09_decisiones_y_supuestos.md) | Decisiones y supuestos |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | ⚠️ Inconsistencias a resolver ANTES de codear |
| [11_analisis_competidores.md](knowledge-base/11_analisis_competidores.md) | Contexto de mercado, patrones a clonar |

> ⚠️ Resolver las preguntas de prioridad **Alta** de `10_preguntas_abiertas.md` antes de arrancar el primer change.

---

## Skills Disponibles

Fuente de verdad: `.atl/skill-registry.md` (project-local, `.agents/skills/` + `skills-lock.json`). Skills instaladas a nivel proyecto, no global.

| Agente | Rol | Skills que carga |
|--------|-----|------------------|
| **Backend Core** | FastAPI / SQLAlchemy / Alembic / Postgres | `postgresql-table-design` |
| **Integraciones** | WhatsApp / GCal / Mercado Pago / Redis workers | `gws-calendar-agenda` |
| **Frontend** | React / TS / Vite mobile-first | `vercel-react-best-practices`, `frontend-design` |
| **QA E2E** | Flujos de turnos (reserva, seña, 24h) | `playwright-cli` |
| **Orquestación y Specs** | OPSX / SDD / Auditoría de Reglas | `openspec-propose`, `openspec-apply-change`, `openspec-archive-change`, `openspec-explore` (en `.opencode/skills/`), `spec-rules-auditor` |

Cargá la skill correspondiente al contexto ANTES de escribir código.

### Skill Propia: `spec-rules-auditor`
- **Ubicación:** `.agents/skills/spec-rules-auditor/SKILL.md` (registrada en `.atl/skill-registry.md`).
- **Cuándo usarla:** Durante la preparación, exploración o revisión de un change (`/opsx:propose`, `/opsx:explore`) o al redactar/revisar `spec.md`, `proposal.md` y `design.md`.
- **Qué necesita:** 
  1. Fuente de verdad de negocio: `knowledge-base/05_reglas_de_negocio.md` y reglas duras (`AGENTS.md`).
  2. Artefacto a auditar: borrador de la propuesta, diseño o especificación delta.
- **Cómo revisar el resultado:**
  1. Verificar que el dictamen (`APROBADO` / `OBSERVACIONES`) contenga la Matriz de Trazabilidad de reglas.
  2. Comprobar que genere la terna de escenarios obligatorios (Esperado / Error de negocio / Caso de borde) en formato BDD.
  3. Confirmar que los ejemplos utilicen información 100% sintética (R19).

---

## Servidores MCP (Integraciones Externas)

> Los servidores MCP conectan al agente con herramientas y servicios externos del sistema; se documentan como integraciones de entorno y no se registran como skills.

### Google Stitch MCP (`@_davideast/stitch-mcp`)
- **Propósito:** Asistir en el prototipado visual y estructuración UI de pantallas mobile-first mediante la plataforma Google Stitch (Google Labs).
- **Capacidades utilizadas:** Generación de pantallas con `generate_screen_from_text`, consulta con `get_screen` y `list_screens`, y descarga del HTML y la captura de cada pantalla con `download_file`. Primer uso real: 2026-11-03 (evidencia en `docs/skills-mcp/evidencia-stitch/`).
- **Momento de uso:** En la etapa de elaboración del `design.md` de changes que involucran interfaz de usuario (ej. `C-05`, `C-08`), asegurando cumplimiento estricto del viewport 360px (R3).
- **Límites de acceso y seguridad:** Acceso exclusivo a artefactos visuales de presentación. Prohibido el acceso a bases de datos o datos sensibles de pacientes; uso exclusivo de datos de fantasía/sintéticos (Ley 25.326 y R19). Requiere un proyecto de Google Cloud con la API de Stitch habilitada y una credencial de vida corta (`STITCH_ACCESS_TOKEN`) o `STITCH_API_KEY`, fuera del repo; ver README sección 9.2.

> Los compact rules de cada skill los resuelve el orquestador desde `.atl/skill-registry.md` (generado por `skill-registry`; no versionado — no está en el repo). Esta tabla solo mapea skill→rol.

---

## Roadmap de Changes

El plan de implementación completo está en [CHANGES.md](CHANGES.md). Resumen:

- **Total**: 16 changes en 5 fases.
- **Camino crítico** (9): detalle en `CHANGES.md` (eje `C-01 → … → C-13` con `C-06 sena-pagos-turno` como change propio de la restricción de seña).
- **Primer change**: `C-01` (foundation-setup) → arrancar con `/opsx:propose C-01-foundation-setup`.
- Estado actual: C-01 a C-09, C-11 y C-12 archivados; próximos por árbol: C-10, C-14 y C-15 (C-15 obligatorio antes de producción), C-16, y C-13 (requiere C-12).

**Antes de cualquier `/opsx:propose`**: leé [CHANGES.md](CHANGES.md), identificá las dependencias del change y los archivos de "Leer antes".

---

## Reglas Duras (específicas del proyecto)

> No hay `~/.claude/CLAUDE.md` global en esta máquina: no hay nada heredado. Las reglas de abajo son el contrato completo. Son contrato; romperlas es un defecto. Formato `NUNCA X → hacer Y`.

**Frontend (React + TypeScript + Vite)**
- R1. NUNCA `any` → TypeScript estricto (`tsconfig` strict), componentes en PascalCase.
- R2. NUNCA fetches en cascada en el flujo de reserva → paralelizar con `Promise.all` + límites `Suspense`.
- R3. NUNCA una pantalla de reserva que no funcione a 360px → mobile-first es criterio de aceptación.

**Base de datos (PostgreSQL vía SQLAlchemy + Alembic)**
- R4. NUNCA tipos sin zona horaria / strings sin límite / float para dinero → `DateTime(timezone=True)`, `String` + `CHECK`, `Numeric` vía SQLAlchemy.
- R5. NUNCA solape de agenda solo a nivel aplicación → `EXCLUDE USING gist` (recurso + rango) como garantía en DB.
- R6. NUNCA FK sin su índice → Postgres no los auto-indexa.

**Tests**
- R7. NUNCA dar por hecho un flujo de turnos (reserva, seña, ventana 24h) sin su E2E Playwright en verde.

**Dominio (contrato con la KB)**
- R8. NUNCA bloquear agenda con un turno `en_espera` → solo la seña acreditada bloquea el slot. Excepción (C-08, O7): el alta manual de recepción o admin nace `reservado` sin seña.
- R9. NUNCA reembolsar la seña ante ausente → queda registrado como recupero.
- R10. Las reglas `RN-XX` de `knowledge-base/05_reglas_de_negocio.md` son contrato.

**Backend (Python / FastAPI / SQLAlchemy / Redis / Docker)**
- R13. NUNCA código sin type hints → todo el backend con firmas tipadas.
- R14. NUNCA SQL crudo fuera de migraciones → SQLAlchemy ORM + Alembic, migraciones siempre reversibles.
- R15. NUNCA endpoint sin esquemas Pydantic de entrada/salida → validación en el borde.
- R16. NUNCA bloquear el event loop → I/O async y trabajo pesado a workers vía Redis.
- R17. NUNCA secretos en código → env vars (Docker Compose); JWT con expiración corta + refresh.
- R18. Backend y servicios solo vía Docker Compose con healthchecks de Postgres/Redis.

**Universales (van acá porque no hay global que las cubra)**
- R11. NUNCA commitear/pushear sin pedido explícito → cambios quedan en working tree.
- R12. Commits con conventional commits, sin co-autoría IA.
- R20. NUNCA crear archivos sueltos en la raíz fuera de la estructura canónica ni commitear archivos de configuración .env*. La raíz solo almacena los artefactos canónicos de la metodología (AGENTS.md, CLAUDE.md, CHANGES.md, README.md, .active-orchestrator-state.json) y los archivos de infraestructura del stack (Dockerfile, compose, requirements, alembic, pytest).

**Privacidad**
- R19. NUNCA utilizar datos reales de pacientes en el repositorio, seeds, tests o logs → información 100% sintética (Ley 25.326).

---

## Flujo de Trabajo

```
1. Leer la KB relevante (knowledge-base/)        → entender el dominio
2. Identificar el change en CHANGES.md           → respetar dependencias
3. /opsx:propose C-NN-nombre                     → proposal + design + specs + tasks
4. Implementar las tasks (cargando skills)       → respetando las reglas duras
5. /opsx:archive C-NN-nombre + marcar [x]        → cerrar el change
```

Aplicar TODAS las reglas duras en cada paso. Ante conflicto entre la KB y este archivo, las reglas duras prevalecen.
