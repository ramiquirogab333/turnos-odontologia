# Design: c-07-cancelacion-reprogramacion-24h

## Context
La motivación está en `proposal.md` (Why) y los requisitos en `specs/turnos/gestion-paciente/spec.md` y en el delta de `pagos/sena-turno`. Esto es lo que se verificó en el código (no en `CHANGES.md`) y condiciona el diseño:

- **El código de gestión ya existe** (migración `005_reserva_publica`): `turno.codigo_gestion TEXT UNIQUE`, `CHECK LENGTH 8..64`, generado como `str(uuid.uuid4())` (122 bits aleatorios) en `reservar_turno_publico`. Los turnos internos (`POST /api/turnos`) lo tienen en `NULL`. **No hay que introducirlo.**
- **El paciente solo conoce el código, no el id del turno:** `Confirmacion.tsx` muestra "Tu código de gestión" y nada más. La seña (C-06) autentica con `turno_id` en la ruta y `X-Codigo-Gestion` en la cabecera, comparado con `hmac.compare_digest`, y cualquier falla es 404.
- **La regla de 24 h y los efectos sobre la seña ya están en `app/pagos/estados.py`** (`aplicar_transicion`, `VENTANA_CANCELACION = 24 h`, `inicio - ahora < 24 h` → `CancelacionFueraDePlazoError`; exactamente 24 h se acepta) y **el servicio `cambiar_estado_turno`** (`app/pagos/service.py`) ya los aplica con el orden de locks advisory → turno → pago y reintento de 40P01/40001. C-06 lo dejó probado esperando a C-07.
- **Hueco encontrado:** `_cambiar_estado_una_vez` solo bloquea y resuelve el pago en `pendiente`/`acreditado`. Un pago `en_revision` de un `en_espera` cancelado quedaría colgado, contra RN-SN-10.
- **Anti-solape:** EXCLUDE parciales `WHERE estado IN ('reservado','confirmado')` (001). Un `UPDATE` de `inicio`/`fin`/`sillon_id` de un turno bloqueante queda alcanzado por el EXCLUDE, y una fila no choca consigo misma. El pre-chequeo de aplicación (`_cargar_bloqueos`) hoy no puede excluir un turno, así que contaría al propio turno como ocupación al reprogramar a un horario que se superpone con el suyo.
- **Disponibilidad y alternativas** ya existen y se reutilizan: `_franja_que_contiene` (RN-TU-07), `_sillon_libre`, `_profesional_ocupado`, `_alternativas` y `ReservaConflictoBody` (409 con `motivo` y `alternativas`).
- **Zona horaria:** `Settings.app_tz = "America/Argentina/Buenos_Aires"`; todas las columnas son `TIMESTAMPTZ` (R4). Argentina no tiene horario de verano hoy.
- **No hay Redis, scheduler, Google Calendar ni recordatorios:** llegan con C-09 y C-10. C-06 dejó la auditoría con `origen` como único punto de enganche.
- **Última migración: `006_sena_pagos`.** Con los defaults recomendados C-07 no necesita una nueva.
- **Frontend sin router:** `App.tsx` decide la vista por `window.location` (`?pago=retorno`). `PasoHorario` recibe `slots: Promise<Slot[]>` y se puede reutilizar. Los E2E corren contra el backend real (360x800, navegador en Asia/Tokyo) y ya manipulan la base por `pg` en `e2e/ayudas.ts`.

## Goals / Non-Goals

**Goals:**
- Exponer la cancelación y la reprogramación públicas reutilizando la máquina de estados y el orden de locks de C-06, sin duplicar la regla de 24 h.
- Que la base de datos siga siendo la garantía del anti-solape al mover un turno (R5), y que una carrera nunca devuelva 500.
- Dejar un puerto de eventos estable para que C-09 y C-10 se enganchen sin tocar el dominio de C-07.

**Non-Goals:**
- Implementar Google Calendar, recordatorios o el link de cancelación de WhatsApp (C-09, C-10).
- Cancelación o reprogramación desde el panel (C-08) y UI de caja para `a_reembolsar` (C-12).
- Rate limiting del endpoint público (ver Riesgos).
- Cambiar el formato del código de gestión.

## Decisions

