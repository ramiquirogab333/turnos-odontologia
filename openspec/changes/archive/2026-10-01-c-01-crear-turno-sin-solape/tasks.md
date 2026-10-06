# Tasks

## 1. Pins, scaffolding y Compose

- [ ] 1.1 Congelar pins exactos (Python 3.12 `python:3.12-slim-bookworm`, `postgres:16-alpine`, `fastapi==*`, `sqlalchemy==*`, `alembic==*`, `pydantic==*`, `asyncpg==*`, `uvicorn==*`) contra los stables vigentes y registrarlos en `backend/requirements.txt` + `Dockerfile` + `docker-compose.yml`, y verificar con `pip install --dry-run` o build que las versiones resuelven sin conflicto.
- [ ] 1.2 Crear layout mínimo (`backend/app/main.py`, `backend/app/shared/{settings,db,logger,exceptions}.py`, `backend/app/turnos/{models,schemas,router,service}.py`, `backend/alembic/` con env async, `.env.example` con `DATABASE_URL` y `APP_TZ`, `Dockerfile`) con type hints en todo el backend (R13) y verificar con `mypy`/`pyright` o `python -m compileall` que no hay errores de tipos/sintaxis.
- [ ] 1.3 Crear `docker-compose.yml` (`backend` + `postgres` con healthcheck `pg_isready`, sin Redis) y verificar con `docker compose up -d postgres` que el servicio postgres pasa a `healthy`.

## 2. Modelos y migración Alembic 001

- [x] 2.1 Implementar modelos SQLAlchemy tipados (`Profesional`, `Sillon`, `Tratamiento` con `duracion_minutos > 0` y `precio_base Numeric(10,2)`, `Turno` con `DateTime(timezone=True)`, `sillon_id` NOT NULL, `estado` TEXT+CHECK, `periodo` tstzrange generado `'[)'`) e índices por cada FK más `(profesional_id, inicio)` y `(sillon_id, inicio)` (R4/R6), y verificar con un test de metadatos que cada FK tiene su índice y que los tipos son tz-aware/Numeric/CHECK. ✅ Verificado 2026-10-01: `backend/tests/test_models_metadata.py` 5/5 en verde (suite 27 passed).
- [ ] 2.2 Escribir migración Alembic 001 reversible con el DDL del checkpoint de `design.md` (`btree_gist` + 4 tablas + 2 EXCLUDE parciales `WHERE estado IN ('reservado','confirmado')`) y verificar con `alembic upgrade head` que las constraints `turno_no_solape_profesional` y `turno_no_solape_sillon` existen en `pg_constraint` con definición gist parcial.
- [ ] 2.3 Verificar reversibilidad con `alembic downgrade -1` seguido de `alembic upgrade head`, comprobando que el ciclo baja y sube limpio y que `btree_gist` sobrevive al downgrade.

## 3. Endpoint `POST /api/turnos` y manejo de errores

- [x] 3.1 Implementar `TurnoCreate`/`TurnoRead` Pydantic (R15, `extra="forbid"`: `fin` enviado → 422), `GET /api/health` (200 con Postgres ok) y `POST /api/turnos` (`fin = inicio + duracion`, `inicio` pasado → 422, FK inexistente o campo faltante → 422, todo async R16, secretos solo por env R17), y verificar con tests HTTP que la creación válida devuelve 201 con `fin` derivado exacto y que `fin` enviado por el cliente devuelve 422. ✅ Verificado 2026-10-01: tests HTTP 3.1 en verde dentro de `test_turnos_api.py` (suite 27 passed).
- [x] 3.2 Implementar chequeo previo de solape por rango (motivo `profesional` primero si ambos colisionan) más captura de `IntegrityError` SQLSTATE 23P01 mapeada a 409 (nunca 500), y verificar con tests HTTP que el solape por profesional devuelve 409 `profesional`, el solape por sillón devuelve 409 `sillon`, los slots adyacentes devuelven 201 y un turno sobre profesional y sillón libres devuelve 201. ✅ Verificado 2026-10-01: tests HTTP 3.2 (409 profesional/sillon, adyacencia 201, carrera 201+409, nunca 500) en verde (suite 27 passed).
- [ ] 3.3 Documentar en el router/docstring que `POST /api/turnos` es primitiva interna identity-free (sin Paciente) que C-05 reutiliza desde `POST /api/public/turnos`, y verificar que la documentación queda visible en `/docs` (OpenAPI) con los códigos 201/409/422 descritos.

