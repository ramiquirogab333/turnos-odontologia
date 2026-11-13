# plataforma/trabajos-programados Specification

## Purpose
Base común para ejecutar trabajos periódicos fuera de la atención de solicitudes (recordatorios, barrido de pre-reservas vencidas y, más adelante, la sincronía con Google Calendar), sobre Redis y un worker levantados por Docker Compose con healthchecks (R16, R18).

## Requirements

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

### Requirement: Trabajos periódicos con intervalo configurable
El worker SHALL ejecutar periódicamente el trabajo de recordatorios (cada `RECORDATORIOS_INTERVALO_SEGUNDOS`, 300 por defecto) y el barrido de pre-reservas vencidas (cada `SENA_BARRIDO_SEGUNDOS`, 60 por defecto). Cada trabajo SHALL poder deshabilitarse por variable de entorno.

#### Scenario: Intervalos por defecto (Happy Path)
- **GIVEN** el worker sin variables de intervalo definidas
- **WHEN** pasan 10 minutos
- **THEN** el trabajo de recordatorios corrió 2 veces y el barrido 10 veces, con una tolerancia de un ciclo

#### Scenario: Intervalo inválido (Error de Negocio)
- **GIVEN** que `RECORDATORIOS_INTERVALO_SEGUNDOS` vale "0" o "abc"
- **WHEN** arranca el worker
- **THEN** el worker no arranca e informa la variable inválida sin mostrar ningún secreto

#### Scenario: Intervalo corto para pruebas E2E (Caso de Borde)
- **GIVEN** que `RECORDATORIOS_INTERVALO_SEGUNDOS` vale 3
- **WHEN** se acredita la seña de un turno que empieza en 30 horas
- **THEN** su recordatorio aparece en a lo sumo 6 segundos

### Requirement: Trabajos idempotentes ante ejecuciones concurrentes
Cada trabajo periódico SHALL poder correr dos veces a la vez, en uno o en varios workers, sin duplicar efectos: el resultado final SHALL ser el mismo que con una sola ejecución.

#### Scenario: Barrido simultáneo (Happy Path)
- **GIVEN** que el turno 140 está `en_espera` y venció
- **WHEN** dos ejecuciones del barrido corren a la vez
- **THEN** el turno 140 queda `cancelado` una sola vez, con un solo registro de auditoría de vencimiento

#### Scenario: Ejecución solapada con la anterior (Error de Negocio)
- **GIVEN** que un ciclo de recordatorios todavía no terminó cuando vence el intervalo
- **WHEN** arranca el ciclo siguiente
- **THEN** no se crean recordatorios duplicados

#### Scenario: Acreditación durante el barrido (Caso de Borde)
- **GIVEN** que la seña del turno 141 se está acreditando en el mismo instante en que corre el barrido y su pre-reserva acaba de vencer
- **WHEN** ambos terminan
- **THEN** el turno 141 queda en un único estado coherente (`reservado` o `cancelado` con su pago `a_reembolsar`, según quien tomó el lock primero, como define C-06) y nunca en ambos

### Requirement: Un ciclo fallido no detiene al worker
Si un ciclo de un trabajo falla (por ejemplo, la base no responde), el worker SHALL registrar el error sin datos personales y SHALL volver a ejecutar el trabajo en el siguiente intervalo, sin detenerse ni afectar a los otros trabajos.

#### Scenario: La base vuelve (Happy Path)
- **GIVEN** que PostgreSQL estuvo caído durante un ciclo de recordatorios
- **WHEN** vuelve y llega el siguiente intervalo
- **THEN** el trabajo corre con normalidad y genera los recordatorios que faltaban

#### Scenario: Error inesperado en un trabajo (Error de Negocio)
- **GIVEN** que el trabajo de recordatorios lanza un error inesperado
- **WHEN** termina el ciclo
- **THEN** el error queda en el log, el worker sigue sano y el barrido de pre-reservas sigue corriendo en su intervalo