### D1. Módulo `app/gestion/` y rutas por cabecera
- **Decisión:** módulo nuevo `backend/src/app/gestion/` con `schemas.py` (Pydantic, `extra="forbid"`, R15), `service.py`, `router.py` y `eventos.py`. Rutas:
  - `GET /api/public/gestion` → `GestionTurnoResponse`.
  - `POST /api/public/gestion/cancelar` (sin body) → `CancelacionResponse`.
  - `POST /api/public/gestion/reprogramar` con `{ "inicio": AwareDatetime }` → `ReprogramacionResponse`.

  Las tres leen `X-Codigo-Gestion` (mismo alias `CodigoGestion` que `pagos/router_public.py`). El turno se busca por `codigo_gestion` (índice único); un código vacío, de largo fuera de 8..64, inexistente o de un turno sin código responde el mismo 404 genérico.
- **Por qué cabecera y no `/api/public/turnos/{codigo}/cancelar` (lo que dice `CHANGES.md`):** el código es la única credencial del turno; en la ruta queda en los access logs del servidor y del proxy, en el historial y en el `Referer`. En la cabecera no. Es el mismo criterio que C-06 (`X-Codigo-Gestion`). Ver decisión abierta **O1**.
- **Por qué sin `turno_id`:** el paciente solo tiene el código. Con UUID4 (122 bits) la búsqueda por igualdad sobre el índice único no es atacable por fuerza bruta ni por tiempo de forma práctica.
- **Alternativas descartadas:** `/api/public/turnos/{id}/cancelar` + cabecera (el paciente no conoce el id); código en la ruta (logs).

### D2. Cancelación: reusar `cambiar_estado_turno`
- `cancelar_turno_publico(session, codigo, *, ahora, notificador)`:
  1. Resuelve el `turno_id` por código (lectura sin lock; el código es inmutable).
  2. Llama a `cambiar_estado_turno(session, turno_id, "cancelado", usuario_id=None, ahora=ahora, origen="cancelacion_paciente")`, que toma el advisory lock, bloquea turno y pagos, aplica `aplicar_transicion` (24 h para `reservado`/`confirmado`; sin ventana para `en_espera`), escribe la auditoría y hace commit.
  3. Mapea errores: `TransicionInvalidaError` → 409 `turno_no_modificable`; `CancelacionFueraDePlazoError` → 409 `fuera_de_plazo` con `limite_cambios`; `OperacionReintentableError` → 503.
  4. Después del commit, si el turno bloqueaba agenda (`reservado`/`confirmado`), publica `turno_cancelado` (D5).
- **Cambios en `app/pagos/service.py`:**
  - `_cambiar_estado_una_vez` acepta `origen: str = "cambio_estado"` para la auditoría (`cancelacion_paciente` aquí; C-08 usará el suyo).
  - Al pasar `en_espera → cancelado`, además del pago `pendiente` → `vencido`, bloquea los pagos `en_revision` del turno y los pasa a `a_reembolsar` (RN-SN-10), con el mismo orden de locks.
  - Devuelve también el estado anterior y el `inicio`/`fin` para armar el evento.
- **`en_espera` vencido que el barrido todavía no tocó:** se cancela igual (mismo resultado final que el barrido). Si el barrido ya lo canceló, es `turno_no_modificable`.

### D3. Reprogramación: mover el turno en el lugar
`reprogramar_turno_publico(session, codigo, nuevo_inicio, *, ahora, notificador)`, en una transacción:
1. `pg_advisory_xact_lock(LOCK_RESERVAS)` y `SELECT turno ... FOR UPDATE` por código (mismo orden que C-06). Luego el pago activo `FOR UPDATE` (solo para leerlo; no cambia).
2. Estado: `en_espera` → 409 `sena_pendiente` (**O3**); final → 409 `turno_no_modificable`.
3. Ventana: `turno.inicio - ahora < 24 h` → 409 `fuera_de_plazo` (reusa `VENTANA_CANCELACION` de `estados.py` mediante una función pura `dentro_de_ventana(inicio, ahora)`, para que la regla tenga una sola fuente).
4. Validación del nuevo inicio: `nuevo_inicio <= ahora` o igual al actual → 422; `fin = nuevo_inicio + tratamiento.duracion_minutos` vigente (RN-TU-04/05); `_franja_que_contiene` de la misma profesional → si no cabe, 422 `fuera_de_disponibilidad` (RN-TU-07).
5. Anti-solape en aplicación (fast-fail): `_cargar_bloqueos(..., excluir_turno_id=turno.id)`; profesional ocupada → 409 `profesional` con `_alternativas`; sin sillón (`_sillon_libre`, prefiere el sillón por defecto de la franja y luego el actual) → 409 `sillon`.
6. `UPDATE` en el lugar: `inicio`, `fin`, `sillon_id`, y `estado = "reservado"` si estaba `confirmado` (**O5**). La columna `periodo` se recalcula sola (`GENERATED`). Auditoría `origen: "reprogramacion_paciente"` con inicio/fin/sillón/estado antes y después, sin PII.
7. `flush`; un 23P01 o 40P01 (red de seguridad, R5) → rollback y 409 con alternativas, nunca 500. Commit.
8. Después del commit, publica `turno_reprogramado` (D5).

