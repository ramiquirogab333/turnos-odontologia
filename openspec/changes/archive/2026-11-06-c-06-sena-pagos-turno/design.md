# Design: c-06-sena-pagos-turno

## Context
La motivación está en `proposal.md` (Why) y los requisitos en `specs/pagos/sena-turno/spec.md` y en los deltas de `turnos/*`. Esto es lo que se verificó en el código (no en `CHANGES.md`) y condiciona el diseño:

- **Última migración: `005_reserva_publica`** (código de gestión y contacto en `turno`). La nueva es la **`006_sena_pagos`**, con `down_revision = "005_reserva_publica"`. `CHANGES.md` dice "migración 005", pero está desactualizado.
- **El CHECK de `turno.estado` ya admite `en_espera`** (migración 001 y `ck_turno_estado` en `app/turnos/models.py`). No hace falta tocarlo.
- **Los EXCLUDE ya son parciales**: `turno_no_solape_profesional` y `turno_no_solape_sillon`, con `WHERE (estado IN ('reservado','confirmado'))` (migración 001). Un `en_espera` no colisiona en la base y el `UPDATE en_espera → reservado` sí queda alcanzado por el EXCLUDE. **No se modifican.**
- **`ESTADOS_BLOQUEANTES = ("reservado", "confirmado")`** en `app/turnos/service.py` alimenta `_cargar_bloqueos` de `app/public/service.py`, así que la disponibilidad ya ignora `en_espera` sin cambios.
- **La reserva pública** (`reservar_turno_publico`) hoy crea el turno con `estado="reservado"`, pre-chequea solapes después de `pg_advisory_xact_lock(LOCK_RESERVAS=5_005_001)` y mapea 23P01/40P01 a 409. **No crea `Paciente`**: guarda `contacto_nombre` y `contacto_telefono` en `turno` y `paciente_id=NULL`. C-06 lo mantiene igual.
- **No hay Redis ni workers** en `docker-compose.yml`: la base de jobs llega con C-09.
- **El frontend no tiene router.** Es un wizard (`Reserva.tsx`) que termina en `Confirmacion.tsx` ("Turno reservado").
- **Los E2E corren contra el backend real** en Docker, sin mocks (`playwright.config.ts`, 360x800). La pasarela no se puede mockear desde el navegador: tiene que ser falsa del lado del backend.

## Goals / Non-Goals

**Goals:**
- Que el único camino de `en_espera` a `reservado` sea la acreditación, con el anti-solape que garantiza la base de datos.
- Integrar Mercado Pago detrás de un puerto, para que ni los tests, ni el CI, ni los E2E hagan llamadas reales.
- Que el webhook sea seguro (firma, tolerancia de timestamp) e idempotente aunque lleguen notificaciones concurrentes.
- Mantener el contrato y la estructura de C-05: código de gestión, contacto en el turno, sin `Paciente`.

**Non-Goals:**
- Reembolsos automáticos. `a_reembolsar` es un estado que la clínica resuelve a mano; la UI de caja es de C-12.
- Recordatorio por WhatsApp y evento en Google Calendar al acreditar (Flujo 1, paso 5): son de C-09 y C-10. C-06 solo deja la auditoría `origen: "acreditacion_sena"` como punto de enganche.
- Cancelación y reprogramación por el paciente con la ventana de 24 h (C-07). C-06 solo define la máquina de estados y la política de seña que C-07 va a usar.
- Endpoints del panel para marcar ausente o atendido (C-08). C-06 entrega el servicio de transición, probado.
- Webhooks `merchant_order`, contracargos y pagos parciales.

## Decisions

