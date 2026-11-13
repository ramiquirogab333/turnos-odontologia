# Spec Delta: plataforma/trabajos-programados

## MODIFIED Requirements

### Requirement: Redis y worker levantados por Docker Compose con healthcheck
El entorno SHALL incluir un servicio Redis y un servicio worker en Docker Compose, cada uno con healthcheck. El worker y el backend SHALL arrancar solo cuando PostgreSQL y Redis estén sanos (R18) y SHALL leer su configuración de variables de entorno, sin secretos en el código ni archivos `.env` versionados (R17, R20). El backend usa Redis solo para los contadores de límite de solicitudes.

#### Scenario: Levantar el entorno (Happy Path)
- **WHEN** se ejecuta `docker compose up -d --wait postgres redis worker backend`
- **THEN** los cuatro servicios quedan `healthy` y el worker registra en el log los trabajos que tiene programados

#### Scenario: Redis caído al arrancar (Error de Negocio)
- **GIVEN** que el servicio Redis no está sano
- **WHEN** se intenta levantar el worker o el backend
- **THEN** no arrancan hasta que Redis esté sano y Compose informa la dependencia insatisfecha

#### Scenario: Backend sin Redis (Caso de Borde)
- **GIVEN** el backend ya levantado y Redis detenido después
- **WHEN** se usan la reserva, la gestión y el panel
- **THEN** responden con normalidad, sin aplicar los límites de solicitudes y registrando un aviso sin datos personales (capacidad `plataforma/limite-de-solicitudes`)

## ADDED Requirements

### Requirement: El worker purga las sesiones del panel vencidas
El worker SHALL ejecutar el trabajo `purga_sesiones` cada `PURGA_SESIONES_INTERVALO_SEGUNDOS` (3600 por defecto), borrando en lotes las sesiones del panel cuyo vencimiento absoluto pasó hace más de `PURGA_SESIONES_MARGEN_MINUTOS` (60 por defecto). El trabajo SHALL poder deshabilitarse por variable de entorno, SHALL ser idempotente y SHALL registrar solo la cantidad borrada, sin datos personales.

#### Scenario: Purga periódica (Happy Path)
- **GIVEN** 3 sesiones vencidas hace más de 2 horas y 2 sesiones vigentes
- **WHEN** corre `purga_sesiones`
- **THEN** se borran las 3 vencidas, quedan las 2 vigentes y el log dice "purga de sesiones: 3"

#### Scenario: Margen inválido (Error de Negocio)
- **GIVEN** `PURGA_SESIONES_MARGEN_MINUTOS=-5`
- **WHEN** arranca el worker
- **THEN** el worker no arranca e informa la variable inválida

#### Scenario: Dos workers a la vez (Caso de Borde)
- **GIVEN** 1500 sesiones vencidas y dos workers que corren la purga al mismo tiempo, con lotes de 500
- **WHEN** terminan los dos
- **THEN** no queda ninguna sesión vencida fuera del margen, ninguna vigente se borró y ningún worker falló