#### Scenario: Apagado durante un ciclo (Caso de Borde)
- **GIVEN** que el worker recibe la señal de apagado mientras corre un ciclo
- **WHEN** se detiene
- **THEN** la transacción en curso se confirma completa o se revierte completa, sin recordatorios a medio guardar

### Requirement: El barrido de pre-reservas vencidas corre en el worker
El barrido de pre-reservas vencidas (RN-SN-07) SHALL ejecutarse en el worker con la misma regla que define `pagos/sena-turno`. La API no SHALL correr el barrido salvo que se habilite explícitamente para desarrollo o pruebas sin worker.

#### Scenario: Barrido desde el worker (Happy Path)
- **GIVEN** que el turno 142 está `en_espera`, vence a las 10:30 y el worker está corriendo
- **WHEN** el barrido corre a las 10:31
- **THEN** el turno 142 queda `cancelado` y su pago pendiente `vencido`, con auditoría

#### Scenario: API sin bandera (Error de Negocio)
- **GIVEN** que el backend arranca sin habilitar el barrido en la API
- **WHEN** pasa un minuto
- **THEN** la API no ejecutó ningún barrido; solo el worker lo hace

#### Scenario: Barrido en la API para pruebas (Caso de Borde)
- **GIVEN** que el backend arranca con el barrido de la API habilitado y no hay worker
- **WHEN** vence una pre-reserva
- **THEN** la API la cancela con la misma regla y el mismo registro de auditoría que el worker

### Requirement: El worker corre la sincronización con Google Calendar
El worker SHALL ejecutar el trabajo de sincronización con Google Calendar cada `GCAL_SYNC_INTERVALO_SEGUNDOS` (60 por defecto, mayor que cero). SHALL poder deshabilitarse con `GCAL_SYNC_HABILITADO=false` y SHALL no registrarse si faltan `GCAL_CLIENT_ID` o `GCAL_CLIENT_SECRET`, sin impedir que corran los demás trabajos.

#### Scenario: Trabajo registrado con su intervalo (Happy Path)
- **GIVEN** el worker con las credenciales de Google por entorno y sin variable de intervalo
- **WHEN** arranca
- **THEN** registra en el log el trabajo `gcal_sync` cada 60 s junto a los de recordatorios y barrido

#### Scenario: Faltan las credenciales de Google (Error de Negocio)
- **GIVEN** que `GCAL_CLIENT_SECRET` no está definida
- **WHEN** arranca el worker
- **THEN** el worker arranca sin el trabajo `gcal_sync`, deja un aviso en el log sin mostrar ningún secreto, y recordatorios y barrido corren normalmente

#### Scenario: Intervalo corto para E2E (Caso de Borde)
- **GIVEN** `GCAL_SYNC_INTERVALO_SEGUNDOS=3`
- **WHEN** se acredita la seña de un turno de una profesional conectada
- **THEN** su evento existe en el calendario dentro de los 6 segundos

### Requirement: La sincronización de una conexión no se pisa entre workers
Cada ciclo de `gcal_sync` SHALL procesar cada conexión a lo sumo una vez a la vez: si otro worker ya la está procesando, SHALL saltearla en ese ciclo. Un error en una conexión SHALL no impedir procesar las demás.

#### Scenario: Dos workers, una conexión (Happy Path)
- **GIVEN** dos workers que arrancan el ciclo al mismo tiempo con la conexión de la profesional 7
- **WHEN** ambos intentan procesarla
- **THEN** uno la procesa y el otro la saltea sin error

#### Scenario: Una conexión falla (Error de Negocio)
- **GIVEN** que la conexión de la profesional 7 lanza un error inesperado
- **WHEN** corre el ciclo
- **THEN** la conexión de la profesional 8 se sincroniza igual y el error de la 7 queda en el log con el nombre del trabajo y la clase del error, sin datos personales

#### Scenario: Ciclo más largo que el intervalo (Caso de Borde)
- **GIVEN** un ciclo que tarda más que `GCAL_SYNC_INTERVALO_SEGUNDOS`
- **WHEN** arranca el ciclo siguiente
- **THEN** las conexiones todavía en proceso se saltean y ningún evento se crea dos veces

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
