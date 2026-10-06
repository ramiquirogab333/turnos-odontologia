# Design

## Context

Ver `proposal.md` (Why). Estado actual: repo sin backend, sin DB, sin specs (`openspec list --specs` vacío); este es el primer change (GATE 0). Restricciones: R4 (tipos tz-aware/Numeric/CHECK), R5 (EXCLUDE en DB), R6 (índice por FK), R13–R18 (backend tipado, ORM+Alembic reversible, Pydantic en borde, async, env-only secrets, Compose con healthcheck), R8 (sin `en_espera` bloqueante aquí; forward-compat con C-06), RN-TU-03/04. Ver `specs/turnos/creacion-sin-solape/spec.md` para el contrato de comportamiento.

## Goals / Non-Goals

**Goals:**

- Vertical slice mínimo que demuestra `POST /api/turnos` con anti-solape real por profesional Y sillón, garantizado en DB.
- Dejar el DDL y los patrones (migración reversible, mapeo 23P01→409, harness E2E con inserts directos) que C-02…C-13 heredan.
- Cumplir el checkpoint de governance MEDIUM: DDL del EXCLUDE + test de carrera definidos antes del apply.

**Non-Goals:**

- Frontend paciente/panel, CI, Redis/workers, auth/JWT, catálogos CRUD, WhatsApp, GCal, pagos/seña (viven en C-03…C-10; ver proposal). No se agrega Redis al Compose aunque el stack lo incluya (llega en C-09).

## Decisions

### D1. Dos EXCLUDE parciales con columna `estado` desde 001 (estrategia A, veredicto usuario 2026-09-30)

Se incluye `estado TEXT NOT NULL + CHECK` en `Turno` desde la migración 001 y ambos EXCLUDE llevan predicado `WHERE (estado IN ('reservado','confirmado'))`. Así el `en_espera` de C-06 nace no-bloqueante sin necesidad de recrear constraints (R8 forward-compat). `cancelado`/`ausente`/`atendido` liberan el slot. Alternativa descartada: EXCLUDE totales sin predicado (habría que recrearlos en C-06 y el `en_espera` colisionaría por defecto).

### D2. Columna generada `periodo tstzrange` con bounds `'[)'`

`periodo tstzrange GENERATED ALWAYS AS (tstzrange(inicio, fin, '[)')) STORED`: los slots adyacentes (`fin` == `inicio` del siguiente) NO colisionan con `&&`. Alternativa descartada: EXCLUDE sobre la expresión `tstzrange(inicio, fin)` inline (funciona pero impide indexar/inspeccionar el rango y complica el downgrade).

### D3. `btree_gist` obligatorio en 001

Los EXCLUDE comparan `BIGINT WITH =` dentro de un índice GiST → requieren `CREATE EXTENSION IF NOT EXISTS btree_gist`. Sin ella, la migración falla. El `upgrade()` la crea primero; el `downgrade()` NO la elimina (extensión compartida con futuras migraciones).

### D4. `fin` derivado, `fin` del cliente rechazado con 422

Pydantic `TurnoCreate` declara solo `profesional_id/sillon_id/tratamiento_id/inicio` con `model_config = extra="forbid"` (RN-TU-04): un `fin` enviado responde 422. El servicio calcula `fin = inicio + tratamiento.duracion_minutos`. `inicio` naive se asume UTC y se normaliza a tz-aware; `inicio` pasado → 422 (Q3).

### D5. 409 con motivo enum (`profesional` vs `sillon`, Q4)

Doble capa: chequeo previo por rango (para devolver el motivo correcto) + captura de `IntegrityError` con SQLSTATE `23P01` como red de seguridad ante carreras (nunca 500). Si el chequeo previo no detecta solape pero el EXCLUDE salta (carrera), el handler re-consulta para determinar el motivo; si no puede determinarlo, responde 409 con motivo `profesional` por defecto documentado.