### D1. Módulo `app/pagos/` con puerto `PasarelaPagos`
- **Decisión:** módulo nuevo `backend/src/app/pagos/` con:
  - `models.py`: `PagoSena` y `ConfiguracionSena`.
  - `schemas.py`.
  - `estados.py`: máquina de estados pura.
  - `calculo.py`: monto y vencimiento, funciones puras.
  - `pasarela.py`: el `Protocol` `PasarelaPagos` con `crear_preferencia(...)`, `obtener_pago(payment_id)` y `verificar_firma(...)`.
  - `mercadopago.py`: adaptador real con `httpx.AsyncClient`, timeout de 10 s y `X-Idempotency-Key = referencia_externa`.
  - `fake.py`: adaptador falso.
  - `service.py`, `router_public.py`, `router_webhook.py`, `router_admin.py` y `barrido.py`.

  La pasarela se elige con `MP_GATEWAY ∈ {mercadopago, fake}` y se inyecta con `Depends(get_pasarela)`, que los tests sobreescriben con `app.dependency_overrides`.
- **Adaptador falso:** es determinístico y no tiene estado, porque el backend en Docker y el runner de Playwright no comparten memoria:
  - `crear_preferencia` devuelve `checkout_url = {PUBLIC_BASE_URL}/?pago=retorno&turno={id}`.
  - `obtener_pago("fake-<status>-<referencia_externa>")` decodifica el estado y la referencia del propio id.

  La firma la verifica el mismo código HMAC que en producción, con `MP_WEBHOOK_SECRET` sintético: el E2E firma igual que Mercado Pago. Si `APP_ENV=production` y `MP_GATEWAY=fake`, `Settings` falla al arrancar.
- **Alternativas descartadas:** el SDK oficial `mercadopago`, porque es síncrono y bloquearía el event loop (R16) o habría que envolverlo en hilos, y suma una dependencia. Endpoints `/api/dev/*` para simular pagos, porque son una superficie de ataque si se filtran a producción.

### D2. Modelo de datos (migración `006_sena_pagos`)
Sigue `postgresql-table-design`: PK identity, `TEXT` + `CHECK`, `NUMERIC`, `TIMESTAMPTZ` y un índice por cada FK (R4, R6). Todo con `op.execute` dentro de la migración, sin SQL crudo en la aplicación (R14).

```sql
ALTER TABLE turno ADD COLUMN en_espera_vence_en TIMESTAMPTZ NULL;
ALTER TABLE turno ADD CONSTRAINT ck_turno_en_espera_vence
  CHECK (estado <> 'en_espera' OR en_espera_vence_en IS NOT NULL);
CREATE INDEX ix_turno_en_espera_vence ON turno (en_espera_vence_en) WHERE estado = 'en_espera';

CREATE TABLE configuracion_sena (
  id                                SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- singleton
  sena_porcentaje                   NUMERIC(5,2) NOT NULL CHECK (sena_porcentaje > 0 AND sena_porcentaje <= 100),
  medios_habilitados                TEXT[] NOT NULL CHECK (cardinality(medios_habilitados) >= 1
                                     AND medios_habilitados <@ ARRAY['mercadopago','transferencia']),
  texto_politica_reembolso          TEXT NOT NULL CHECK (LENGTH(texto_politica_reembolso) BETWEEN 1 AND 500),
  expiracion_mp_minutos             INTEGER NOT NULL CHECK (expiracion_mp_minutos BETWEEN 5 AND 1440),
  expiracion_transferencia_minutos  INTEGER NOT NULL CHECK (expiracion_transferencia_minutos BETWEEN 5 AND 4320),
  transferencia_alias               TEXT NULL CHECK (transferencia_alias IS NULL OR LENGTH(transferencia_alias) BETWEEN 6 AND 40),
  transferencia_cbu                 TEXT NULL CHECK (transferencia_cbu IS NULL OR transferencia_cbu ~ '^[0-9]{22}$'),
  transferencia_titular             TEXT NULL CHECK (transferencia_titular IS NULL OR LENGTH(transferencia_titular) BETWEEN 1 AND 120),
  created_at / updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO configuracion_sena (...) VALUES (1, 30.00, '{mercadopago,transferencia}',
  'Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve.',
  30, 1440, NULL, NULL, NULL);

CREATE TABLE pago_sena (
  id                         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  turno_id                   BIGINT NOT NULL REFERENCES turno (id) ON DELETE RESTRICT,
  medio                      TEXT NOT NULL CHECK (medio IN ('mercadopago','transferencia')),
  monto                      NUMERIC(10,2) NOT NULL CHECK (monto > 0),
  porcentaje_aplicado        NUMERIC(5,2) NOT NULL CHECK (porcentaje_aplicado > 0 AND porcentaje_aplicado <= 100),
  estado                     TEXT NOT NULL DEFAULT 'pendiente'
                             CHECK (estado IN ('pendiente','acreditado','vencido','no_reembolsado','a_reembolsar')),
  referencia_externa         TEXT NOT NULL CHECK (LENGTH(referencia_externa) BETWEEN 8 AND 64),
  mp_payment_id              TEXT NULL CHECK (mp_payment_id IS NULL OR LENGTH(mp_payment_id) <= 64),
  checkout_url               TEXT NULL CHECK (checkout_url IS NULL OR LENGTH(checkout_url) <= 2048),
  vence_en                   TIMESTAMPTZ NOT NULL,
  acreditado_en              TIMESTAMPTZ NULL,
  acreditado_por_usuario_id  BIGINT NULL REFERENCES usuario (id) ON DELETE RESTRICT,
  created_at / updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_pago_sena_referencia UNIQUE (referencia_externa),
  CONSTRAINT uq_pago_sena_mp_payment UNIQUE (mp_payment_id),
  CONSTRAINT ck_pago_sena_acreditado CHECK (estado NOT IN ('acreditado','no_reembolsado') OR acreditado_en IS NOT NULL)
);
CREATE INDEX ix_pago_sena_turno ON pago_sena (turno_id);                      -- R6
CREATE INDEX ix_pago_sena_acreditado_por ON pago_sena (acreditado_por_usuario_id);  -- R6
CREATE UNIQUE INDEX uq_pago_sena_activo ON pago_sena (turno_id) WHERE estado IN ('pendiente','acreditado');
CREATE INDEX ix_pago_sena_pendiente_vence ON pago_sena (vence_en) WHERE estado = 'pendiente';
```