- **Por qué en el lugar y no cancelar + crear uno nuevo:** conserva el id, el código de gestión (los enlaces siguen funcionando), el `PagoSena` acreditado (su FK apunta al turno, así que "la seña acompaña al turno" sale gratis) y la historia en la auditoría. Cancelar + crear obligaría a mover el pago a otro turno o a marcarlo `a_reembolsar` y cobrar de nuevo, y rompería el enlace del paciente.
- **Por qué mismo tratamiento y misma profesional (O2):** la seña se calculó sobre el precio del tratamiento; cambiarlo abre cobros de diferencia. Cambiar de profesional es posible técnicamente pero amplía la UI y el caso del paciente "elige nuevo horario libre" (Flujo 2) no lo pide.
- `_cargar_bloqueos` gana un parámetro opcional `excluir_turno_id: int | None = None`; las llamadas existentes no cambian.

### D4. Semántica de la ventana de 24 h
- Se compara en **instantes absolutos**: `turno.inicio - ahora >= timedelta(hours=24)` con ambos `datetime` con zona (UTC en la base). No se usa la hora de pared, así que un cambio de horario no altera la ventana. **Exactamente 24 h se acepta** (como ya decidió C-06 y prueba `test_sena_estados.py`) (**O6**).
- `ahora` es el reloj del servidor tomado **después** de obtener el advisory lock (una solicitud que espera el lock se evalúa con la hora en que realmente se procesa). Los servicios aceptan `ahora` inyectado para los tests.
- Para reprogramar, la ventana se mide contra el **inicio actual**. El nuevo horario puede estar a menos de 24 h si está libre (**O7**); el paciente queda avisado de que después no va a poder cambiarlo.
- `limite_cambios = inicio - 24 h`, devuelto con el offset de la clínica (`astimezone(ZoneInfo(app_tz))`), igual que las demás horas de la API pública.

### D5. Puerto de eventos para C-09/C-10 (`app/gestion/eventos.py`)
- `class NotificadorTurnos(Protocol)` con `async def publicar(evento: EventoTurno) -> None`. `EventoTurno` es un `dataclass(frozen=True)` con `tipo: Literal["turno_cancelado", "turno_reprogramado"]`, `turno_id`, `profesional_id`, `inicio_anterior`, `fin_anterior`, `inicio_nuevo | None`, `fin_nuevo | None`, `ocurrido_en`. Sin nombre ni teléfono (R19, Ley 25.326).
- Implementación v1: `NotificadorNulo`, que escribe un log estructurado sin PII. Se inyecta con `Depends(get_notificador)` y los tests lo reemplazan por uno que registra (`dependency_overrides`).
- Se llama **después del commit** y dentro de `try/except`: una falla se loguea y no revierte la operación (spec "publicador caído").
- Solo se publica para turnos que bloqueaban agenda (`reservado`/`confirmado`): un `en_espera` nunca tuvo evento de calendario ni recordatorio (RN-SN-01).
- **Durabilidad:** el registro de auditoría (`origen` `cancelacion_paciente` / `reprogramacion_paciente`, en la misma transacción) queda como fuente reconciliable. C-09 y C-10 implementan el puerto (encolar en Redis) y pueden reconciliar desde la auditoría o desde el estado del turno si se pierde una publicación.
- **Alternativa descartada por ahora:** tabla outbox (`evento_turno`, migración 007) con entrega garantizada. Es lo más robusto, pero adelanta la infraestructura de C-09 sin un consumidor. Ver **O8**.

