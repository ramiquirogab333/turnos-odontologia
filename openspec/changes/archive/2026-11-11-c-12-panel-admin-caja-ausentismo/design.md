# Design: c-12-panel-admin-caja-ausentismo

## Context
La motivación está en `proposal.md` y los requisitos en los specs de este change (cuatro capacidades nuevas y cinco modificadas). Esto es lo que se verificó en el código (rama `feat/c-12-panel-admin-caja-ausentismo`, última migración `008_ficha_odonto_presup`) y condiciona el diseño.

**Dinero que ya existe**
- `pago_sena` (C-06): estados `pendiente`, `acreditado`, `vencido`, `no_reembolsado`, `a_reembolsar`, `en_revision`; `monto NUMERIC(10,2)`, `monto_reportado` (lo que informó la pasarela si no coincidió), `acreditado_en`, `mp_payment_id`. No tiene índice por `acreditado_en`.
- `acreditado_en` ya se usa como "momento en que la clínica recibió el dinero": lo sella la acreditación y también `_marcar_a_reembolsar` (pago tardío u horario perdido). **Hay un camino que no lo sella:** un `en_revision` que pasa a `a_reembolsar` al cancelarse la pre-reserva (`_cambiar_estado_una_vez`).
- `pago_sena_aprobacion` (RN-SN-10) guarda cada pago aprobado de Mercado Pago por su id, con estado `aplicado`, `en_revision` o `a_reembolsar`. Un **pago excedente** (otro id sobre una seña ya resuelta) queda `a_reembolsar` solo en esta tabla: la seña puede seguir `acreditado`. Hay entonces dos niveles de "dinero a devolver".
- Un pago `en_revision` ya se acepta con `POST /api/admin/pagos-sena/{id}/acreditar` (si el turno ya no está vigente queda `a_reembolsar`). **No existe forma de rechazarlo, ni de listar pendientes, ni de registrar una devolución hecha.** El barrido de vencimientos no toca los `en_revision`: quedan así sobre un turno `cancelado` hasta que alguien intente acreditarlos.
- `pago_presupuesto` (C-11): `registrado`/`anulado`, `fecha_cobro` con índice, y `app.clinica.service_pagos.resumen_por_dia_y_medio` como contrato para la caja. `fecha_cobro` puede ser anterior a hoy y un pago se anula en cualquier momento: sin una regla nueva, un día ya cerrado cambiaría.

**Turnos**
- `TRANSICIONES_TURNO` (`app/pagos/estados.py`) no tiene salida desde `atendido`; RN-TU-12 dice "nadie deshace un `atendido`". `cambiar_estado_turno` toma siempre los locks en el orden advisory de reservas → turno → pago.
- `atendido`, `reservado` y `confirmado` ocupan agenda (EXCLUDE de la 007): volver de `atendido` a `reservado` nunca puede chocar con otro turno.
- `alcance_paciente` (C-11) calcula el acceso de la odontóloga en cada pedido con los `atendido` existentes: no guarda nada.
- `disponibilidad` es por profesional y día de semana, con `sillon_defecto_id` opcional; `sillon` no tiene horario propio. No hay historial de disponibilidad ni tabla de feriados.
- `turno.paciente_id` solo se llena cuando recepción vincula el turno (C-11 O1): el ausentismo por paciente cuenta turnos vinculados; el general, todos.

**Panel**
- `GET /api/panel/pacientes` exige `dni` y devuelve una lista simple. `frontend-panel/` no tiene navegación: `App.tsx` muestra el ingreso o la agenda. `Accion = 'atendido' | 'ausente' | 'cancelar'` en backend y frontend.
- La limpieza de los tests borra filas con `DELETE` del ORM (`clean_db`); el E2E usa `TRUNCATE … CASCADE` con una lista fija de tablas.
- No hay efectivo (RN-PG-01): no existe un arqueo físico. La KB no define qué es una "liquidación" ni la "tasa de recupero".

## Goals / Non-Goals
**Goals**
- Una caja diaria determinística: el mismo día da siempre los mismos importes una vez cerrado.
- Cierre inmutable con una vía de corrección explícita y auditada.
- Cerrar los dos estados colgados de la seña (`en_revision`, `a_reembolsar`) sin tocar el camino del webhook.
- Corregir un `atendido` equivocado sin efectos sobre el dinero ni sobre el anti-solape.
- Indicadores calculados en una consulta por pantalla, sin tablas de agregados.

**Non-Goals**
- Honorarios por profesional, liquidación a obras sociales y comisiones (no hay reglas en la KB).
- Reembolsos automáticos por la API de Mercado Pago. Efectivo y arqueo físico.
- Que el barrido resuelva solo los `en_revision` vencidos (se listan y se resuelven a mano).
- Pantallas de alta, edición y vínculo de pacientes (C-16). Exportación y auditoría por middleware (C-13).
- Deshacer un `ausente` (O10).

## Decisions

### D1. Módulos y rutas
Todas las rutas son `recepcion`/`admin` (`require_recepcion_o_admin`), salvo la anulación de un cierre, que es solo `admin` (`require_role("admin")`).

| Ruta | Módulo | Spec |
|---|---|---|
| `GET /api/panel/caja?dia=` | `app/caja/` | `caja/movimientos-caja` |
| `GET /api/panel/caja/pendientes` | `app/pagos/devoluciones.py` | `pagos/devoluciones-sena` |
| `POST /api/panel/caja/revisiones/{pago_id}/rechazar` | ídem | ídem |
| `POST /api/panel/caja/devoluciones/senas/{pago_id}` | ídem | ídem |
| `POST /api/panel/caja/devoluciones/excedentes/{id}` | ídem | ídem |
| `POST /api/panel/caja/cierres` · `GET …/cierres` · `GET …/cierres/{id}` · `POST …/cierres/{id}/anular` | `app/caja/cierres.py` | `caja/cierre-caja` |
| `GET /api/panel/caja/liquidacion?desde=&hasta=` | `app/caja/cierres.py` | ídem |
| `GET /api/panel/ocupacion` · `GET /api/panel/ausentismo` | `app/panel/indicadores.py` | `turnos/indicadores-panel` |
| `POST /api/panel/turnos/{id}/deshacer-atendido` | `app/pagos/service.py` + `app/panel/router.py` | `turnos/gestion-panel` |
| `GET /api/panel/pacientes/listado` | `app/pacientes/listado.py` | `pacientes/registro-paciente` |