- El `downgrade` borra, en orden inverso, los índices, `pago_sena`, `configuracion_sena`, el CHECK y la columna de `turno`. Antes de borrar la columna pasa los `en_espera` a `cancelado`, porque si no el CHECK de 001 los dejaría válidos pero sin vencimiento. El `downgrade` es destructivo para `pago_sena` y se documenta como tal.
- Los turnos existentes no se tocan: ninguno está `en_espera`, así que el CHECK nuevo vale para todos.
- `uq_pago_sena_activo` garantiza en la base un solo pago activo por turno.
- **Alternativas descartadas:**
  - Configuración en variables de entorno: el admin no podría editarla y `CHANGES.md` pide que sea configurable por él.
  - Un `ENUM` de Postgres para `estado`: los valores pueden cambiar y `TEXT` + `CHECK` es la convención del repo.
  - Reusar la tabla `Pago`: la KB la ata a `Presupuesto`.

### D3. Cambios en la reserva pública (C-05 → C-06)
`reservar_turno_publico` mantiene la validación, el `pg_advisory_xact_lock` y el pre-chequeo de solape contra los bloqueantes (sigue habiendo 409 si el horario ya está `reservado` o `confirmado`). Los cambios son:
1. Calcula el monto con `calculo.monto_sena(precio_base, porcentaje)`, en `Decimal` con `quantize(Decimal("0.01"), ROUND_HALF_UP)`.
2. Si el monto es mayor que 0, inserta el turno con `estado="en_espera"` y `en_espera_vence_en = min(now + expiracion_mp_minutos, inicio)`. Si es 0, lo inserta `reservado`, como hoy (RN-SN-06).
3. La respuesta agrega `sena: {monto, vence_en, medios_habilitados, texto_politica_reembolso} | null`. `estado` pasa a ser `"en_espera" | "reservado"`.
4. La auditoría conserva `origen: "reserva_publica"` y no guarda PII.

El sillón asignado al crear es tentativo: se reevalúa al acreditar (D5). El alta interna `POST /api/turnos` de C-01 no cambia (nace `reservado`).

