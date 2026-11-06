# Proposal: c-06-sena-pagos-turno

## Why
Hoy la reserva pública de C-05 crea el turno directamente en `reservado` y bloquea la agenda sin ningún compromiso del paciente, así que un turno abandonado ocupa un horario que otro podría usar y el ausentismo no tiene costo. La restricción del usuario (GAP del header de `CHANGES.md`, RN-SN-01..03) pide que el turno quede en `en_espera` sin bloquear agenda hasta que se acredite una seña configurable, y que la seña no se devuelva ante un ausente (R8, R9). C-05 ya está archivado y dejó preparado ese punto de extensión, por eso C-06 va ahora.

## What Changes
- **BREAKING (contrato público):** `POST /api/public/turnos` deja de crear el turno en `reservado`: lo crea en `en_espera`, con un vencimiento (`en_espera_vence_en`), y la respuesta agrega los datos de la seña a pagar. Un `en_espera` no bloquea agenda ni aparece como ocupado en `GET /api/public/disponibilidad` (R8).
- **Iniciar el pago de la seña** con `POST /api/public/turnos/{id}/sena`, autenticado con el código de gestión del turno: con Mercado Pago crea una preferencia de pago y devuelve la URL de checkout; con transferencia registra un pago pendiente y devuelve el alias, el CBU y un código de referencia del turno para poner en el concepto. Recepción o admin acreditan la transferencia a mano (RN-SN-08). Antes de cobrar vuelve a comprobar que el horario siga libre.
- **Consultar el estado de la seña** con `GET /api/public/turnos/{id}/sena`, para la pantalla que espera la acreditación.
- **Webhook** `POST /api/webhooks/mercadopago`: verifica la firma (`x-signature`, HMAC-SHA256), es idempotente por referencia externa y por id de pago, consulta el pago real al gateway y, si está aprobado, acredita la seña y pasa el turno a `reservado`. El anti-solape (RN-TU-03) se vuelve a comprobar al acreditar.
- **Acreditación manual de transferencias** por recepción/admin (`POST /api/admin/pagos-sena/{id}/acreditar`), con auditoría (RN-GL-01).
- **Expiración de `en_espera`:** un barrido periódico local (C-09 lo pasará a la base de jobs) cancela las pre-reservas vencidas y marca sus pagos pendientes como `vencido`.
- **Máquina de estados del turno y de la seña:** `en_espera → reservado → confirmado / cancelado / ausente / atendido`. Marcar `ausente` deja la seña como `no_reembolsado` (R9). Cancelar con 24 h o más de anticipación la deja `a_reembolsar`, con devolución manual (RN-SN-04); la regla queda en la máquina de estados y C-07 la expone.
- **Configuración de la seña para el admin** (`GET/PUT /api/admin/config/sena`): `sena_porcentaje`, medios habilitados (solo Mercado Pago y transferencia, RN-PG-01), texto de la política de reembolso, vencimiento de la pre-reserva y datos de transferencia.
- **Migración Alembic `006_sena_pagos` reversible:** tablas `pago_sena` y `configuracion_sena`, y la columna `turno.en_espera_vence_en`. `CHANGES.md` habla de la "migración 005", pero ese número ya lo usa C-05.
- **Puerto `PasarelaPagos`** con un adaptador real de Mercado Pago (HTTP asíncrono) y uno falso para tests, CI y E2E. Los secretos (`MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET`) solo llegan por variables de entorno (R17).
- **Frontend `frontend-paciente/`:** después de reservar, la confirmación se reemplaza por la pantalla "Pagá la seña para confirmar tu turno" a 360px (R3), con el retorno desde Mercado Pago y la espera de la acreditación.

## Capabilities

### New Capabilities
- `pagos/sena-turno`: seña del turno de punta a punta: iniciarla, consultarla, acreditarla por webhook de Mercado Pago o a mano por transferencia, el vencimiento de la pre-reserva, la retención ante un ausente y la configuración del admin.

### Modified Capabilities
- `turnos/reserva-publica`: la reserva pública crea el turno en `en_espera` y no bloquea; la consulta de disponibilidad ignora las pre-reservas `en_espera`.
- `turnos/creacion-sin-solape`: el requisito "El turno creado bloquea el slot; estados no bloqueantes nunca colisionan" se actualiza, porque `en_espera` ya existe. `POST /api/turnos` interno sigue creando turnos bloqueantes y el paso de `en_espera` a `reservado` queda alcanzado por los EXCLUDE.

## Impact
- **Backend:** módulo nuevo `app/pagos/` (modelos, esquemas Pydantic, servicio, máquina de estados, puerto y adaptadores, router público, webhook y router admin); cambios en `app/public/service.py` (estado inicial y respuesta); `app/shared/settings.py` (variables de Mercado Pago y de la seña); `app/main.py` (routers y barrido en el `lifespan`).
- **Base de datos:** migración `006_sena_pagos` (R4, R6, R14). Los EXCLUDE parciales de C-01 no cambian.
- **API:** el contrato de `POST /api/public/turnos` cambia (`estado: "en_espera"` y el bloque `sena`), y hay cinco endpoints nuevos.
- **Tests existentes que se rompen a propósito:** los de backend (`test_public_endpoints_integration.py`) y los E2E (`e2e/reserva.spec.ts`) que esperan `reservado` o un 201/409 en la reserva concurrente. Se reescriben en este change.
- **Infra:** variables nuevas en `docker-compose.yml` y CI (`MP_GATEWAY=fake` en test y E2E). No se agrega ninguna dependencia: el adaptador de Mercado Pago usa `httpx`, que ya está en el proyecto.
- **Fuera de alcance:** recordatorio de WhatsApp (C-09), evento de Google Calendar (C-10), cancelación y reprogramación del paciente (C-07), UI del panel para la caja (C-08 y C-12) y reembolsos automáticos.