- `app/caja/`: `models.py` (`CierreCaja`, `CierreCajaLinea`), `calculo.py` (puro: agrupar movimientos, comparar cierre contra actual), `service.py` (movimientos del día), `cierres.py`, `schemas.py`, `errores.py`, `router.py`. El router de caja incluye las rutas de pendientes para que todo viva bajo `/api/panel/caja`.
- `GET /pacientes/listado` se declara **antes** de `GET /pacientes/{paciente_id}` para que "listado" no se interprete como id.
- CHANGES.md nombraba `POST /api/panel/caja/cierre`; se usa el plural `cierres` porque el cierre es un recurso con consulta y anulación.
- Esquemas Pydantic `extra="forbid"` en todas las entradas (R15): por eso un `monto` o un `total_ingresos` enviados dan 422.

### D2. Caja del día (O4, O14)
Un movimiento es `(concepto, medio, importe, instante)`. El día es `[00:00, 24:00)` en `zona_clinica()` (`APP_TZ`), con los límites convertidos a UTC como hace `rango_utc` de C-08.

| Concepto | Signo | Filas | Instante | Importe |
|---|---|---|---|---|
| `sena` | ingreso | `pago_sena` con `acreditado_en` no nulo y estado `acreditado`, `no_reembolsado`, `a_reembolsar` o `reembolsado` | `acreditado_en` | `COALESCE(monto_reportado, monto)` |
| `pago_presupuesto` | ingreso | `pago_presupuesto` `registrado` | `fecha_cobro` | `monto` |
| `devolucion_sena` | egreso | `pago_sena` `reembolsado` | `reembolsado_en` | el mismo importe del ingreso |

- El ingreso de una seña **no depende de su estado posterior**: cancelar, marcar ausente o devolver no cambia el día en que entró el dinero. Por eso un cierre sigue cuadrando después de esos cambios, y por eso la seña de un ausente "queda en caja" (R9): `senas_retenidas` es solo una lectura de cuántas señas del día están hoy `no_reembolsado`.
- Un pago tardío (`a_reembolsar` sin haber estado `acreditado`) entra como ingreso el día en que llegó y sale como egreso el día en que se devuelve: neto cero, y el dinero nunca queda invisible.
- `COALESCE(monto_reportado, monto)`: si recepción aceptó un pago informado por 2999.99, eso es lo que entró.
- Para que todo `a_reembolsar` tenga instante, C-12 sella `acreditado_en = ahora` en el único camino que no lo hacía (`en_revision` → `a_reembolsar` al cancelar la pre-reserva) y en el rechazo nuevo; la migración rellena las filas existentes con `updated_at`.
- Fuera de los totales: `pendiente`, `vencido`, `en_revision` (dinero sin reconocer) y los pagos excedentes (nunca fueron una seña). Se ven en la lista de pendientes.
- Se reutiliza la consulta de C-11 (`resumen_por_dia_y_medio`) para los totales de presupuestos; las señas y las devoluciones usan consultas ORM equivalentes con `func.timezone` (R14). Tres agregados más el detalle: sin N+1.
- La consulta se audita como `lectura_caja` con el día (RN-CL-03 incluye los pagos de presupuesto), sin importes de personas.

### D3. Cierre de caja (O1, O2)
- **Un cierre por día de la clínica, solo de días terminados.** `cerrable_desde = 00:00 del día siguiente + 15 min` (constante `MARGEN_CIERRE`). El margen cubre una acreditación que tomó su `ahora` a las 23:59:59 y confirma unos segundos después. Con esto, ninguna acreditación (que siempre usa `ahora`) puede caer en un día cerrado: no hace falta tocar el webhook.
- **Snapshot.** `cierre_caja` guarda día, totales, quién y cuándo; `cierre_caja_linea` una fila por `(concepto, medio)` con cantidad y total. El servidor calcula todo dentro de la transacción del cierre con las mismas funciones de D2.
- **Inmutabilidad en tres capas:** (1) la API no tiene rutas de edición ni borrado; (2) `CHECK (total_neto = total_ingresos - total_egresos)` y coherencia de la anulación; (3) un trigger `BEFORE UPDATE` rechaza cualquier cambio en `cierre_caja_linea` y, en `cierre_caja`, todo cambio que no sea la transición `vigente → anulado` con sus tres campos. No se bloquea `DELETE` en la base porque la limpieza de tests lo necesita; ninguna ruta borra.
- **Un vigente por día:** índice único parcial `(dia) WHERE estado = 'vigente'`. Dos cierres simultáneos: el segundo recibe 23505 → 409 `dia_ya_cerrado`.
- **Día cerrado = sin movimientos nuevos.** Función única `exigir_dia_abierto(session, instante)` que levanta `CajaCerradaError(dia)` si el día local de `instante` tiene un cierre vigente. La llaman: registrar pago de presupuesto (por `fecha_cobro`), anular pago de presupuesto (por la `fecha_cobro` del pago) y registrar devolución (por la fecha de devolución).
- **Serialización.** Cierre, anulación de cierre y las tres operaciones anteriores toman primero `pg_advisory_xact_lock(LOCK_CAJA)`. Orden global de locks: `LOCK_CAJA` → (turno → pago_sena | presupuesto). Los caminos de C-06 (advisory de reservas → turno → pago) nunca toman `LOCK_CAJA`, así que no hay ciclo.
- **Corrección.** `POST …/cierres/{id}/anular` (solo admin, motivo 3–300): `vigente → anulado`, el día vuelve a estar abierto, se corrige y se cierra de nuevo. El cierre anulado queda como historia.
- **Cuadra.** `GET …/cierres/{id}` recalcula los movimientos del día y los compara con las líneas (`calculo.comparar`): `cuadra` y `diferencias`. Con el bloqueo anterior, una diferencia solo puede venir de un cambio hecho fuera de la aplicación o de un defecto: es un detector, no un flujo. Un cierre anulado informa `cuadra: null`.