### D4. Inicio de la seña (`POST /api/public/turnos/{id}/sena`)
La transacción hace, en orden:
1. Autentica con `X-Codigo-Gestion`, comparado en tiempo constante (`hmac.compare_digest`). Si no coincide, 404.
2. `SELECT turno ... FOR UPDATE`. Si no está `en_espera` o ya venció, 409.
3. Valida que el medio esté habilitado (422).
4. Toma el `pg_advisory_xact_lock(LOCK_RESERVAS)` y re-chequea el solape contra los bloqueantes (409 con alternativas, reusando `_alternativas`).
5. Busca un pago activo: si es del mismo medio, lo devuelve (200, idempotente); si es de otro medio, lo pasa a `vencido`.
6. Genera `referencia_externa`: con Mercado Pago, `uuid4().hex`; con transferencia, un código corto para el concepto bancario, `SENA-{turno_id}-{6 hex en mayúsculas}` (20 caracteres o menos, único por el UNIQUE de la tabla; se reintenta si colisiona). Se devuelve como `referencia_concepto` (RN-SN-08). Después calcula `vence_en`: para Mercado Pago es el vencimiento del turno; para transferencia, `min(now + expiracion_transferencia_minutos, inicio)`, y extiende `turno.en_espera_vence_en` a ese valor.
7. Con Mercado Pago llama a `pasarela.crear_preferencia(...)` (external_reference, monto, `expiration_date_to = vence_en`, `notification_url`, `back_urls`) **antes** del commit. Si la pasarela falla, rollback y 502 con un mensaje claro: no queda un pago pendiente sin preferencia.
8. Commit y 201.

El `GET` hace la misma autenticación y es solo lectura.

### D5. Acreditación (servicio único para el webhook y para el admin)
`acreditar_pago(session, pago_id, *, mp_payment_id=None, usuario_id=None)`:
1. Toma `pg_advisory_xact_lock(LOCK_RESERVAS)`, que serializa con las reservas y con otras acreditaciones (evita el deadlock 40P01 documentado en C-05).
2. `SELECT pago ... FOR UPDATE` y `SELECT turno ... FOR UPDATE`.
3. Idempotencia: si el pago ya está `acreditado` (o `a_reembolsar`) con el mismo `mp_payment_id`, devuelve un no-op.
4. Si el turno no está `en_espera` o ya venció, el pago pasa a `a_reembolsar` (RN-SN-05), con auditoría, y termina.
5. Re-chequea el anti-solape (RN-TU-03): profesional libre y `_sillon_libre(...)`, que prefiere el sillón tentativo y si no reasigna. Si el profesional está ocupado o no hay sillón, el turno pasa a `cancelado` y el pago a `a_reembolsar`.
6. Si está libre: el pago pasa a `acreditado` (`acreditado_en`, `mp_payment_id`, `acreditado_por_usuario_id`), el turno a `reservado` (`en_espera_vence_en = NULL`, posible nuevo `sillon_id`) y se escribe la auditoría (`origen: "acreditacion_sena"`, medio y sillón anterior/nuevo).
7. `flush`. Si salta 23P01 (red de seguridad, R5), hace rollback y repite el camino del paso 5 en una transacción nueva. Nunca devuelve 500.

**Por qué un advisory lock y no solo el EXCLUDE:** dos acreditaciones que compiten por el mismo rango violan a la vez el EXCLUDE de profesional y el de sillón, y Postgres aborta una con deadlock en lugar de 23P01 (lo encontró C-05). El lock global de reservas es de baja contención en una clínica y ya está probado.

### D6. Webhook de Mercado Pago
- Ruta `POST /api/webhooks/mercadopago`, sin JWT. Lee `x-signature` (`ts=…,v1=…`), `x-request-id` y `data.id` (del query o del body).
- Arma el manifest `id:{data.id};request-id:{x-request-id};ts:{ts};` y lo firma con HMAC-SHA256 y `MP_WEBHOOK_SECRET`. Compara con `hmac.compare_digest`; `|now − ts|` tiene que ser menor o igual que `MP_WEBHOOK_TOLERANCIA_SEGUNDOS` (300). Si no, 401.
- Si `type != "payment"`, 200 e ignora.
- Llama a `pasarela.obtener_pago(data.id)`. Nunca confía en el estado que trae el body.
- Si está `approved` y la `external_reference` existe, llama a `acreditar_pago`. Si no, 200 y log estructurado sin PII (solo la referencia y el estado).
- Si la pasarela falla al consultar, responde 503 para que Mercado Pago reintente; la idempotencia de D5 cubre el reintento.

