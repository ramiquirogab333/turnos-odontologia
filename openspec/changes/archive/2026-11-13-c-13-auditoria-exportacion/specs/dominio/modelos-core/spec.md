# Spec Delta: dominio/modelos-core

## ADDED Requirements

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