### D6. `sillon_id` NOT NULL día 1 + índice por cada FK (R6, multi-sillón día 1)

`Turno.profesional_id/sillon_id/tratamiento_id` NOT NULL con índices B-tree propios; además índices `(profesional_id, inicio)`, `(sillon_id, inicio)` para lectura de agenda. Alternativa descartada: `sillon_id` nullable (rompe el anti-solape por sillón y la ocupación de C-12).

### D7. Tipos R4 estrictos + `precio_base` Numeric en 001 (Q5)

`TIMESTAMPTZ` para `inicio/fin`, `NUMERIC(10,2)` para `precio_base`, `TEXT + CHECK(LENGTH<=n)` para strings, `BOOLEAN NOT NULL`, PK `BIGINT GENERATED ALWAYS AS IDENTITY`. `precio_base` entra en 001 para evitar un ALTER posterior (una línea de justificación exigida: el catálogo de C-04 lo necesita y crearlo después costaría una migración solo para una columna).

### D8. Stack y pins (Q6)

Líneas mayores: Python 3.12, PostgreSQL 16, FastAPI 0.11x, SQLAlchemy 2.0 (async + asyncpg), Alembic 1.1x, Pydantic 2.x, Uvicorn. Pins exactos de imagen y requirements (`python:3.12-slim-bookworm`, `postgres:16-alpine`, `fastapi==…`, `sqlalchemy==…`, `alembic==…`, `pydantic==…`, `asyncpg==…`, `uvicorn==…`) se congelan en la primera task del apply contra los stables vigentes y quedan registrados en `backend/requirements.txt` + Compose; la task lo exige explícitamente.

### D9. Endpoint interno identity-free (Q2)

`POST /api/turnos` no recibe ni devuelve identidad del paciente. C-05 construye `POST /api/public/turnos` (nombre+teléfono, código de gestión) sobre este constraint — reuse explícito, no supersede: esta primitiva sigue existiendo para el uso manual de C-08.

### D10. E2E Playwright de carrera + test DB de doble-INSERT; fixtures vía inserts directos

Padres FK (Profesional/Sillon/Tratamiento) creados con INSERTs SQL directos en el harness (sus CRUDs llegan en C-04). Dos niveles: (a) Playwright — dos `POST /api/turnos` concurrentes (fetch simultáneos desde el runner, sin UI: backend-only) → exactamente un 201 + un 409; (b) DB — dos INSERTs solapados en transacciones concurrentes → uno aborta con 23P01. Patrón Playwright según skill `playwright-cli` (scripts bajo `e2e/`, `--raw` para aserciones).

### D11. Layout backend mínimo

`backend/app/main.py` (FastAPI + handlers), `backend/app/shared/{settings,db,logger,exceptions}.py`, `backend/app/turnos/{models,schemas,router,service}.py`, `backend/alembic/` (env async + versiones), `backend/requirements.txt`, `Dockerfile`, `docker-compose.yml` (backend+postgres+healthcheck), `.env.example` (`DATABASE_URL` + `APP_TZ=America/Argentina/Buenos_Aires`). Sin SQL crudo fuera de `alembic/versions/` (R14).

## MEDIUM-Governance Checkpoint — DDL del EXCLUDE (mostrar antes del apply)