### D7. Máquina de estados (`app/pagos/estados.py`, pura)
- `TRANSICIONES_TURNO = {en_espera: {reservado, cancelado}, reservado: {confirmado, cancelado, ausente, atendido}, confirmado: {cancelado, ausente, atendido}}`.
- `transicionar(actual, destino) -> str` lanza `TransicionInvalidaError`, que se mapea a 409 `transicion_invalida`.
- Efectos sobre la seña:
  - Si el turno pasa a `ausente` con pago `acreditado`, el pago pasa a `no_reembolsado` (R9, RN-SN-02).
  - Si pasa a `cancelado` desde `reservado`/`confirmado` con pago `acreditado`, el pago pasa a `a_reembolsar` (RN-SN-04). La función recibe `ahora` y lanza `CancelacionFueraDePlazoError` (409 `fuera_de_plazo`) si faltan menos de 24 h para el inicio (RN-TU-01); exactamente 24 h se acepta.
  - Si pasa de `en_espera` a `cancelado`, el pago `pendiente` pasa a `vencido`.
- C-06 expone `cambiar_estado_turno(session, turno_id, destino, usuario_id)` como servicio, probado. Los endpoints del panel que lo usan son de C-07 y C-08.

### D8. Vencimiento (barrido local, que C-09 va a consolidar)
- `expirar_pre_reservas(session, ahora) -> int` (servicio idempotente) hace un `UPDATE` vía ORM de los turnos `en_espera` con `en_espera_vence_en <= ahora` a `cancelado`, y de sus pagos `pendiente` a `vencido`, con una auditoría por turno.
- Se ejecuta en una tarea `asyncio` del `lifespan` de FastAPI cada `SENA_BARRIDO_SEGUNDOS` (60). Se desactiva con `SENA_BARRIDO_HABILITADO=false` en los tests de integración, que llaman al servicio con un `ahora` inyectado. Es I/O asíncrono liviano, no bloquea el event loop (R16).
- **Defensa en profundidad:** el inicio de seña y la acreditación tratan como vencido un `en_espera` con el plazo cumplido aunque el barrido no haya corrido.
- **Alternativa descartada:** Redis + worker ahora. Adelantaría C-09 y sumaría un servicio a Compose por un único job; C-09 va a mover `expirar_pre_reservas` a su scheduler sin cambiar el servicio.

### D9. Configuración y secretos (R17)
- Nuevas variables en `Settings`:
  - `MP_GATEWAY` (default `fake`).
  - `MP_ACCESS_TOKEN` y `MP_WEBHOOK_SECRET`: `SecretStr`, obligatorias si `MP_GATEWAY=mercadopago`.
  - `MP_API_BASE_URL` (default `https://api.mercadopago.com`).
  - `MP_WEBHOOK_TOLERANCIA_SEGUNDOS`.
  - `PUBLIC_BASE_URL` (back_urls) y `API_PUBLIC_BASE_URL` (notification_url).
  - `APP_ENV`.
  - `SENA_BARRIDO_SEGUNDOS` y `SENA_BARRIDO_HABILITADO`.
- `hide_input_in_errors` ya está activo, y el validador nombra la variable faltante sin mostrar su valor.
- `docker-compose.yml` las pasa desde el entorno del host con defaults de test (`MP_GATEWAY=fake` y secreto sintético). CI hace lo mismo.
- Nunca se commitea `.env` (R20).