### D6. Respuestas y errores
- `GestionTurnoResponse`: `estado`, `inicio`, `fin`, `tratamiento {id, nombre, duracion_minutos}`, `profesional {id, nombre}`, `sena {monto, estado} | null`, `limite_cambios`, `puede_cancelar`, `puede_reprogramar`, `motivo_no_cancelable | null`, `motivo_no_reprogramable | null`, `texto_politica_reembolso`. Los `id` de tratamiento y profesional son los que el frontend necesita para `GET /api/public/disponibilidad`.
- Errores: 404 `{"detail": "No encontramos un turno con ese código"}`; 409 `{"detail", "motivo": "fuera_de_plazo" | "turno_no_modificable" | "sena_pendiente", "limite_cambios"?}`; 409 de solape con `ReservaConflictoBody` (`motivo` `profesional`/`sillon`, `alternativas`); 422 `fuera_de_disponibilidad` / `mismo_horario` / validación Pydantic; 503 `reintentar` si se agotan los reintentos transitorios.
- Los textos para el paciente van en castellano rioplatense y dicen qué pasó y qué hacer (por ejemplo, "Ya no podés cancelar online porque faltan menos de 24 h para tu turno (el límite era el domingo 15/11 a las 10:00). Comunicate con la clínica.").

### D7. Frontend (`frontend-paciente/`)
- **Ruta:** `App.tsx` muestra `GestionTurno` cuando `location.pathname === "/gestionar"`. El código se lee de `location.hash` (nunca viaja al servidor), se guarda en memoria y se limpia del hash con `history.replaceState`. Sin hash, la pantalla pide pegar el código (`<input>` con `inputMode="text"`, `autoComplete="off"`).
- **Carga sin cascadas (R2):** al abrir, un único `GET /api/public/gestion` dentro de `Suspense`. La disponibilidad se pide recién cuando la o el paciente toca "Cambiar horario" (acción del usuario, como en C-05), reutilizando `PasoHorario` con los ids del turno.
- **Cancelar:** diálogo de confirmación con el texto de la seña según el estado (`acreditado` → "La clínica te va a devolver la seña de $ 3.000,00"; `en_espera` → "No se te cobra nada"). Resultado: "Turno cancelado".
- **Cambiar horario:** elegir día y horario → "Confirmar cambio" → "Turno reprogramado" con el horario nuevo. Un 409 de solape muestra "Ese horario ya no está disponible" y las alternativas.
- **Dentro de las 24 h:** se muestra el aviso y no se habilitan las acciones; el backend sigue siendo la autoridad (un 409 `fuera_de_plazo` muestra el mismo texto).
- `Confirmacion.tsx` agrega el enlace "Gestionar mi turno" (`/gestionar#<código>`) y el texto "Podés cancelar o cambiar el horario hasta 24 h antes".
- Tipos discriminados para estados y motivos, sin `any` (R1); tokens de `estilos.css`, botones de 48 px, sin scroll horizontal a 360 px (R3). Stitch MCP es opcional para una pantalla de referencia con datos sintéticos.

### D8. Estrategia de pruebas (Strict TDD)
- **Unit (sin DB):** `estados` (ventana con `ahora` inyectado: 24 h exactas, 24 h − 1 s, 23 h 59 min, después del inicio; `en_espera` sin ventana), cálculo de `limite_cambios` en hora de la clínica, armado del `EventoTurno` sin PII.
- **Integración (pytest + PostgreSQL real):** 404 por código (ausente, vacío, desconocido, turno interno); consulta con `puede_*`; cancelación `reservado` 48 h → `a_reembolsar` y horario libre; 23 h 59 min → 409 sin cambios; exactamente 24 h; `en_espera` con pago `pendiente` → `vencido`; con `en_revision` → `a_reembolsar`; aprobación tardía → `a_reembolsar`; finales → 409; reprogramación feliz (mismo id, código y pago); a horario ocupado → 409 con alternativas; superpuesto con el propio → aceptado; fuera de franja, pasado, mismo horario, sin zona → 422; `confirmado` → `reservado`; dos reprogramaciones concurrentes (`asyncio.gather`) al mismo horario → una 200 y una 409, nunca 500; `UPDATE` directo solapado → 23P01; notificador que registra y notificador que falla.
- **E2E (Playwright, 360 px, backend real):** el reloj del servidor no se puede inyectar desde el navegador, así que el borde exacto se prueba en integración y el E2E siembra turnos por `pg` a cada lado del borde con margen: `inicio = ahora + 24 h + 5 min` (se acepta) y `inicio = ahora + 23 h 55 min` (se rechaza con el mensaje). Ver **O9**.