### D4. Liquidación (O3) — [SUPUESTO]
La KB nombra "liquidaciones" sin definirlas. Se adopta la lectura que no inventa reglas: la liquidación es el **consolidado por medio de pago** de los cierres vigentes de un rango (ingresos, egresos, neto y detalle por concepto), que es lo que recepción compara con la liquidación de Mercado Pago y con el extracto del banco. Informa los días del rango sin cierre vigente para que el total no se lea como completo. No calcula honorarios ni obras sociales.

### D5. Pendientes de la seña (O5, O6)
- **Unidad de devolución.** (a) Tipo `sena`: `pago_sena.estado = 'a_reembolsar'`, importe `COALESCE(monto_reportado, monto)`. (b) Tipo `excedente_mp`: `pago_sena_aprobacion.estado = 'a_reembolsar'` cuyo `mp_payment_id` es **distinto** del `mp_payment_id` de su `pago_sena` (el pago propio de la seña ya está cubierto por (a)). Importe `monto_reportado`; si es nulo, `importe_a_verificar`.
- **Registrar devolución de seña:** `LOCK_CAJA` → turno → pago `FOR UPDATE`; exige `a_reembolsar`; `exigir_dia_abierto(fecha)`; `acreditado_en ≤ fecha ≤ ahora`; pasa a `reembolsado` con `reembolsado_en`, `reembolsado_por_usuario_id`, `reembolso_referencia`. Además marca `reembolsado` la aprobación propia (`mp_payment_id` igual) si estaba `a_reembolsar`. `reembolsado` es final.
- **Registrar devolución de excedente:** solo cambia la aprobación; no toca seña, turno ni caja.
- **Rechazar revisión:** orden de locks de C-06 (advisory de reservas → turno → pago); exige `en_revision`; pasa a `a_reembolsar`, sella `acreditado_en = ahora`, deja las aprobaciones `en_revision` del pago en `a_reembolsar`. **No cambia el turno:** si sigue `en_espera`, vence solo o la persona paga de nuevo. Como `ahora` es siempre de un día abierto, no necesita `LOCK_CAJA`.
- **Aceptar revisión:** el endpoint de C-06, sin cambios. La pantalla lo llama desde la lista de pendientes.
- **R9:** `no_reembolsado` nunca es una devolución pendiente; registrar su devolución da 409 `no_es_devolucion_pendiente`.
- Estado nuevo `reembolsado` en los dos `CHECK`, con `CHECK` de coherencia (`reembolsado` ⇔ fecha y referencia presentes). La agenda ya devuelve `sena.estado` como texto: el panel suma la etiqueta "Seña devuelta".

### D6. Deshacer un `atendido` (O7, O8, O9)
- **Función propia, no una transición más.** `TRANSICIONES_TURNO` no cambia: la vía general sigue rechazando salir de `atendido`. `deshacer_atendido(session, turno_id, usuario_id, motivo, ahora)` en `app/pagos/service.py` toma los mismos locks (advisory de reservas → turno), exige `estado == 'atendido'` (si no, `TransicionInvalidaError`) y `ahora ≤ inicio + VENTANA_DESHACER_ATENDIDO` (7 días; si no, `PlazoVencidoError(limite)`), y deja `reservado`. Con el mismo reintento ante deadlock que `cambiar_estado_turno`.
- **Vuelve siempre a `reservado`**, aunque antes fuera `confirmado` (precedente RN-TU-10). No se lee la auditoría para reconstruir estados.
- **Seña y agenda:** no cambian. No hay EXCLUDE que pueda fallar.
- **Motivo de catálogo** (`turno_equivocado`, `paciente_no_asistio`, `otro`): se puede auditar sin riesgo de texto libre con datos personales.
- **Auditoría:** `UPDATE turno` con `antes {estado: atendido}`, `despues {estado: reservado, origen: deshacer_atendido_panel, motivo}`. Sin eventos (precedente C-08 O15).
- **Agenda:** `Accion` suma `deshacer_atendido`; `acciones_permitidas` la devuelve con permiso `total`, estado `atendido` y dentro del plazo. `ESTADOS` finales `ausente` y `cancelado` siguen sin acciones.
- **Acceso clínico:** no hay nada que revertir. `alcance_paciente` vuelve a calcular y el `atendido` deshecho deja de contar; lo escrito queda (odontograma solo de alta, ficha con `actualizado_por`). El diálogo lo avisa.

### D7. Indicadores (O11, O12)
- **Cálculo puro** en `app/panel/calculo_indicadores.py`: `minutos_de_atencion(franjas)` (unión de intervalos), `porcentaje(ocupados, atencion)` (half-up a dos decimales, `None` si la atención es 0) y `tasa(ausentes, atendidos)`.
- **Ocupación:** una consulta agrupa por sillón, día local del inicio y estado (`SUM(fin - inicio)`, `COUNT`), filtrando `estado IN ('reservado','confirmado','atendido','ausente')`; otra trae las franjas activas. El armado por día y sillón es en memoria (≤ 31 días × sillones). Usa `ix_turno_sillon_inicio`. `ESTADOS_BLOQUEANTES` es la única fuente de "ocupa agenda": `en_espera` queda fuera por construcción (R8).
- **Ausentismo:** una consulta agrupa por profesional y estado los turnos con inicio en el rango, con `LEFT JOIN` a la seña `no_reembolsado` para el recupero; `sin_marcar` = `reservado`/`confirmado` con `fin < ahora`.
- Sin auditoría de lectura: son agregados sin datos de personas.