### D10. Frontend (`frontend-paciente/`)
- **Componente nuevo `PagoSena.tsx`:** reemplaza a `Confirmacion` cuando la respuesta trae `estado === "en_espera"`. Título "Pagá la seña para confirmar tu turno"; resumen (tratamiento, día y hora de la clínica); monto (con `formato.ts`, sin float: el monto llega como string decimal); "Tu reserva vence a las HH:MM"; el texto de la política de reembolso que viene de la configuración (por defecto: "Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve."); un botón por medio habilitado ("Pagar con Mercado Pago" / "Pagar por transferencia"); aviso "Tu turno no está confirmado hasta acreditar la seña".
- **Mercado Pago:** antes de `window.location.assign(checkout_url)` guarda `{turnoId, codigoGestion}` en `localStorage` con vencimiento (versionado y mínimo; el código de gestión no va en la URL; ver P15). Al volver (`?pago=retorno&turno=`), `App` monta `EsperaAcreditacion`.
- **Espera de acreditación:** consulta `GET .../sena` cada 3 s con backoff hasta 2 minutos y se detiene en un estado terminal. Termina en "Turno reservado" (reusa `Confirmacion`), "La reserva venció" (CTA "Elegir otro horario"), "El horario se ocupó" (`a_reembolsar`: "La clínica se va a comunicar para devolverte la seña") o "Seguimos esperando la acreditación". No hay fetch en cascada (R2): es un único recurso que se sondea.
- **Transferencia:** alias, CBU, titular, monto y el código de referencia para el concepto ("Poné este código en el concepto de la transferencia"), cada uno con botón "Copiar", y el aviso "La clínica confirma tu turno al acreditar la transferencia".
- **Diseño:** usa los tokens de C-05 (`estilos.css`, paleta de Stitch, Plus Jakarta Sans, botones de 48px, sin barra fija). El monto es el elemento destacado de la pantalla; el resto queda sobrio (`frontend-design`). Sin `any` y con tipos discriminados para el estado (R1).
- **Stitch MCP:** se puede generar una pantalla de referencia de 360px para el `PagoSena` y guardarla como evidencia en `docs/skills-mcp/evidencia-stitch/` con datos sintéticos. Es opcional y no bloquea el apply.

### D11. Estrategia de pruebas (Strict TDD)
- **Unit (pytest, sin DB):** `calculo` (redondeo, tope por inicio), `estados` (tabla completa de transiciones), firma HMAC (válida, otro secreto, ts fuera de tolerancia, cabecera malformada) y adaptador falso.
- **Integración (pytest + PostgreSQL real, como hoy):** reserva en `en_espera`, inicio de seña (MP, transferencia, idempotente, cambio de medio, 404 por código, 409 por horario tomado), webhook (firma inválida 401, duplicado, concurrente con `asyncio.gather`, desconocido 200), acreditación con competencia entre dos `en_espera`, reasignación de sillón, admin (RBAC 403/200), barrido (inyectando `ahora`), ausente → `no_reembolsado`, cancelación con 24 h o más → `a_reembolsar` y con 23 h 59 min → 409, migración `upgrade → downgrade → upgrade`.
- **Adaptador real de Mercado Pago:** se prueba con `httpx.MockTransport`, sin red.
- **E2E (Playwright 360px, backend real con `MP_GATEWAY=fake`):** reserva → pantalla de seña → MP → retorno → el test firma y envía el webhook con `request` → "Turno reservado"; transferencia → acreditación por la API admin con login sintético → "Turno reservado"; vencimiento (con `expiracion_mp_minutos` mínimo y el barrido invocado, o el `en_espera_vence_en` adelantado por `pg` en el helper, como ya hace `e2e/ayudas.ts`); competencia: dos pacientes reservan el mismo horario (ambos 201) y gana el primero en acreditar; sin scroll horizontal a 360px.

