# Spec Delta: plataforma/trabajos-programados

## ADDED Requirements

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
