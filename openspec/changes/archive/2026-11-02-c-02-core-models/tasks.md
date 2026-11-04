# Tasks: c-02-core-models

## 1. Modelos SQLAlchemy y Mixins Base

- [x] 1.1 Implementar mixins base `TimestampMixin` (`created_at`, `updated_at` con `DateTime(timezone=True)` - R4) y `ActiveMixin` (`is_active: bool`) en `backend/src/app/models/base.py`, verificando defaults y comportamiento con tests unitarios.
- [x] 1.2 Implementar modelos tipados con SQLAlchemy 2.0 `Paciente` (con DNI obligatorio numérico de 7 u 8 dígitos y constraint `CHECK`, teléfono E.164), `Disponibilidad`, `Usuario`, `Rol`, `UsuarioRol`, `RegistroAuditoria`, `ObraSocial` y `Nomenclador`, garantizando índices manuales en cada FK (R6), tipos `Numeric` para dinero (R4) y strings acotados con constraints. ✅ Código en `backend/src/app/models/core.py`.
- [x] 1.3 Actualizar modelo `Turno` incorporando `paciente_id` como clave foránea con índice explícito (R6). ✅ Código en `backend/src/app/turnos/models.py` (FK `paciente_id` + índice compuesto `ix_turno_paciente_inicio`).

## 2. Repositorios y Unit of Work Asíncrono

- [x] 2.1 Implementar interfaz y clase concreta `BaseRepository[T]` en `backend/src/app/repositories/` con operaciones asíncronas CRUD estándar (R13, R16). ✅ Código en `backend/src/app/repositories/base.py`.
- [x] 2.2 Implementar `UnitOfWork` async gestionando el ciclo de vida de la sesión de base de datos y garantizando transacciones atómicas con rollback automático ante excepciones. ✅ Código en `backend/src/app/repositories/uow.py`.

## 3. Migración de Base de Datos Alembic 002

- [x] 3.1 Crear script de migración reversible `002_core_models.py` en `backend/src/alembic/versions/` conteniendo las tablas del core, claves foráneas, restricciones de unicidad e índices manuales.
- [x] 3.2 Verificar la reversibilidad de la migración ejecutando `alembic upgrade head` seguido de `alembic downgrade -1` y re-upgrade en entorno de prueba sin pérdida de integridad (R14).

## 4. Seeds Idempotentes y Verificación de Escenarios (SDD)

- [x] 4.1 Implementar script de carga inicial de datos `backend/src/app/db/seeds/` que precargue roles (`admin`, `odontologo`, `recepcion`), usuario admin inicial, catálogo de tratamientos con duración real (RN-TU-05), obras sociales de referencia y múltiples odontólogos/sillones (cierra SU-03).
- [x] 4.2 Verificar **Escenario 1 (Happy Path)** y **Escenario 2 (Error de Negocio)** mediante tests pytest: persistencia correcta de relaciones foráneas y rechazo con rollback atómico ante FK inexistente o email duplicado.
- [x] 4.3 Verificar **Escenario 3 (Caso de Borde)**: test automatizado que ejecuta el seeder dos veces consecutivas comprobando que no arroja violaciones de clave única y mantiene cardinalidad exacta de registros.

## Workflow follow-up
- Una vez implementadas las tareas y verificados los tests, archivar con `openspec archive c-02-core-models`.