## Risks / Trade-offs
- **[Dos pacientes pagan el mismo horario]**, consecuencia directa de R8 → *Mitigación:* revalidación al iniciar el pago (D4), vencimiento de la preferencia igual al de la pre-reserva y estado `a_reembolsar` visible para la clínica. El riesgo queda acotado a pagos casi simultáneos.
- **[El webhook no llega o llega tarde]** → *Mitigación:* el sondeo del frontend avisa "Seguimos esperando la acreditación", Mercado Pago reintenta y la idempotencia de D5 cubre los reintentos. Futuro: una conciliación periódica con `obtener_pago` (posible tarea de C-09).
- **[Firma de Mercado Pago mal implementada]** → *Mitigación:* tests con vectores fijos y comparación en tiempo constante. La firma nunca se saltea, tampoco con la pasarela falsa.
- **[Se activa la pasarela falsa en producción]** → *Mitigación:* `Settings` falla si `APP_ENV=production` y `MP_GATEWAY=fake`.
- **[Barrido con varias réplicas del backend]** → *Mitigación:* es idempotente (`UPDATE ... WHERE estado='en_espera' AND vence <= ahora`). C-09 lo centraliza.
- **[Breaking del contrato de C-05]** → *Mitigación:* el frontend y los E2E se actualizan en el mismo change; no hay otros consumidores.
- **[La preferencia de Mercado Pago se crea con el lock global tomado]** → *Aceptado (P11):* si la pasarela se cuelga, las reservas esperan hasta el timeout de 10 s. *Mejora futura:* crear la preferencia fuera del advisory lock (primero el pago pendiente y el commit, después la preferencia, con compensación si falla).
- **[El advisory lock global serializa todas las reservas y acreditaciones]** → Trade-off aceptado por el volumen de una clínica. Si hiciera falta, se puede pasar a una clave por profesional.

## Migration Plan
1. `alembic upgrade head` aplica `006_sena_pagos`. Los turnos existentes no cambian y la configuración por defecto se inserta con 30%.
2. Deploy del backend con `MP_GATEWAY` y las credenciales en el entorno. Configurar en Mercado Pago la URL del webhook y el secreto.
3. Deploy del frontend.
4. **Rollback:** `alembic downgrade 005_reserva_publica` (cancela los `en_espera` y borra `pago_sena` y `configuracion_sena`; se pierde el historial de señas) y volver al build anterior.

## Decisiones aprobadas (2026-11-06)
El usuario las aprobó el 2026-11-06 y quedaron como contrato en la KB: `05_reglas_de_negocio.md` (RN-SN-04 a RN-SN-08), `04_modelo_de_datos.md` (§PagoSena) y `09_decisiones_y_supuestos.md`.

| # | Decisión | Resolución | Regla |
|---|----------|------------|-------|
| P1 | Cuánto dura un `en_espera` | Mercado Pago: **30 min**. Transferencia: **24 h** (se extiende al elegir el medio). En ambos casos, como máximo hasta el inicio del turno. El admin puede editarlos. | RN-SN-07 |
| P2 | Seña ante una cancelación con 24 h o más de anticipación | **Se devuelve:** el pago pasa a `a_reembolsar` y la devolución es manual. Con menos de 24 h no se puede cancelar (RN-TU-01). El ausente sigue sin reembolso (`no_reembolsado`). C-06 define la regla en la máquina de estados (D7) y C-07 la aplica en el endpoint de cancelación. *(Cambió respecto del default propuesto, que era no reembolsable.)* | RN-SN-04, RN-SN-02 |
| P3 | Pago aprobado sobre un turno vencido o cancelado, o sobre un horario que ganó otro | **`a_reembolsar`**, con devolución manual; el turno no se revive. | RN-SN-05 |
| P4 | Tratamiento con precio base 0 | **Exento de seña:** nace `reservado` directo. | RN-SN-06 |
| P5 | `sena_porcentaje` inicial | **30%** del precio base del tratamiento. | RN-SN-03 |
| P6 | ¿La transferencia necesita acreditación manual? | **Sí:** la acredita recepción/admin por la API (`POST /api/admin/pagos-sena/{id}/acreditar`); la UI llega en C-12. El paciente ve el alias, el CBU y un código de referencia del turno para el concepto. | RN-SN-08 |
| P7 | ¿Se rompen los E2E y tests de C-05? | **Sí, se reescriben en este change** (la carrera 201/409 pasa a 201/201 con la competencia en la acreditación). | R7, R8 |
| P8 | Barrido de vencimiento antes de C-09 | **Tarea `asyncio` en el `lifespan`** cada 60 s, idempotente, sin Redis. C-09 la consolida. | RN-SN-07 |
| P9 | Monto informado por la pasarela distinto de la seña | **No se acredita:** el pago pasa a `en_revision` (estado nuevo en `ck_pago_sena_estado`, columnas `monto_reportado` y `moneda_reportada`, editando la 006 porque no está publicada), el turno sigue `en_espera` con su vencimiento normal y el webhook responde 200 de forma idempotente con una auditoría `sena_en_revision` sin PII. La comparación es decimal exacta y la moneda debe ser ARS. **Falla cerrado:** si la pasarela no informa el monto o la moneda, o son ilegibles, el pago también va a `en_revision` (el contrato de la pasarela exige ambos; `acreditar_pago` solo omite la comparación con `manual=True`, que usa únicamente la acreditación de recepción/admin; el adaptador de Mercado Pago informa `None` ante un dato ausente o ilegible). Recepción/admin lo resuelve con el endpoint de acreditación manual, que acepta pagos `en_revision` de cualquier medio; si el turno ya no está vigente queda `a_reembolsar`. La pasarela falsa codifica monto y moneda en el id (`fake-approved-<ref>@<monto>@<moneda>`). | RN-SN-09 |
| P10 | Pago `vencido` por cambio de medio que la pasarela aprueba con el turno vigente | **Se acredita** (el dinero llegó y el turno está vivo) y vence los demás pagos pendientes. | RN-SN-05 |
| P11 | Llamada a la pasarela dentro del lock global de reservas | **Se mantiene** (D4) con timeout de 10 s. Mejora futura: ver Riesgos. | D4 |

