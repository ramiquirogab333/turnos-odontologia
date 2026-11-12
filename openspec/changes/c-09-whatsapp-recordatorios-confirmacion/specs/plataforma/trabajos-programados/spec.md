# Spec Delta: plataforma/trabajos-programados

## Purpose

Base común para ejecutar trabajos periódicos fuera de la atención de solicitudes (recordatorios, barrido de pre-reservas vencidas y, más adelante, la sincronía con Google Calendar), sobre Redis y un worker levantados por Docker Compose con healthchecks (R16, R18).

## ADDED Requirements

### Requirement: Redis y worker levantados por Docker Compose con healthcheck
El entorno SHALL incluir un servicio Redis y un servicio worker en Docker Compose, cada uno con healthcheck. El worker SHALL arrancar solo cuando PostgreSQL y Redis estén sanos (R18) y SHALL leer su configuración de variables de entorno, sin secretos en el código ni archivos `.env` versionados (R17, R20).

#### Scenario: Levantar el entorno (Happy Path)
- **WHEN** se ejecuta `docker compose up -d --wait postgres redis worker`
- **THEN** los tres servicios quedan `healthy` y el worker registra en el log los trabajos que tiene programados

#### Scenario: Redis caído al arrancar (Error de Negocio)
- **GIVEN** que el servicio Redis no está sano
- **WHEN** se intenta levantar el worker
- **THEN** el worker no arranca hasta que Redis esté sano y Compose informa la dependencia insatisfecha

#### Scenario: Backend sin Redis (Caso de Borde)
- **GIVEN** que solo están levantados PostgreSQL y el backend
- **WHEN** se usan la reserva, la gestión y el panel
- **THEN** responden con normalidad: la API no necesita Redis para atender solicitudes, solo el worker lo usa

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