### D8. Listado de pacientes (O13)
- Ruta nueva; `?dni=` no cambia. `q` se normaliza (`strip`, espacios simples) y se busca con `unaccent(lower(...)) LIKE` sobre `nombre || ' ' || apellido`, `apellido || ' ' || nombre` y `dni LIKE q || '%'` cuando `q` son dígitos. Los comodines de `q` se escapan. Vía ORM (`func.unaccent`), sin SQL crudo (R14).
- Contadores con una subconsulta agregada por `paciente_id` (`COUNT … FILTER`), unida con `LEFT JOIN`: una sola consulta más el `COUNT` del total.
- Sin índice de texto: una clínica tiene miles de pacientes, no millones (SU-02). Si creciera, `pg_trgm`.
- No se audita la lectura (C-11 tampoco audita `GET /pacientes?dni=` ni `GET /pacientes/{id}`; la auditoría transversal es de C-13) y **el texto buscado no se guarda en ningún log**.

### D9. Migración `009_caja_cierres_devol` (archivo `009_caja_cierres_devoluciones.py`; R4, R6, R14)
Id de 22 caracteres (`alembic_version.version_num` es `VARCHAR(32)`). `down_revision = "008_ficha_odonto_presup"`.
- `CREATE EXTENSION IF NOT EXISTS unaccent`.
- `cierre_caja`: `id BIGINT GENERATED ALWAYS AS IDENTITY`, `dia DATE NOT NULL`, `estado TEXT` (`vigente`/`anulado`), `total_ingresos`, `total_egresos`, `total_neto NUMERIC(14,2)` (`≥ 0` los dos primeros; `CHECK` de la resta), `observaciones TEXT NULL ≤ 500`, `cerrado_por` (FK `usuario`, `SET NULL`, índice), `cerrado_en TIMESTAMPTZ`, `anulado_por` (FK, índice), `anulado_en`, `anulado_motivo` (3–300), `CHECK` de coherencia de la anulación. Índice único parcial `(dia) WHERE estado = 'vigente'` e índice `(dia)`.
- `cierre_caja_linea`: `cierre_id` (FK `RESTRICT`), `concepto` (`sena`, `pago_presupuesto`, `devolucion_sena`), `medio` (`mercadopago`, `transferencia`), `cantidad INTEGER ≥ 0`, `total NUMERIC(14,2) ≥ 0`, `UNIQUE (cierre_id, concepto, medio)` (cubre la FK).
- Función y triggers de inmutabilidad (D3).
- `pago_sena`: `CHECK` de estado con `reembolsado`; `reembolsado_en TIMESTAMPTZ NULL`, `reembolsado_por_usuario_id` (FK, índice), `reembolso_referencia TEXT NULL` (3–64); `CHECK` de coherencia; índice parcial `(acreditado_en) WHERE acreditado_en IS NOT NULL`; índice parcial `(reembolsado_en) WHERE estado = 'reembolsado'`; índice parcial `(estado) WHERE estado IN ('a_reembolsar','en_revision')`.
- `pago_sena_aprobacion`: `CHECK` con `reembolsado` y las mismas tres columnas con su índice de FK.
- Relleno: `UPDATE pago_sena SET acreditado_en = updated_at WHERE estado = 'a_reembolsar' AND acreditado_en IS NULL`.
- `downgrade()`: devuelve los `reembolsado` a `a_reembolsar`, quita columnas, índices, triggers y tablas, restaura los `CHECK` y borra la extensión. Se pierden los cierres y los datos de devolución (avisar antes de producción).

### D10. Frontend (O16)
- **Navegación sin dependencias:** `lib/ruta.ts` lee y escribe `location.hash` (`#/agenda`, `#/pacientes`, `#/indicadores`, `#/caja`); `Navegacion.tsx` muestra las secciones solo si `opciones.puede_escribir` es verdadero. La odontóloga sigue viendo solo la agenda.
- **Pantallas:** `Pacientes.tsx`, `Indicadores.tsx` (`Ocupacion`, `Ausentismo`), `Caja.tsx` (`ResumenCaja`, `PendientesCaja`, `CierreCaja`), y el diálogo de corrección dentro de `AccionesTurno.tsx`. Componentes definidos a nivel de módulo, estado derivado en el render.
- **R2:** `Caja` pide resumen y pendientes con `Promise.all`; `Indicadores` pide ocupación y ausentismo en paralelo con un límite de error por bloque (una falla no tapa a la otra).
- **Importes:** llegan como texto decimal y se formatean con `Intl.NumberFormat('es-AR')`; nunca se suman en el navegador con `number`.
- **Día de la clínica:** se reutiliza `lib/tiempo.ts` (los tests ya corren en zona Tokio).
- **Estilo (skill `frontend-design`):** tablas y barras horizontales simples con el número y el texto siempre visibles, sin tarjetas de números grandes; mensajes de error que dicen qué pasó y cómo seguir; foco visible; 360 px.
- **Stitch:** si hay credencial (`STITCH_ACCESS_TOKEN`), prototipar Caja e Indicadores a 360 px antes de codear y guardar la evidencia en `docs/skills-mcp/evidencia-stitch/`; si no, se omite sin bloquear.