## Risks / Trade-offs
- **[El código en el enlace se comparte o se filtra]** → quien lo tenga puede cancelar el turno. *Mitigación:* el código va en el fragmento (no llega a logs), es de 122 bits, y la auditoría deja rastro. Igual que en C-06. Rate limiting queda para cuando haya Redis (C-09).
- **[Se pierde un evento si el proceso muere entre el commit y la publicación]** → *Mitigación:* la auditoría transaccional permite reconciliar; outbox si se aprueba O8.
- **[La disponibilidad pública muestra como ocupado el horario propio]** → al reprogramar a un horario que se superpone con el propio, ese slot no aparece en la grilla aunque el backend lo aceptaría. *Aceptado:* caso raro; el backend no lo rechaza si llega.
- **[Reloj del servidor desfasado]** → la ventana depende del reloj del contenedor. *Mitigación:* NTP del host; el margen de los E2E absorbe segundos.
- **[El advisory lock global también serializa cancelaciones y reprogramaciones]** → trade-off aceptado por el volumen de una clínica, igual que en C-06.
- **[`CHANGES.md` dice "R9 (seña retenida en cancelación de `reservado`)"]** → contradice RN-SN-04 (decisión 2026-11-06: se devuelve). Este diseño sigue la KB; hay que corregir `CHANGES.md` (tarea 11.2).

## Migration Plan
1. Sin migración de base con los defaults recomendados. Si se aprueba O4 (límite de reprogramaciones) se agrega `007_gestion_turno` con `turno.reprogramaciones SMALLINT NOT NULL DEFAULT 0 CHECK (reprogramaciones >= 0)`, reversible. Si se aprueba O8, la misma 007 crea la outbox.
2. Deploy del backend (router nuevo, cambio compatible en `cambiar_estado_turno`).
3. Deploy del frontend (pantalla y enlace en la confirmación).
4. **Rollback:** volver al build anterior; no hay datos nuevos que revertir (los turnos cancelados o movidos quedan como están, con su auditoría).

## Decisiones a confirmar (governance MEDIO)
Los specs están escritos con el default recomendado. Si el usuario elige otra opción, se ajustan spec, diseño y tareas antes del apply.

| # | Decisión | Opciones | Default recomendado / estado |
|---|----------|----------|---------------------|
| O1 | Cómo viaja el código de gestión en la API | (a) cabecera `X-Codigo-Gestion` en `/api/public/gestion/*`; (b) en la ruta `/api/public/turnos/{codigo}/cancelar`, como dice `CHANGES.md` | **(a)**: no queda en logs ni en el `Referer`, y es el criterio de C-06. Se actualiza `CHANGES.md`.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O2 | Qué se puede cambiar al reprogramar | (a) solo día y hora, mismo tratamiento y profesional; (b) también profesional; (c) también tratamiento | **(a)**: evita recalcular la seña; (b) se puede sumar después sin romper el contrato.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O3 | Reprogramar un `en_espera` | (a) no: 409 `sena_pendiente`, que cancele y reserve otro; (b) sí, moviendo la pre-reserva y su pago pendiente | **(a)**: la pre-reserva dura 30 min (MP) y no bloquea nada; mover pagos pendientes con preferencia ya creada suma riesgo sin beneficio.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O4 | Límite de reprogramaciones por turno | (a) sin límite; (b) N veces (migración 007) | **(a)**: no hay regla en la KB y cada cambio igual exige 24 h y un horario libre. Se audita cada cambio para que C-12 lo reporte.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O5 | Estado de un `confirmado` reprogramado | (a) vuelve a `reservado`; (b) sigue `confirmado` | **(a)**: la confirmación (C-09) fue para el horario anterior; el recordatorio del nuevo horario pide confirmar otra vez.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O6 | Borde exacto de 24 h | (a) exactamente 24 h se acepta (`>=`); (b) se rechaza (`>`) | **(a)**: ya decidido y probado en C-06 (`test_sena_estados.py`); RN-TU-01 dice "menos de 24 h" se rechaza.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O7 | Nuevo horario a menos de 24 h | (a) se permite si está libre, con aviso; (b) el nuevo horario también debe estar a 24 h o más | **(a)**: RN-TU-02 limita la anticipación respecto del turno que se cambia; la reserva pública tampoco exige 24 h.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O8 | Entrega de eventos a C-09/C-10 | (a) puerto `NotificadorTurnos` post-commit + auditoría reconciliable; (b) tabla outbox (migración 007) | **(a)**: sin consumidor todavía; C-09 puede introducir la outbox junto con Redis sin cambiar el puerto.  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O9 | Cobertura E2E del borde de 24 h | (a) borde exacto en integración con reloj inyectado + E2E con margen de ±5 min; (b) reloj falso del backend para E2E (`APP_CLOCK_OFFSET`, solo `APP_ENV=e2e`) | **(a)**: un reloj manipulable por entorno es superficie de riesgo en producción, como la pasarela falsa (P12 de C-06).  Aprobado por el usuario 2026-11-06 (default confirmado). |
| O10 | Cancelar un `en_espera` | (a) en cualquier momento mientras siga en espera; (b) también con la ventana de 24 h | **(a)**: no bloquea agenda ni hay cobro (R8); es lo que pide `CHANGES.md`.  Aprobado por el usuario 2026-11-06 (default confirmado). |

