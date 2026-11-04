# Design: c-04-catalogo-tratamientos-disponibilidad

## Context
C-02 creó los modelos base `Tratamiento`, `Profesional`, `Sillon` y `Disponibilidad`, pero no hay forma de administrarlos desde el panel. C-03 ya provee `PermissionContext.require_role()` listo para usar. C-04 añade CRUD admin puro para estos catálogos, protegiendo endpoints con el RBAC de C-03 y respetando las reglas duras **R4** (DateTime tz-aware, Numeric dinero, strings acotados + CHECK), **R5** (anti-solape solo a nivel app), **R6** (índice en cada FK), **R13** (type hints 100%), **R14** (SQLAlchemy ORM + Alembic reversible), **R15** (Pydantic in/out), **R16** (I/O async) y **R17** (secretos solo env vars).

---
## Goals / Non-Goals

**Goals:**
- CRUD admin para tratamientos, profesionales, sillones y disponibilidad bajo prefijo `/api/admin/`.
- Protección RBAC `require_role('recepcion')` / `require_role('admin')` en cada endpoint (C-03).
- Esquemas Pydantic de entrada/salida para cada entidad (R15).
- Servicios async usando `BaseRepository[T]` y `UnitOfWork` de C-02 (R13, R16).
- Migración Alembic 004 reversible con constraints de catálogo (`duracion_minutos > 0`, `precio_base >= 0`, etc.).
- Auditar cambios de catálogo en `RegistroAuditoria` (RN-GL-01).
- Regla: duración editable por admin sin tocar código; al cambiarla los horarios libres se recalculan (sin migración de datos históricos) — RN-TU-05, DD-03.

**Non-Goals:**
- Frontend admin UI — **C-08**.
- Cálculo dinámico de horarios libres público (`GET /api/public/disponibilidad`) — **C-05**.
- Endpoints de reserva pública — **C-05**.
- WhatsApp — **C-09**.
- Google Calendar — **C-10**.

---
## Decisions

### Decision 1: Endpoints admin CRUD bajo prefijo `/api/admin/` con protección RBAC
* **Decisión:** Routers `GET/POST/PUT/DELETE` para cada entidad bajo `/api/admin/tratamientos`, `/api/admin/profesionales`, `/api/admin/sillones`, `/api/admin/disponibilidad`, cada uno protegido con `Depends(require_role('recepcion'))` o `Depends(require_role('admin'))` de `app.auth.rbac`.
* **Alternativas descartadas:** Prefijo `/api/panel/` (inconsistencia con C-03 que usa `/api/auth`; se elige `/api/admin` por claridad de propósito), protección a nivel aplicación sin `require_role` (violaría el patrón de C-03).

### Decision 2: Esquemas Pydantic de entrada/salida para cada entidad (R15)
* **Decisión:** Para cada entidad se definen `Create` (sin `id`, sin campos computados), `Read` (con `id`, `from_attributes=True`) y `Update` (campos opcionales). `extra="forbid"` para rechazar campos inesperados con 422. Tipos `int`, `str`, `Decimal` para dinero, `time` para horas, `datetime` tz-aware donde aplique (R4).
* **Alternativas descartadas:** Esquema único para create/read/update (menos seguro, aceptaría `id` en creación), `dataclasses` sin validación (violaría R15).

### Decision 3: Servicios async usando BaseRepository[T] y UnitOfWork de C-02 (R13, R16)
* **Decisión:** Cada servicio hereda de `BaseRepository[T]` y opera dentro de un `UnitOfWork` (commit explícito tras cada escritura). Firmas 100% tipadas (R13), I/O async sin bloquear el event loop (R16). Auditoría insertada en `RegistroAuditoria` dentro de la misma transacción (RN-GL-01).
* **Alternativas descartadas:** SQLAlchemy session directa sin repositorio (duplica lógica), transacciones manuales sin UoW (riesgo de olvidar commit/rollback).

### Decision 4: Migración Alembic 004 reversible con constraints de catálogo
* **Decisión:** Migración `004_catalogo.py` que añade/refuerza constraints `CHECK` (`duracion_minutos > 0`, `precio_base >= 0`, `dia_semana BETWEEN 0 AND 6`, `hora_fin > hora_inicio`) e índices en cada FK (R6). `upgrade` crea constraints/índices; `downgrade` los elimina. Reversible (R14), sin SQL crudo fuera de migraciones.
* **Alternativas descartadas:** Constraints solo en ORM (no son garantía en DB), `ALTER TABLE` crudo fuera de migración (violaría R14).

### Decision 5: Auditar cambios de catálogo en RegistroAuditoria (RN-GL-01)
* **Decisión:** En cada CREATE/UPDATE/DELETE de catálogo se inserta una fila en `RegistroAuditoria` (`accion`, `entidad`, `entidad_id`, `datos_antes`, `datos_despues`, `ip`) dentro de la misma transacción del UoW.
* **Alternativas descartadas:** Auditoría asíncrona externa (perdería atomicidad y trazabilidad inmediata), no auditar (violaría RN-GL-01).

**Decisiones alineadas con:** R4, R6, R13, R14, R15, R16, R17, RN-TU-04, RN-TU-05, RN-GL-01, DD-03.

---
## Risks / Trade-offs

- **[Riesgo: Edición de duración invalida horarios futuros]** → *Mitigación:* la duración se edita sin tocar datos históricos (turnos ya creados conservan su `fin` original); solo afecta el recálculo de libres futuro (C-05). Se documenta la interfaz de recálculo para C-05.
- **[Riesgo: Borrado de tratamiento/sillón/profesional con turnos asociados]** → *Mitigación:* `ForeignKey(..., ondelete="RESTRICT")` en `turno` impide el borrado con dependencias; el endpoint devuelve 409/422 con mensaje claro.
- **[Riesgo: Rol odontólogo intenta escribir catálogo]** → *Mitigación:* `require_role('recepcion')` / `require_role('admin')` devuelve 403 para cualquier rol distinto.