| P12 | Pasarela falsa y secretos por defecto | **Fail-safe (R17):** los defaults son producción con Mercado Pago real; la pasarela falsa solo se acepta con `APP_ENV=test` o `APP_ENV=e2e` (`Settings` no arranca en otro caso) y `docker-compose.yml` no trae ningún secreto de webhook por defecto (`MP_WEBHOOK_SECRET` es obligatoria). CI, tests y E2E exportan valores sintéticos. | R17 |
| P13 | Varios pagos de la pasarela para una misma seña | **Se registran por id** (tabla `pago_sena_aprobacion`): idempotencia por id, sobrantes y pagos en revisión no aceptados quedan `a_reembolsar` con trazabilidad. | RN-SN-10 |
| P14 | Errores transitorios en la acreditación | **Un deadlock o un error de serialización nunca produce un reembolso:** se reintenta y, agotado, responde 503 (el webhook se reintenta). Orden de locks único (advisory, turno, pago) en acreditar, cambiar estado y barrido; la acreditación manual se valida bajo lock. | RN-SN-05 |
| P15 | Retorno del checkout en otra pestaña | La seña pendiente va a `localStorage` con vencimiento (pre-reserva + 30 min, tope 24 h), clave versionada y sin el código en la URL; se borra al llegar a un estado terminal. La pantalla trata `en_revision` como pantalla clara. | R3 |

Aceptados también del reporte del apply: (3) `GET /api/public/turnos/{id}/sena` devuelve `inicio`, `fin`, `tratamiento_nombre` y `profesional_nombre` (sin contacto) para mostrar la confirmación al volver del checkout; (4) la transferencia solo se ofrece si el admin cargó alias y CBU; (5) `en_espera → reservado` no existe como transición manual: la única vía es la acreditación; (6) el monto viaja a Mercado Pago como literal numérico exacto, sin pasar por float.

## Open Questions
- Datos reales de la cuenta para transferir (alias, CBU, titular): los carga el admin. En el repo solo hay valores sintéticos (R19).
- Si la clínica va a usar Checkout Pro (redirect, lo que asume este diseño) o Checkout Bricks embebido. No cambia los specs: es un detalle del adaptador y de la pantalla.

## Audit & Compliance Note (spec-rules-auditor)
Auditado con `spec-rules-auditor` sobre `proposal.md`, este `design.md` y los tres deltas de spec. El dictamen y la matriz de trazabilidad están en el resumen de la propuesta. Resultado: **APROBADO**. La re-auditoría del 2026-11-06, hecha después de aprobar las decisiones, no dejó supuestos abiertos: cada regla nueva tiene su RN-SN.