### D11. Estrategia de pruebas (Strict TDD)
- **Unit (sin base):** `caja/calculo.py` (agrupar, totales, comparar), `calculo_indicadores.py` (unión de franjas, porcentaje half-up, tasa con denominador 0), `estados.py` (`deshacer_habilitado_hasta`: 7 días exactos y +1 s), `acciones.py` (acción nueva por permiso y plazo), esquemas (`extra="forbid"`, rangos, `q`).
- **Integración (pytest + PostgreSQL real):** migración 009 arriba/abajo/arriba con relleno; caja por día con límites de zona; ausente retiene seña; cierre (margen, único, simultáneo con `asyncio.gather`, trigger, cuadra, anulación por rol); bloqueo `caja_cerrada` en pagos de presupuesto y devoluciones; pendientes, rechazo, devolución y excedentes; deshacer (plazo, roles, concurrencia, acceso clínico); indicadores (`en_espera` excluida); listado de pacientes. Reloj inyectable `get_reloj` en todas las rutas nuevas.
- **E2E Playwright (R7), 360 px y 1280 px:** ausente → seña retenida en caja; deshacer un `atendido` desde la agenda; cierre de caja y aviso de que cuadra; registrar una devolución; indicadores con una pre-reserva que no ocupa; búsqueda de pacientes.
- **Red de seguridad:** las suites de C-06, C-08 y C-11 corren antes de tocar `pagos/service.py`, `panel/acciones.py` y `clinica/service_pagos.py`.

## Decisiones del usuario (aprobadas el 2026-11-11)

**Aprobación (2026-11-11):** el usuario aprobó la opción recomendada (a) de O1–O16; ninguna cambia los specs ni las tareas. Aclaraciones pedidas por el usuario: O2 se confirma (el bloqueo rige por la fecha del movimiento: la devolución de una seña un día posterior es un egreso de ese día posterior) y O6 se confirma (rechazar un `en_revision` NO cancela el turno). Governance ALTO: **nada de dinero ni de estados se implementa antes de que el usuario apruebe esta tabla.** Se puede responder "recomendada" para todas o ajustar las que haga falta; los specs y las tareas reflejan la opción recomendada. Criticidad ALTA = dinero, estados del turno o datos de salud.

| # | Criticidad | Pregunta | Decisión final (2026-11-11) | Alternativas |
|---|---|---|---|---|
| O1 | ALTA | ¿Cómo se modela el cierre de caja y qué lo hace inmutable? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Un cierre por día de la clínica, solo de días terminados (desde las 00:15 del día siguiente); foto en `cierre_caja` + líneas; sin edición ni borrado por API; un trigger rechaza cambios de importes; corregir = anular (con motivo) y volver a cerrar | (b) cierre por corte horario, varios por día, cada uno desde el corte anterior; (c) el cierre es solo una marca, sin foto de importes |
| O2 | ALTA | ¿Qué significa que el cierre "cuadra" y cómo se protege? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Cuadra si las líneas suman los totales y coinciden con los movimientos del día recalculados al consultar; mientras el día esté cerrado se rechaza con 409 `caja_cerrada` registrar o anular cobros de presupuesto y registrar devoluciones con fecha en ese día. **Cambia C-11**: anular un pago de un día cerrado exige anular antes el cierre | (b) además, importe declarado por medio (extracto de MP y del banco) con diferencia y observación obligatoria; (c) solo guardar la foto, sin verificación ni bloqueo |
| O3 | ALTA | ¿Qué es una "liquidación"? La KB no la define **[SUPUESTO]** | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** El consolidado por medio de pago y concepto de los cierres de un rango, para conciliar con Mercado Pago y el banco; sin honorarios ni obras sociales | (b) honorarios por profesional (necesita porcentaje de comisión y a quién se atribuye cada cobro: change nuevo); (c) lo que se factura a cada obra social por cobertura; (d) no entregar liquidaciones en C-12 |
| O4 | ALTA | ¿Qué entra en la caja de un día? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Ingresos: señas por el día en que se recibió el dinero (sin importar si después se canceló, faltó o se devolvió; importe recibido) y cobros de presupuesto `registrado` por fecha de cobro. Egresos: devoluciones por su fecha. La seña de un ausente sigue como ingreso y se muestra retenida. `en_revision` y excedentes, fuera de los totales | (b) solo señas que hoy siguen `acreditado` o `no_reembolsado` (el pasado cambia al cancelar); (c) señas por la fecha del turno y no del cobro |
| O5 | ALTA | ¿Cómo se resuelve un `a_reembolsar`? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Estado nuevo `reembolsado` en la seña y en el registro de pagos de la pasarela; recepción o admin registra la devolución hecha con referencia obligatoria y fecha; el importe lo fija el sistema; es final. Los pagos excedentes de Mercado Pago se devuelven por separado y no mueven la caja. Sin tocar el webhook | (b) tabla nueva "libro de devoluciones" con una fila por importe adeudado, modificando los cinco puntos de C-06 donde nace un `a_reembolsar`; (c) solo a nivel seña, los excedentes quedan fuera de C-12 |
| O6 | ALTA | ¿Cómo se resuelve un `en_revision`? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Se lista; se acepta con la acreditación manual de C-06 (sin cambios) o se **rechaza** (nuevo) y queda `a_reembolsar`; rechazar no cancela el turno; los de pre-reservas ya vencidas se listan y se resuelven a mano | (b) además, que el barrido pase solos a `a_reembolsar` los de turnos vencidos (toca C-06); (c) rechazar también cancela la pre-reserva |
| O7 | ALTA | ¿Quién deshace un `atendido` y a qué estado vuelve? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Recepción y admin; vuelve siempre a `reservado`; motivo de un catálogo; auditado; la odontóloga no deshace (C-11 O15 se mantiene); la seña no cambia; sin avisos. **Enmienda RN-TU-12** | (b) solo admin; (c) vuelve al estado exacto anterior (`confirmado` o `reservado`) leyendo la auditoría |
| O8 | ALTA | ¿Hasta cuándo se puede deshacer? **[SUPUESTO]** | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Hasta 7 días corridos desde el inicio del turno (exactamente 7 días se acepta) | (b) sin límite; (c) solo el mismo día de la clínica |
| O9 | ALTA | ¿Qué pasa con el acceso clínico de la odontóloga (C-11 O2/O16)? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Se recalcula solo: si era su única atención pierde el acceso (403 `paciente_ajeno`); lo que escribió queda con su autoría; el diálogo lo avisa; no se bloquea la corrección | (b) impedir deshacer si hubo escrituras clínicas después del marcado; (c) conservarle la lectura |
| O10 | Media | ¿También se deshace un `ausente`? (alguien que llegó tarde) | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** No en C-12: devolvería una seña retenida a `acreditado` (R9); queda como seguimiento | (b) sí, con las mismas reglas, y la seña vuelve a `acreditado` |
| O11 | Media | ¿Cómo se mide la ocupación? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Por sillón y día de la clínica: minutos de turnos `reservado`/`confirmado`/`atendido` que empiezan ese día sobre los minutos de atención (unión de las franjas activas de ese día de semana); `en_espera` y `cancelado` no cuentan; `ausente` se informa aparte; sin atención, porcentaje vacío; hasta 31 días. Usa la disponibilidad actual, no la histórica | (b) solo minutos, sin porcentaje; (c) capacidad = franjas que tienen ese sillón por defecto |
| O12 | Media | ¿Cómo se miden el ausentismo y el recupero? **[SUPUESTO sobre "tasa de recupero"]** | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Ausentismo = ausentes ÷ (atendidos + ausentes) por inicio del turno, total y por profesional, informando los `sin_marcar`. Recupero = señas retenidas: cantidad, importe y porcentaje de ausentes con seña retenida | (b) denominador = todos los turnos que ocuparon agenda; (c) recupero = ausentes que volvieron a reservar |
| O13 | Media | ¿Cómo se listan y buscan pacientes? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Ruta nueva `GET /api/panel/pacientes/listado`, paginada, con búsqueda por nombre, apellido o comienzo del DNI sin distinguir mayúsculas ni acentos (extensión `unaccent`), contadores de atendidos y ausentes de turnos vinculados y filtro «con ausencias»; `?dni=` no cambia; el texto buscado no se registra | (b) cambiar `GET /pacientes` a respuesta paginada (rompe el contrato de C-11); (c) sin `unaccent` (distingue acentos) |
| O14 | Media | ¿Qué es "el día" para la caja y los indicadores? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** El día calendario de `APP_TZ` (America/Argentina/Buenos_Aires), como en C-08 y C-11 | (b) día UTC; (c) jornada con hora de corte configurable |
| O15 | Media | ¿Quién accede? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Todo C-12 solo recepción y admin (la odontóloga, 403); anular un cierre, solo admin | (b) recepción también anula cierres; (c) la odontóloga ve la ocupación y el ausentismo de su profesional |
| O16 | Media | ¿Qué pantallas entran? | **Decisión final: (a) recomendada — aprobada por el usuario 2026-11-11.** Navegación por secciones sin dependencias nuevas (Agenda, Pacientes, Indicadores, Caja), visibles solo para recepción y admin; Pacientes = listado, búsqueda y ausencias; alta, edición y vínculo de pacientes quedan en C-16 | (b) solo API en C-12 y las pantallas en un change nuevo (como C-11 con C-16); (c) sumar acá alta, edición y vínculo de pacientes |

