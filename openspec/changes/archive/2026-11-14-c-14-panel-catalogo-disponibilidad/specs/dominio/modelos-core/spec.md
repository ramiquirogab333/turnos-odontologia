# Spec Delta

## ADDED Requirements

### Requirement: Integridad del catálogo garantizada en la base
`tratamiento` y `profesional` SHALL tener `is_active` booleano no nulo con valor por defecto verdadero. La base SHALL rechazar dos franjas activas superpuestas del mismo profesional y día, y nombres de tratamiento o sillón y matrículas repetidos (sin distinguir mayúsculas ni espacios en los extremos). La migración SHALL ser reversible y no SHALL corregir datos existentes por su cuenta.

#### Scenario: Migración sobre datos válidos (Happy Path)
- **GIVEN** una base en `013_auditoria_exportacion` con el seed sintético
- **WHEN** se aplica `alembic upgrade head`
- **THEN** todos los tratamientos y profesionales quedan activos, las restricciones nuevas existen y `alembic downgrade -1` las quita sin perder filas

#### Scenario: Datos existentes que violan una restricción (Error de Negocio)
- **GIVEN** dos franjas activas de la misma profesional el lunes de 09:00 a 13:00 y de 12:00 a 15:00
- **WHEN** se aplica la migración
- **THEN** la migración se detiene sin cambios con un mensaje que nombra los ids de las franjas en conflicto

#### Scenario: Franjas superpuestas pero una inactiva (Caso de Borde)
- **GIVEN** una franja activa del lunes de 09:00 a 13:00 y otra inactiva de 12:00 a 15:00 de la misma profesional
- **WHEN** se inserta o migra
- **THEN** la base lo acepta; reactivar la segunda es rechazado por la base
