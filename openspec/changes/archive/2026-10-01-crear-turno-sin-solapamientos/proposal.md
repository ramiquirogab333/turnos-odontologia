# Proposal

## Why

La agenda del consultorio necesita una primitiva de creación de turnos que impida el doble-booking por profesional Y por sillón/box desde el día 1 (multi-odontólogo/multi-sillón, Resolución PO 2026-09-30). Sin una garantía a nivel de base de datos, dos reservas concurrentes sobre el mismo slot pueden crear turnos solapados aunque la validación de aplicación exista. Este change funda el backend y el constraint que todos los changes posteriores (C-02…C-13) heredan.

## What Changes

- Backend mínimo FastAPI (`backend/`): app con `GET /api/health`, `shared/` con settings Pydantic, logger, db async, exceptions; todo tipado (R13), sin SQL crudo fuera de migraciones (R14), Pydantic in/out en el borde (R15), I/O async (R16), secretos solo por env vars (R17).
- `docker-compose.yml`: servicios `backend` + `postgres` con healthcheck de Postgres (R18); `.env.example` con `DATABASE_URL`. Sin Redis (llega en C-09).
- Modelos SQLAlchemy tipados (migración Alembic 001, reversible): `Profesional`, `Sillon`, `Tratamiento` (nombre, `duracion_minutos > 0`, `precio_base` Numeric — se incluye en 001 para evitar un ALTER posterior), `Turno` (`inicio`/`fin` `DateTime(timezone=True)`, `profesional_id` + `sillon_id` NOT NULL, `tratamiento_id`, columna `estado` TEXT+CHECK desde 001).
- Garantía anti-solape en DB (R5): dos `EXCLUDE USING gist` PARCIALES sobre `Turno` — uno por `(profesional_id WITH =, periodo WITH &&)`, otro por `(sillon_id WITH =, periodo WITH &&)`, ambos `WHERE (estado IN (...bloqueantes...))` desde el día 1 (estrategia A decidida 2026-09-30: el `en_espera` no bloqueante de C-06 nunca colisionará — R8 forward-compat).
- `POST /api/turnos` interno (identity-free: sin Paciente/nombre/teléfono — Q2): recibe `profesional_id + sillon_id + tratamiento_id + inicio`; `fin = inicio + duracion del tratamiento` (RN-TU-04; un `fin` enviado por el cliente se rechaza/ignora); `inicio` en el pasado → 422 (Q3); solape por profesional o por sillón → 409 con motivo enum (`profesional` vs `sillon`, Q4); violación del EXCLUDE (23P01) se mapea a 409, nunca 500.
- Tests: E2E Playwright de carrera — dos reservas concurrentes sobre el mismo slot → exactamente un 201 + un 409 (R7); test a nivel DB de doble-INSERT solapado rechazado por el EXCLUDE; padres FK (Profesional/Sillon/Tratamiento) creados vía inserts directos en el harness (sus CRUDs llegan en C-04).
- EXPLÍCITAMENTE FUERA: `frontend-paciente/` → C-05; `frontend-panel/` → C-08; CI → C-05; jobs/scheduler + Redis workers → C-09.

## Capabilities

### New Capabilities

- `turnos/creacion-sin-solape`: crear un turno con anti-solape por profesional y por sillón/box, con `fin` derivado de la duración del tratamiento, errores 422/409 tipados y garantía EXCLUDE en DB. Incluye los DDL de las 4 tablas, el endpoint `POST /api/turnos`, el `GET /api/health` mínimo y el E2E de carrera concurrente.

### Modified Capabilities

- (vacío — no hay specs existentes; `openspec list --specs` está vacío)

## Impact

- Afecta: `backend/`, `docker-compose.yml`, `.env.example`, migración Alembic 001, `POST /api/turnos`, `GET /api/health`, suite E2E Playwright.
- Dependencias: ninguna (GATE 0, primer change del árbol).
- Desbloquea: C-02 (`core-models` extiende las 4 tablas) y, vía C-05, el endpoint público que reutiliza esta primitiva (`POST /api/public/turnos` documentado como capa que construye sobre este endpoint interno — supersede-vs-reuse explícito: C-05 reutiliza el constraint, no lo reemplaza).
- Governance MEDIUM: el checkpoint exige mostrar el DDL del `EXCLUDE USING gist` (`btree_gist`, `tstzrange` con bounds `'[)'`, parcial por `estado`) + el test de carrera concurrente en `design.md`/`tasks.md` antes de asumir trabajo de apply.