**Reglas nuevas propuestas** (se redactan en `05_reglas_de_negocio.md` en el apply, con las opciones aprobadas):
- **RN-TU-12 (enmienda, O7–O9):** recepción y admin corrigen un `atendido` marcado por error hasta 7 días después del inicio; vuelve a `reservado`; la odontóloga no.
- **RN-CJ-01 (O4, O14):** qué es ingreso y egreso de la caja y a qué día pertenece. **RN-CJ-02 (O1):** un cierre vigente por día terminado, inmutable. **RN-CJ-03 (O2):** un día cerrado no admite movimientos; corregir exige anular el cierre (admin, con motivo). **RN-CJ-04 (O2):** el cierre cuadra si coincide con los movimientos recalculados. **RN-CJ-05 (O3) [SUPUESTO]:** la liquidación es el consolidado por medio de pago.
- **RN-SN-11 (O5, O6):** un `en_revision` se acredita o se rechaza; un `a_reembolsar` pasa a `reembolsado` cuando recepción registra la devolución con su referencia; `no_reembolsado` nunca se devuelve.
- **RN-IN-01 (O11)** ocupación por sillón. **RN-IN-02 (O12) [SUPUESTO]** ausentismo y recupero.

## Risks / Trade-offs
- [O3 y O12 interpretan términos que la KB no define] → marcados **[SUPUESTO]**, con alternativas; un test fija cada fórmula para que un cambio sea explícito.
- [El cierre solo se hace al día siguiente] → recepción cierra "ayer" a la mañana. Es el precio de que una acreditación de Mercado Pago a las 23:50 no quede fuera; la pantalla lo explica.
- [O2 cambia un contrato de C-11: anular un pago puede dar 409 `caja_cerrada`] → requisito nuevo en `pagos/pagos-presupuesto`; los tests de C-11 no cierran días, así que siguen en verde; el camino de corrección queda documentado.
- [Anular un cierre requiere admin] → una clínica con un solo usuario admin depende de esa persona; O15 (b) lo relaja.
- [`acreditado_en` significa "se recibió el dinero", no solo "se acreditó"] → ya era así en `_marcar_a_reembolsar`; se documenta en el modelo y se completa el camino faltante. Alternativa descartada: columna nueva `recibido_en` (duplica el dato).
- [Dos niveles de devolución (seña y excedente)] → la regla de D5 los separa por `mp_payment_id`; test con los siete casos reales (cancelación con transferencia, con MP, pago tardío, horario perdido, revisión cancelada, revisión aceptada tarde, excedente). Alternativa descartada por ahora: libro de devoluciones (O5 b), más claro pero toca cinco puntos del webhook.
- [Un excedente sin importe informado] → se marca `importe_a_verificar`; recepción lo mira en Mercado Pago.
- [Los `en_revision` de turnos vencidos siguen colgados hasta que alguien actúe] → ahora son visibles y se resuelven con un toque; automatizarlo es O6 (b).
- [Deshacer un `atendido` quita un acceso clínico ya usado] → lo escrito queda con autoría y auditoría; es el efecto buscado al corregir un error.
- [Marcar `atendido` y deshacer repetidamente] → cada vez queda auditada con usuario y motivo; plazo de 7 días.
- [La ocupación usa la disponibilidad actual para días pasados] → si se cambiaron franjas, el porcentaje histórico cambia; puede superar 100 %. Aceptado y documentado; no hay historial de disponibilidad.
- [El ausentismo por paciente depende de que recepción vincule los turnos] → el indicador general no depende de eso; la pantalla de vínculo es de C-16.
- [`unaccent` es una extensión] → incluida en la imagen oficial de PostgreSQL; la migración la crea y el downgrade la borra. Sin índice: volumen bajo.
- [Trigger de inmutabilidad] → solo `UPDATE`; no interfiere con la limpieza de tests. `TRUNCATE` del E2E suma las tablas nuevas.
- [`LOCK_CAJA` serializa cierres, cobros de presupuesto y devoluciones] → operaciones manuales y poco frecuentes; el webhook no lo toma.
- [No existe la devolución de un cobro de presupuesto] → C-11 solo permite anular un cobro por error de carga; no hay reembolso de un cobro real (egreso de caja por presupuesto). El usuario eligió dejarlo **fuera de C-12 como seguimiento** (registrar en CHANGES.md en el grupo 11). Mientras tanto, un cobro devuelto fuera del sistema no tiene reflejo en la caja.
- [Tamaño del change] → los grupos de tareas son independientes por capacidad y cada uno lleva sus tests; si el usuario elige O16 (b), los grupos de frontend pasan a un change nuevo sin tocar el resto.

