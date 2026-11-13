# Spec Delta: turnos/creacion-sin-solape

## ADDED Requirements

### Requirement: El alta interna queda auditada
Cada turno creado con `POST /api/turnos` SHALL dejar, en la misma transacción, un registro de auditoría `alta_turno_interna` con el usuario, la IP, el id del turno, su profesional, sillón, tratamiento, inicio, fin y estado (RN-GL-01, C-13 O10). Un alta rechazada (solape, validación, permiso) no SHALL dejar registro.

#### Scenario: Alta interna auditada (Happy Path)
- **GIVEN** la usuaria `recepcion@turnos.test` y un horario libre de la profesional "Dra. Ana Ficticia"
- **WHEN** crea el turno con `POST /api/turnos`
- **THEN** responde 201 y existe un registro `alta_turno_interna` con su usuario, la IP del pedido y el id del turno

#### Scenario: Alta con solape (Error de Negocio)
- **GIVEN** un turno `reservado` de la misma profesional en ese horario
- **WHEN** recepción intenta crear otro superpuesto
- **THEN** responde 409 y no queda ningún registro `alta_turno_interna`

#### Scenario: Dos altas simultáneas por el mismo horario (Caso de Borde)
- **WHEN** dos pedidos crean a la vez un turno en el mismo horario y sillón
- **THEN** uno responde 201 y el otro 409, y hay exactamente un registro `alta_turno_interna`
