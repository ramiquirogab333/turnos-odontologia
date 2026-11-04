# Proposal: c-02-core-models

## Why
El cambio C-01 estableció el vertical slice mínimo con 4 entidades (`Profesional`, `Sillon`, `Tratamiento`, `Turno`) para validar la exclusión de solapamientos GiST en PostgreSQL. Para que el sistema pueda soportar la gestión de pacientes, la seguridad por roles, la disponibilidad horaria y la trazabilidad clínica requerida por las reglas de negocio, es necesario incorporar el resto de los modelos base del dominio (`Paciente`, `Disponibilidad`, `Usuario`, `Rol`, `RegistroAuditoria`, `ObraSocial`, `Nomenclador`), junto con las abstracciones de repositorio, Unit of Work y la migración Alembic 002 con seeds idempotentes.

## What Changes
- **Modelos de Dominio SQLAlchemy:**
  - `Paciente`: datos personales de contacto (nombre, apellido, DNI obligatorio con validación numérica de 7 u 8 dígitos, teléfono/WhatsApp obligatorio con validación E.164, obra social y número de afiliado opcionales).
  - `Disponibilidad`: reglas de franjas horarias por profesional y día de la semana (`dia_semana`, `hora_inicio`, `hora_fin`) y tabla de excepciones/feriados.
  - `Usuario`, `Rol` y tabla intermedia `UsuarioRol`: estructura para el control de acceso basado en roles (RBAC) requerido en el panel.
  - `RegistroAuditoria`: entidad para registrar acciones críticas (creación, modificación, cancelación de turnos, login/logout) con `usuario_id`, `accion`, `entidad`, `datos_json` y `timestamp` (RN-GL-01).
  - `ObraSocial` y `Nomenclador`: catálogo precargado de cobertura de prestaciones y aranceles odontológicos de referencia.
  - Actualización de `Turno`: agregado de clave foránea indexada `paciente_id` vinculando con `Paciente`.
- **Arquitectura de Persistencia y Mixins:**
  - Mixins reutilizables: `TimestampMixin` (`created_at`, `updated_at` con `DateTime(timezone=True)` - R4) y `ActiveMixin` (`is_active` booleano).
  - Abstracciones genéricas: `BaseRepository[T]` y `UnitOfWork` async (R13, R14, R16).
- **Migración de Base de Datos (Alembic 002):**
  - DDL reversible para crear las tablas restantes, asegurando claves foráneas indexadas manualmente (R6), tipos seguros sin floats para dinero (R4), y restricciones `CHECK` de integridad.
- **Seeds Idempotentes:**
  - Carga inicial reproducible: roles del sistema (`admin`, `odontologo`, `recepcion`), usuario administrador por defecto, nomenclador de obras sociales, configuración de múltiples profesionales y sillones (Resolución 2026-09-30 nº1) y catálogo inicial de tratamientos con duración parametrizada (RN-TU-05).

## Capabilities

### New Capabilities
- `dominio/modelos-core`: Estructura relacional completa para pacientes, usuarios, roles, disponibilidad horaria, auditoría y coberturas médicas, garantizando tipos estrictos, índices en FKs e idempotencia de inicialización.

### Modified Capabilities
- Ninguna.

## Impact
- **Backend:** Nuevos módulos en `backend/src/app/models/`, `backend/src/app/repositories/` y `backend/src/app/db/seeds/`.
- **Base de Datos:** Migración `002_core_models.py` en `backend/src/alembic/versions/`.
- **Tests:** Suite de pruebas en `backend/tests/` para verificar restricciones relacionales, timestamps con zona horaria, integridad referencial y doble corrida de seeds sin duplicación.