## Migration Plan
1. Verificar con `ls backend/src/alembic/versions` que `009` sigue libre (C-09, C-10, C-14 o C-15 pueden correr en paralelo) y `alembic upgrade head`.
2. Deploy del backend: endpoints nuevos; dos respuestas nuevas en rutas existentes (409 `caja_cerrada`, acción `deshacer_atendido`).
3. Deploy de `frontend-panel/`.
4. **Rollback:** build anterior y `alembic downgrade -1` (se pierden cierres y datos de devolución; los `reembolsado` vuelven a `a_reembolsar`).

## Audit & Compliance Note (spec-rules-auditor)
Auditoría del 2026-11-11 sobre `proposal.md`, este `design.md` y los nueve deltas, contra `knowledge-base/05_reglas_de_negocio.md` y las reglas duras de `AGENTS.md`.

**Dictamen: OBSERVACIONES.** Los specs cubren cada regla afectada con su terna de escenarios (esperado, error de negocio, caso de borde), pero el change no puede darse por aprobado hasta que el usuario resuelva O1–O16: enmienda una regla vigente (RN-TU-12), cambia un contrato de C-11 (O2) y adopta tres supuestos sin fuente en la KB (O3, O8, O12).

| Regla | Estado | Dónde / observación |
|---|---|---|
| R8 / RN-SN-01 (`en_espera` no bloquea) | CUBIERTA | `indicadores-panel` "Solo cuentan los turnos que ocupan agenda" (pre-reserva → 0 minutos; al acreditarse → cuenta); rechazar una revisión no ocupa agenda |
| R9 / RN-SN-02 (ausente no se reembolsa) | CUBIERTA | `movimientos-caja` "La seña de un ausente queda retenida en caja"; `devoluciones-sena` (409 `no_es_devolucion_pendiente` sobre `no_reembolsado`); recupero en `indicadores-panel` |
| RN-GL-01 (auditoría de panel) | CUBIERTA | Auditoría de cierre, anulación, rechazo, devoluciones, corrección de `atendido` y `lectura_caja`; rechazos sin registro |
| RN-GL-02 (exportación) | FUERA DE ALCANCE | C-13 |
| RN-GL-03 / R3 | CUBIERTA | Las cuatro pantallas a 360 px |
| RN-TU-12 (marcado; "nadie deshace un `atendido`") | **CONTRADICHA DELIBERADAMENTE** | `gestion-panel` "Deshacer un atendido…" y delta MODIFIED de `sena-turno`. Requiere aprobar O7–O9 y enmendar el texto en el apply |
| RN-TU-03 / R5 (anti-solape) | NO AFECTADA | `atendido → reservado` no cambia la ocupación; sin cambios en los EXCLUDE |
| RN-TU-01/02 (24 h) | NO AFECTADA | Un turno corregido ya empezó: no se puede cancelar ni reprogramar |
| RN-SN-04, RN-SN-05 (`a_reembolsar`) | CUBIERTA | `devoluciones-sena` "Registro de la devolución de una seña" |
| RN-SN-09 (`en_revision`) | CUBIERTA | "Rechazar un pago en revisión"; aceptar = endpoint de C-06 |
| RN-SN-10 (pagos por id, excedentes) | CUBIERTA | "Devolución de pagos excedentes de Mercado Pago" |
| RN-SN-07 (vencimiento) | NO AFECTADA | El barrido no cambia; observación: no resuelve `en_revision` (O6 b) |
| RN-PG-01 (MP + transferencia) | CUBIERTA | Medios de la caja y de las líneas del cierre; sin efectivo |
| RN-PG-06 (pagos de presupuesto; anulación sin borrado) | AMPLIADA | `pagos-presupuesto` "Los cobros de un día cerrado…" (O2) |
| RN-PG-03 (sin ARCA) | NO AFECTADA | La liquidación no factura |
| RN-CL-02, RN-CL-04 (acceso clínico) | AFECTADA INDIRECTAMENTE | `gestion-panel` "Deshacer un atendido recalcula el acceso clínico" (O9) |
| RN-CL-03 (auditoría de pagos de presupuesto) | CUBIERTA | `lectura_caja` |
| Matriz RBAC (03): Caja/liquidaciones solo recepción/admin | CUBIERTA | 403 para `odontologo` en caja, cierres, pendientes, indicadores y listado; anular cierre solo admin (más estricto que la matriz, O15) |
| R1, R2 | CUBIERTAS | TypeScript estricto; cargas en paralelo en Caja e Indicadores |
| R4 | CUBIERTA | `NUMERIC(14,2)`, `TIMESTAMPTZ`, `TEXT` + `CHECK`; importes como texto decimal |
| R6 | CUBIERTA | Índice en cada FK nueva (D9) |
| R7 | CUBIERTA | E2E de ausente → caja, corrección de `atendido`, cierre, devolución, indicadores y pacientes |
| R13–R16, R18 | CUBIERTAS | Type hints, ORM, Pydantic `extra="forbid"`, async, Compose existente |
| R14 | CUBIERTA | `009` reversible; triggers y extensión solo en la migración |
| R17 | NO AFECTADA | Sin secretos nuevos |
| R19 / Ley 25.326 | CUBIERTA | Datos sintéticos ("Lucía Ejemplo", "Mateo Prueba", "Dra. Ana Ficticia", DNI `99xxxxxx`, `+54911000000xx`, referencias `TRF-SINT-…`, `DEV-SINT-…`); caja, pendientes e indicadores sin datos de personas; el texto buscado y el motivo de anulación no van a la auditoría |
| R11, R12, R20 | CUBIERTAS | Sin commits; archivos solo en `backend/`, `frontend-panel/` y docs canónicas |

