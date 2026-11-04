# Proposal: c-04-catalogo-tratamientos-disponibilidad

## Why
C-02 (`core-models`) estableció los modelos base del dominio (`Tratamiento`, `Profesional`, `Sillon`, `Disponibilidad`) pero no hay forma de administrarlos desde el panel interno. Sin CRUD administrativo, ni recepción ni admin pueden dar de alta, editar o dar de baja tratamientos (nombre, `duracion_minutos`, `precio_base`), profesionales, sillones ni franjas de disponibilidad. Ese catálogo es el insumo que alimenta el cálculo de horarios libres (US-008) en C-05, por lo que debe ser editable por la clínica sin tocar código (RN-TU-05, DD-03).

C-04 cierra esta brecha con endpoints admin CRUD protegidos por el RBAC de C-03 y una migración Alembic 004 reversible que refuerza las constraints de catálogo (duración > 0, precio >= 0).

## What Changes
- **Endpoints admin CRUD (protegidos por C-03, rol `recepcion` o `admin`; Pydantic in/out, R15):**
  - `GET/POST/PUT/DELETE /api/admin/tratamientos`
  - `GET/POST/PUT/DELETE /api/admin/profesionales`
  - `GET/POST/PUT/DELETE /api/admin/sillones`
  - `GET/POST/PUT/DELETE /api/admin/disponibilidad`
- **Esquemas Pydantic** de entrada/salida para cada entidad (Crear/Leer/Actualizar).
- **Servicios async** sobre `BaseRepository[T]` + `UnitOfWork` de C-02 (R13, R16).
- **Migración Alembic 004** (reversible): constraints de catálogo (`duracion_minutos > 0`, `precio_base >= 0`, etc.).
- **Auditoría** de CREATE/UPDATE/DELETE de catálogo en `RegistroAuditoria` (RN-GL-01).

## Capabilities
### New Capabilities
- `catalogo/tratamientos`: CRUD admin de tratamientos (nombre, duración, precio base).
- `catalogo/profesionales`: CRUD admin de profesionales (nombre, matrícula, especialidad).
- `catalogo/sillones`: CRUD admin de sillones (nombre, estado).
- `catalogo/disponibilidad`: CRUD admin de franjas horarias de disponibilidad (profesional, día_semana, hora_inicio, hora_fin, sillon_defecto).

### Modified Capabilities
- Ninguna.

## Impact
- **Backend:** Nuevos módulos en `backend/src/app/catalogo/` (esquemas Pydantic, servicios async, routers admin) y aplicación de `require_role()` de C-03.
- **Base de Datos:** Migración `004_catalogo.py` en `backend/src/alembic/versions/` con constraints de catálogo.
- **Tests:** suite pytest que verifica CRUD denegado por rol sin permiso (403), duración inválida → 422 (CHECK), CRUD exitoso con rol `recepcion` (201/200/204), y auditoría en `RegistroAuditoria` (RN-GL-01).