## Open Questions
- Texto exacto del canal de contacto de la clínica en el mensaje de "fuera de plazo" (teléfono o WhatsApp). No cambia el contrato: el texto puede salir de configuración más adelante; por ahora es genérico ("Comunicate con la clínica").

## Audit & Compliance Note (spec-rules-auditor)
Auditado con `spec-rules-auditor` sobre `proposal.md`, este `design.md` y los dos deltas de spec, contra `knowledge-base/05_reglas_de_negocio.md` y las reglas duras R1–R20. Dictamen: **APROBADO**, condicionado a que el usuario confirme O1–O10 (marcadas como `[SUPUESTO / ABIERTO]` con su default).

| Regla | Estado | Dónde |
|-------|--------|-------|
| RN-TU-01 (no cancelar < 24 h) | CUBIERTA | gestion-paciente: "Cancelación … respetando 24 horas" (48 h / 23 h 59 min / exactamente 24 h) |
| RN-TU-02 (no reprogramar < 24 h) | CUBIERTA (supuesto IN-02 → O6/O7) | "Reprogramación a un horario libre respetando 24 horas" |
| RN-TU-03 / R5 (anti-solape) | CUBIERTA | "Reprogramación a un horario ocupado ofrece alternativas" (ocupado, concurrencia, nunca 500) |
| RN-TU-04 / RN-TU-05 (duración vigente) | CUBIERTA | fin = nuevo inicio + duración vigente |
| RN-TU-06 (sin login) | CUBIERTA | "Acceso a la gestión solo con el código de gestión" |
| RN-TU-07 (horario libre vigente) | CUBIERTA | "Reprogramación solo dentro de la disponibilidad vigente" |
| RN-SN-01 / R8 (`en_espera` no bloquea ni notifica) | CUBIERTA | cancelación de pre-reserva sin ventana ni caja; sin evento |
| RN-SN-02 / R9 (ausente no reembolsa) | CUBIERTA | estados finales → 409, seña `no_reembolsado` intacta |
| RN-SN-04 (≥ 24 h devuelve) | CUBIERTA | sena-turno MODIFIED + gestion-paciente |
| RN-SN-05 (pago tardío) | CUBIERTA | aprobación después de cancelar → `a_reembolsar` |
| RN-SN-10 (`en_revision`) | CUBIERTA (gap del código de C-06 corregido en D2) | sena-turno ADDED |
| RN-GL-01 (auditoría) | CUBIERTA | auditoría `cancelacion_paciente` / `reprogramacion_paciente` |
| RN-GL-03 / R3 (360 px) | CUBIERTA | "Pantalla de gestión del turno a 360px" |
| R7 (E2E) | CUBIERTA | tasks 6.2 (borde con margen; exacto en integración, O9) |
| R19 (datos sintéticos) | CUBIERTA | eventos y respuestas sin PII; ejemplos sintéticos |
| RN-WA-*, RN-GC-* | FUERA DE ALCANCE | puerto `NotificadorTurnos` para C-09/C-10 |

Observaciones levantadas y resueltas en los borradores: pagos `en_revision` sin resolver al cancelar un `en_espera` (D2); el propio turno contaba como ocupación al reprogramar (D3, `excluir_turno_id`); eventos sin PII; `CHANGES.md` contradice RN-SN-04 en "R9 (seña retenida en cancelación de `reservado`)" (tarea 7.2).