**Supuestos marcados:** definición de liquidación (O3), plazo de 7 días (O8), "tasa de recupero" (O12).
**Observaciones:** (1) RN-TU-12 se contradice a propósito y necesita aprobación explícita; (2) O2 cambia un comportamiento de C-11; (3) el barrido no resuelve los `en_revision` vencidos (queda manual); (4) el ausentismo por paciente depende del vínculo de turnos, cuya pantalla es de C-16; (5) la ocupación histórica usa la disponibilidad actual.
**Gaps sin escenario:** ninguno.

### Re-auditoría final (2026-11-11, fin del apply)
Se re-auditaron los nueve deltas contra las reglas ya redactadas en `knowledge-base/05_reglas_de_negocio.md` (RN-TU-12 enmendada, RN-CJ-01 a RN-CJ-05, RN-SN-11, RN-IN-01 y RN-IN-02) y contra la implementación (backend, migración `009` y `frontend-panel/`).

**Dictamen: APROBADO.** Las tres observaciones que condicionaban el dictamen inicial quedaron cerradas: O1-O16 fueron aprobadas por el usuario el 2026-11-11 (RN-TU-12 se enmendó con su aprobación, O2 cambió el contrato de C-11 con tests de ambos lados y los tres supuestos están marcados **[SUPUESTO]** en la KB: RN-CJ-05, el plazo de 7 días de RN-TU-12 y RN-IN-02). Las observaciones (3), (4) y (5) siguen vigentes y documentadas como seguimiento o trade-off.

| Regla | Estado final | Evidencia |
|---|---|---|
| RN-TU-12 (enmendada: recepción/admin deshacen un `atendido` hasta 7 días; la odontóloga no) | CUBIERTA | `test_panel_deshacer_integration.py`, `test_panel_acciones.py`, matriz de roles, E2E `gestion.spec.ts` (deshacer y odontóloga sin el botón) |
| RN-CJ-01 (qué entra en la caja y a qué día) | CUBIERTA | `test_caja_calculo.py`, `test_caja_integration.py`, E2E `caja.spec.ts` (ausente → seña retenida; devolución como egreso) |
| RN-CJ-02 (un cierre vigente por día terminado, inmutable) | CUBIERTA | `test_cierre_caja_integration.py`, `test_caja_migracion.py` (trigger), E2E de cierre |
| RN-CJ-03 (día cerrado no admite movimientos; anular solo admin) | CUBIERTA | `test_cierre_caja_integration.py`, `test_pagos_presupuesto_integration.py`, `test_caja_rbac_matriz.py`, E2E (409 `caja_cerrada` por API) |
| RN-CJ-04 (el cierre cuadra) | CUBIERTA | `test_cierre_caja_integration.py`, `CierreCaja.test.tsx`, E2E "El cierre cuadra" |
| RN-CJ-05 [SUPUESTO] (liquidación = consolidado por medio) | CUBIERTA (supuesto) | `test_cierre_caja_integration.py` (liquidación); sin pantalla en C-12 |
| RN-SN-11 (acreditar o rechazar `en_revision`; `a_reembolsar` → `reembolsado`; `no_reembolsado` nunca) | CUBIERTA | `test_devoluciones_integration.py`, `test_devoluciones_flujos_integration.py`, `PendientesCaja.test.tsx`, E2E de devolución |
| RN-IN-01 (ocupación; `en_espera` no cuenta, R8) | CUBIERTA | `test_ocupacion_integration.py`, `test_indicadores_calculo.py`, E2E `indicadores.spec.ts` (pre-reserva 0 %, reservado con su porcentaje) |
| RN-IN-02 [SUPUESTO] (ausentismo y recupero) | CUBIERTA (supuesto) | `test_ausentismo_integration.py`, E2E de ausentismo con la seña retenida |
| R3 (360 px), R2 (cargas en paralelo), R1 | CUBIERTAS | E2E a 360 px y 1280 px de las cuatro secciones; `Caja`/`Indicadores` piden en paralelo (tests con promesas pendientes); `tsc` estricto sin `any` |
| R7 (E2E de cada flujo) | CUBIERTA | `pacientes.spec.ts`, `indicadores.spec.ts`, `caja.spec.ts`, `gestion.spec.ts` |
| R19 | CUBIERTA | Datos de fantasía en backend, frontend y E2E |

**Matriz sin reglas sin estado:** cada regla afectada figura CUBIERTA, FUERA DE ALCANCE (RN-GL-02, C-13) o NO AFECTADA. **Gaps sin escenario:** ninguno.
