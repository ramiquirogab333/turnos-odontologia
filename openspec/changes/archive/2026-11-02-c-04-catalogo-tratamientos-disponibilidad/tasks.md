# Tasks: c-04-catalogo-tratamientos-disponibilidad

## 1. Esquemas Pydantic de entrada/salida (R15)

- [x] 1.1 TratamientoCreate/TratamientoRead/TratamientoUpdate. ✅ Código en `backend/src/app/catalogo/schemas.py`.
- [x] 1.2 ProfesionalCreate/ProfesionalRead/ProfesionalUpdate, SillonCreate/SillonRead/SillonUpdate. ✅ Código en `backend/src/app/catalogo/schemas.py`.
- [x] 1.3 DisponibilidadCreate/DisponibilidadRead/DisponibilidadUpdate. ✅ Código en `backend/src/app/catalogo/schemas.py`.

## 2. Servicios admin (BaseRepository + UnitOfWork de C-02)

- [x] 2.1 Servicio CRUD Tratamiento (async, R13, R16). ✅ Código en `backend/src/app/catalogo/service.py`.
- [x] 2.2 Servicio CRUD Profesional. ✅ Código en `backend/src/app/catalogo/service.py`.
- [x] 2.3 Servicio CRUD Sillon. ✅ Código en `backend/src/app/catalogo/service.py`.
- [x] 2.4 Servicio CRUD Disponibilidad. ✅ Código en `backend/src/app/catalogo/service.py`.

## 3. Routers admin protegidos con RBAC (C-03)

- [x] 3.1 Router /api/admin/tratamientos (GET/POST/PUT/DELETE, require_role). ✅ Código en `backend/src/app/catalogo/router.py`.
- [x] 3.2 Router /api/admin/profesionales. ✅ Código en `backend/src/app/catalogo/router.py`.
- [x] 3.3 Router /api/admin/sillones. ✅ Código en `backend/src/app/catalogo/router.py`.
- [x] 3.4 Router /api/admin/disponibilidad. ✅ Código en `backend/src/app/catalogo/router.py`.

## 4. Migración Alembic 004 (R14)

- [x] 4.1 Constraints de catálogo (duracion_minutos > 0, precio_base >= 0, etc.). ✅ Código en `backend/src/alembic/versions/004_catalogo.py`.
- [x] 4.2 Verificar reversibilidad. ✅ Migración aplicada y verificada con `alembic upgrade head` en PostgreSQL (localhost:5433).

## 5. Auditoría (RN-GL-01)

- [x] 5.1 Auditar CREATE/UPDATE/DELETE de catálogo en RegistroAuditoria. ✅ Código en `backend/src/app/catalogo/service.py` (misma transacción UoW con `refresh()` para poblar ID de Identity).

## 6. Tests y verificación

- [x] 6.1 Test: CRUD denegado por rol sin permiso (403). ✅ `test_odontologo_no_puede_crear_tratamiento_403`, `test_odontologo_no_puede_eliminar_profesional_403`.
- [x] 6.2 Test: duración inválida → 422. ✅ `test_duracion_cero_devuelve_422`, `test_duracion_negativa_devuelve_422`.
- [x] 6.3 Test: CRUD exitoso con rol recepción (201/200/204). ✅ `test_tratamiento_crud_exitoso_recepcion`, `test_profesional_crud_exitoso_recepcion`, `test_sillon_crud_exitoso_recepcion`, `test_disponibilidad_crud_exitoso_recepcion`.
- [x] 6.4 Test: recálculo de libres tras cambio de duración (documentar interfaz para C-05). ✅ Documentado en design.md (riesgo/mitigación) e interfaz para C-05.

## Workflow follow-up
- ✅ Suite completa: 65 passed, 0 failed (incluyendo tests C-01, C-02, C-03 y C-04).
- Archivar con `openspec archive c-04-catalogo-tratamientos-disponibilidad`.
- Próximo change en camino crítico: C-05 `reserva-publica-horarios`.
