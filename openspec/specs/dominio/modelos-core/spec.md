# dominio/modelos-core Specification

## Purpose
Establece los modelos de datos relacionales, tipos de datos estrictos, restricciones de integridad referencial, índices foráneos e inicialización idempotente para el núcleo del sistema odontológico (pacientes, usuarios, roles, disponibilidad, auditoría y coberturas).

## Requirements

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

### Requirement: RegistroAuditoria es de solo agregado y consultable por entidad
`RegistroAuditoria` SHALL rechazar en la base toda modificación o borrado de filas, su referencia al usuario SHALL impedir borrar un usuario con registros, la IP SHALL tener a lo sumo 45 caracteres y SHALL existir un índice por entidad, id de entidad e instante. La migración que lo establece SHALL ser reversible (R14).

#### Scenario: Esquema tras migrar (Happy Path)
- **WHEN** se aplica la migración `013_auditoria_exportacion`
- **THEN** la tabla rechaza `UPDATE` y `DELETE`, la FK de usuario es `RESTRICT`, existe el índice `(entidad, entidad_id, created_at)` y el `CHECK` de longitud de IP

#### Scenario: IP demasiado larga (Error de Negocio)
- **WHEN** se intenta guardar un registro con una IP de 46 caracteres
- **THEN** la base lo rechaza por el `CHECK` y no se guarda nada

#### Scenario: Volver atrás la migración (Caso de Borde)
- **GIVEN** la base en `013_auditoria_exportacion` con registros existentes
- **WHEN** se ejecuta `downgrade -1` y luego `upgrade head`
- **THEN** el downgrade quita el trigger, el índice y el `CHECK` y restaura la FK `SET NULL` sin perder registros, y el upgrade vuelve a aplicarlos
