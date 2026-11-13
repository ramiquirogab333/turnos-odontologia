# Spec Delta: integraciones/google-calendar

## ADDED Requirements

### Requirement: Iniciar la conexión con Google queda auditado
Cada inicio de conexión aceptado (`POST /api/panel/google-calendar/conexion/iniciar`) SHALL dejar un registro de auditoría `inicio_conexion_gcal` con el usuario, la IP y la profesional, sin la URL de consentimiento, el `state` ni el verificador PKCE (RN-GL-01, C-13 O10).

#### Scenario: La profesional inicia la conexión (Happy Path)
- **GIVEN** `dra.ficticia@turnos.test` vinculada a la profesional "Dra. Ana Ficticia" sin conexión activa
- **WHEN** pide iniciar la conexión
- **THEN** recibe la URL de consentimiento y existe un registro `inicio_conexion_gcal` con su usuario y la profesional, que no contiene la URL ni el `state`

#### Scenario: Conexión ya activa (Error de Negocio)
- **GIVEN** la misma profesional con una conexión activa
- **WHEN** pide iniciar otra
- **THEN** recibe 409 `conexion_activa` y no queda ningún registro `inicio_conexion_gcal`

#### Scenario: Google no configurado (Caso de Borde)
- **GIVEN** el entorno sin credenciales de Google
- **WHEN** la profesional pide iniciar la conexión
- **THEN** recibe 503 `gcal_no_configurado` y no queda ningún registro