## 4. Carrera concurrente y DB-level (R7)

- [ ] 4.1 Crear harness E2E Playwright (`e2e/`) con padres FK vía INSERTs SQL directos (sin CRUDs) y test de carrera de dos `POST /api/turnos` simultáneos sobre el mismo slot, y verificar que el resultado es exactamente un 201 y un 409 en corridas repetidas (`--repeat-each` o loop). ⏸️ DIFERIDO por orden del usuario 2026-10-01 (dos intentos previos colgaron popups `python.exe` en este host Windows; prohibido Playwright en cualquier forma). Desviación R7 registrada: evidencia interina = cobertura de concurrencia a nivel API (`test_carrera_concurrente_un_201_y_un_409`) + DB (`test_insert_concurrente_solo_uno_confirma`), ambas en verde en la suite 27 passed.
- [x] 4.2 Agregar test a nivel DB de doble-INSERT solapado en transacciones concurrentes sobre `turno` (mismo profesional y mismo sillón por separado) más test de adyacencia `'[)'`, y verificar que los INSERTs solapados abortan con SQLSTATE 23P01 mientras los adyacentes confirman. ✅ Verificado 2026-10-01: `backend/tests/test_turnos_db.py` 5/5 en verde (suite 27 passed).

## 5. Integración final y handoff

- [ ] 5.1 Correr la suite completa (migración desde cero + tests HTTP + tests DB + E2E Playwright) con `docker compose up --build` y verificar que todo está en verde y que ningún 409 esperado llega como 500 en los logs. ⏸️ Parcial 2026-10-01 (cierre solo-pytest por orden del usuario): `python -m pytest tests -q --no-header -p no:randomly` (workdir `backend/`) → **27 passed, 0 failed, 0 skipped in 3.41s** (verificado por el orquestador en la terminal actual; el sub-agente reportó 27 passed in 4.63s en su corrida); healthcheck explícito en verde (`GET /api/health` → 200 con Postgres ok, cubierto en 3.1); ningún 409 llegó como 500 (`test_ningun_solape_llega_como_500` verde). E2E Playwright pendiente (ver 4.1); `docker build` prohibido por orden del usuario.
- [ ] 5.2 Correr `openspec validate --change c-01-crear-turno-sin-solape` (o `openspec status --change c-01-crear-turno-sin-solape`) y verificar que los 4 artefactos reportan listos para review sin pendientes de planning.

## Archive record (2026-10-01 — archivado con warnings, por orden del usuario)

- Verificación verde a nivel código: `python -m pytest tests -q --no-header -p no:randomly` (workdir `backend/`) → 27 passed, 0 failed, 0 skipped; `GET /api/health` → 200; sweep nunca-500 verde. Nada rojo a nivel código; cero diffs de backend fueron necesarios.
- Specs sincronizados: `turnos/creacion-sin-solape` → `openspec/specs/turnos/creacion-sin-solape/spec.md` (6 requirements ADDED, validado con `openspec validate --specs` → 1 passed, 0 failed).
- Artefactos: proposal/specs/design/tasks = done (4/4). Tareas: 4/13 completas (2.1, 3.1, 3.2, 4.2); 9 abiertas por restricción de entorno/tooling, NO por código incompleto: 1.1, 1.2, 1.3, 2.2, 2.3, 3.3, 4.1, 5.1 (parcial), 5.2.
- DIFERIDO explícito — 4.1 E2E Playwright de carrera (dos POST simultáneos → un 201 + un 409): diferido por orden del usuario (popups `python.exe` cuelgan este host Windows; Playwright prohibido en cualquier forma). Desviación R7 registrada: cobertura interina verde a nivel API (`test_carrera_concurrente_un_201_y_un_409`) + DB (`test_insert_concurrente_solo_uno_confirma`) dentro de la suite 27 passed. Follow-up: C-05/C-08 o change dedicado retoma 4.1 cuando el host lo permita.
- R11 respetado: sin commits/push — todo queda en working tree.
