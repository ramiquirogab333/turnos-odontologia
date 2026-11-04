# Spec Delta: dominio/modelos-core

## Purpose
Establece los modelos de datos relacionales, tipos de datos estrictos, restricciones de integridad referencial, índices foráneos e inicialización idempotente para el núcleo del sistema odontológico (pacientes, usuarios, roles, disponibilidad, auditoría y coberturas).

## ADDED Requirements

### Requirement: Modelado e integridad de entidades core
El sistema SHALL proveer modelos relacionales para Paciente, Usuario, Rol, Disponibilidad, ObraSocial, Nomenclador y RegistroAuditoria, utilizando marcas temporales con zona horaria, tipos numéricos de punto fijo para aranceles e índices en todas las claves foráneas.

#### Scenario: Persistencia válida de entidades relacionadas (Happy Path)
- **WHEN** se persiste un nuevo Paciente con DNI "38123456" y teléfono "+5491144445555", un Usuario con Rol "odontologo" y una franja de Disponibilidad para día lunes
- **THEN** PostgreSQL almacena los registros con timestamps en UTC, genera identificadores primarios y resuelve las relaciones foráneas válidas sin errores

#### Scenario: Rechazo ante violación de integridad referencial o unicidad (Error de Negocio)
- **WHEN** se intenta insertar un Paciente sin DNI o con DNI duplicado, o un registro de Turno asignando un `paciente_id` inexistente
- **THEN** la base de datos rechaza la transacción con violación de clave foránea, unicidad o check constraint, el Unit of Work ejecuta un rollback atómico y no persiste registros parciales

### Requirement: Idempotencia en la carga inicial de datos (Seeding)
El sistema SHALL proveer un procedimiento de carga inicial de datos (seeds) que garantice la inserción de roles base, usuario administrador, tratamientos con duración y nomenclador sin generar duplicados ante múltiples ejecuciones consecutivas.

#### Scenario: Doble ejecución consecutiva del script de seeds (Caso de Borde)
- **WHEN** el comando de seeding se ejecuta por primera vez sobre una base vacía y posteriormente se re-ejecuta de manera inmediata sobre los mismos datos
- **THEN** la segunda ejecución completa con código de éxito sin arrojar violaciones de clave única, la cantidad total de registros en cada tabla permanece idéntica y no se alteran las fechas de creación originales