```sql
-- 001 (upgrade): pre-requisito GiST para comparar BIGINT dentro del EXCLUDE
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE profesional (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre     TEXT NOT NULL CHECK (LENGTH(nombre) BETWEEN 1 AND 120),
  matricula  TEXT NOT NULL CHECK (LENGTH(matricula) BETWEEN 1 AND 40),
  especialidad TEXT NOT NULL DEFAULT '' CHECK (LENGTH(especialidad) <= 120)
);

CREATE TABLE sillon (
  id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre TEXT NOT NULL CHECK (LENGTH(nombre) BETWEEN 1 AND 60),
  estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo','mantenimiento'))
);

CREATE TABLE tratamiento (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre           TEXT NOT NULL CHECK (LENGTH(nombre) BETWEEN 1 AND 120),
  duracion_minutos INTEGER NOT NULL CHECK (duracion_minutos > 0),
  precio_base      NUMERIC(10,2) NOT NULL CHECK (precio_base >= 0)
);

CREATE TABLE turno (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  profesional_id  BIGINT NOT NULL REFERENCES profesional(id) ON DELETE RESTRICT,
  sillon_id       BIGINT NOT NULL REFERENCES sillon(id) ON DELETE RESTRICT,
  tratamiento_id  BIGINT NOT NULL REFERENCES tratamiento(id) ON DELETE RESTRICT,
  inicio          TIMESTAMPTZ NOT NULL,
  fin             TIMESTAMPTZ NOT NULL CHECK (fin > inicio),
  estado          TEXT NOT NULL DEFAULT 'reservado'
                  CHECK (estado IN ('reservado','confirmado','en_espera','cancelado','ausente','atendido')),
  periodo         tstzrange GENERATED ALWAYS AS (tstzrange(inicio, fin, '[)')) STORED
);

CREATE INDEX ON turno (profesional_id);
CREATE INDEX ON turno (sillon_id);
CREATE INDEX ON turno (tratamiento_id);
CREATE INDEX ON turno (profesional_id, inicio);
CREATE INDEX ON turno (sillon_id, inicio);

-- Anti-solape por profesional (solo estados bloqueantes; '[)' => adyacentes no colisionan)
ALTER TABLE turno ADD CONSTRAINT turno_no_solape_profesional
  EXCLUDE USING gist (profesional_id WITH =, periodo WITH &&)
  WHERE (estado IN ('reservado', 'confirmado'));

-- Anti-solape por sillón/box (solo estados bloqueantes)
ALTER TABLE turno ADD CONSTRAINT turno_no_solape_sillon
  EXCLUDE USING gist (sillon_id WITH =, periodo WITH &&)
  WHERE (estado IN ('reservado', 'confirmado'));
```

`downgrade()`: dropea ambas constraints, índices, las 4 tablas (orden inverso); no remueve `btree_gist`. Test de carrera (resumen; detalle en `tasks.md`): dos `POST` concurrentes mismo slot → `assert sorted(statuses) == [201, 409]`; doble-INSERT concurrente → uno recibe `23P01` mapeado a 409.

## Risks / Trade-offs

- [Predicado parcial olvidado en C-06] → Mitigación: la spec exige que `en_espera` nunca colisione; C-06 cita este DDL como dependencia y su done-criteria lo verifica.
- [Motivo 409 ambiguo cuando ambos recursos colisionan] → Mitigación: si hay solape por ambos, se devuelve `profesional` primero (documentado en la spec del error y en tasks).
- [Reloj/zonas horarias (inicio pasado vs. TZ)] → Mitigación: todo tz-aware, `APP_TZ` por env, normalización en el borde; tests con casos borde UTC/Argentina.
- [Carrera entre chequeo previo e INSERT] → Mitigación: el EXCLUDE es la garantía real; el chequeo previo solo existe para el motivo del 409.
- [Adyacencia `'[)'` malinterpretada] → Mitigación: escenario explícito en la spec + test dedicado.

## Migration Plan

1. `docker compose up --build` (postgres healthy → backend).
2. `alembic upgrade head` (001 crea extensión + 4 tablas + constraints + índices).
3. Rollback: `alembic downgrade -1` (reversible, R14); sin datos previos no hay migración de datos.
4. Deploy: sin ventanas ni backfill (primera migración del proyecto).

## Open Questions

Ninguna que cambie specs, enfoque o tasks: las 6 preguntas de DISEÑO (Q1–Q6) quedaron decididas por el usuario el 2026-09-30. Solo queda congelar los patch pins al iniciar el apply (task 1).
