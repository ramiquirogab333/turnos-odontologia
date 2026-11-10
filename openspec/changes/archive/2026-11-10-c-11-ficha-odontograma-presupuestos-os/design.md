# Design: c-11-ficha-odontograma-presupuestos-os

## Context
La motivación está en `proposal.md` y los requisitos en los specs de este change (cinco capacidades nuevas y tres modificadas). Esto es lo que se verificó en el código (rama `feat/c-11-ficha-odontograma-presupuestos-os`, última migración `007_turno_origen_ocupacion`) y condiciona el diseño:

**Pacientes**
- `Paciente` (002) exige `dni` único (`^[0-9]{7,8}$`), `nombre`, `apellido`, `telefono`; `obra_social_id` y `numero_afiliado` opcionales. **No existe ningún endpoint de pacientes**, aunque el escenario RBAC de `auth/panel-login` ya cita `POST /api/panel/pacientes` y `PUT /api/panel/pacientes/{id}`.
- `turno.paciente_id` existe (nullable, FK `RESTRICT`, índice `ix_turno_paciente_inicio`), pero **ningún turno lo llena**: la reserva pública y el alta manual guardan `contacto_nombre`/`contacto_telefono` porque la reserva no pide DNI (RN-TU-06, C-08 O8).

**Cobertura**
- `nomenclador` (002) es por `(obra_social_id, tratamiento_id)` único, con `codigo_prestacion`, `cobertura_porcentaje NUMERIC(5,2)` 0–100 y `arancel_diferencial NUMERIC(10,2) ≥ 0`. El seed aplica un % único por obra social a todos los tratamientos (OSDE 100, Swiss 90, Galicia 80, Omint 85, Particular 0) y `arancel_diferencial = 0`. `obra_social` tiene `is_active`; `tratamiento.precio_base NUMERIC(10,2)`.
- Nada en el código consume el nomenclador todavía.

**Panel, roles y auditoría**
- `resolver_alcance` (`app/panel/service.py`) aplica "el permiso más amplio gana" y obtiene `usuario.profesional_id` de la base. `require_recepcion_o_admin` vive en `app/catalogo/router.py`.
- `registro_auditoria` guarda `usuario_id`, `accion` (2–50), `entidad` (2–50), `entidad_id`, `datos_antes`/`datos_despues` JSONB. C-08 fijó la convención: auditar en la misma transacción y sin PII.
- **Cambios de estado (C-08):** `POST /api/panel/turnos/{id}/atendido|ausente|cancelar` usan `Depends(require_recepcion_o_admin)` (`app/panel/router.py`); `marcar_turno` (`app/panel/service.py`) delega en `cambiar_estado_turno` (`app/pagos/service.py`), que toma el turno con `FOR UPDATE`, valida la transición (`reservado`/`confirmado` → final) y `habilitado_desde` (atendido: 00:00 del día local, RN-TU-12) y audita con origen `marcado_atendido_panel` y el `usuario_id` del actor. Errores: 404 `TurnoInexistenteError`, 409 `transicion_invalida` / `marcado_no_habilitado`. `acciones_permitidas(…, puede_escribir, …)` (`app/panel/acciones.py`) devuelve `[]` sin permiso de escritura, y `Alcance.puede_escribir` también gobierna el teléfono de la agenda y `opciones.puede_escribir` (botón «Nuevo turno»). El panel React muestra las acciones que informa el servidor sin mirar el rol (`AccionesTurno.tsx`). Tests que hoy fijan la regla vieja: `test_panel_estados_integration.py::test_odontologo_es_403_y_sin_token_es_401_y_no_cambia_nada`, `test_panel_acciones.py` (`escribe=False → []`), `test_panel_agenda_integration.py::test_la_odontologa_no_recibe_acciones_aunque_el_turno_haya_empezado` y el E2E `frontend-panel/e2e/agenda.spec.ts` ("sin acciones de escritura").
- Tests: `conftest.py` ya da `token_recepcion`, `token_admin`, `crear_usuario_panel`, `reloj`, `clean_db`, `seed_ids`; `panel_helpers.sembrar_mundo` e `insertar_turno` arman profesionales, turnos y franjas.

**Inconsistencias KB ↔ código detectadas** (se resuelven con las decisiones de abajo y tareas de docs del grupo 10):
1. DD-09 / C-08 O8 dice que el alta de `Paciente` "llega en C-12", pero C-11 no puede tener ficha sin paciente (→ O1).
2. `04_modelo_de_datos.md` §Paciente describe teléfono como identificador y un campo `notas`; el código exige DNI único y no tiene `notas`.
3. El ERD pone `Ficha ───* Odontograma / Presupuesto`, pero §Presupuesto define `paciente_id` (→ D2: todo cuelga de `paciente_id`).
4. §ObraSocial/Nomenclador modela una sola entidad con "cobertura"; el código tiene dos tablas y un `arancel_diferencial` sin semántica documentada (→ O9).
5. La matriz RBAC dice "odontólogo: lectura (sus pacientes)" sin definirlo (→ O2); US-009 asigna la carga del odontograma a recepción/admin (→ O4). **O4 aprobada contradice ambas: ver D11.**
6. US-010 (cobrar presupuestos) no está asignada a ningún change: C-06 la usó "extendida al turno" (→ O12).
7. El "nomenclador AR precargado" del seed es un placeholder sintético con un % por obra social, no un nomenclador real por prestación.
8. RN-TU-12, la nota de C-08 en `03_actores_y_roles.md` y C-08 O5 dicen que solo recepción/admin marcan `atendido`; la decisión del usuario del 2026-11-10 deja que la odontóloga marque sus turnos (→ O15, D12).
9. La KB no limita en el tiempo el acceso de la odontóloga a "sus pacientes" (→ O16, D2).

## Goals / Non-Goals

**Goals:**
- Cálculo de cobertura como función pura con `Decimal`, probado exhaustivamente antes de tocar la base.
- Un único punto de control de acceso por paciente (`alcance_paciente`) reutilizado por ficha, odontograma, presupuestos y pagos.
- Historia clínica que no se pisa: odontograma solo de alta y ficha con control de versión.
- Pagos de presupuesto con invariantes en la base (`CHECK`, índice único parcial) y serialización por fila, listos para que C-12 los sume.

**Non-Goals:**
- UI (C-16, O13). Listado y búsqueda libre de pacientes, ausentismo y caja (C-12). Exportación y auditoría transversal por middleware (C-13).
- Checkout online de presupuestos, facturación ARCA (RN-PG-03), firma digital, adjuntos o imágenes clínicas.
- Editar el nomenclador o las obras sociales desde la API (siguen por seed; C-14 o posterior).
- Fusionar pacientes duplicados o borrar pacientes.

## Decisions

### D1. Módulos y rutas
Siguiendo `08_arquitectura_propuesta.md` (`pacientes/`, `clinica/`), con el estilo de `app/panel/` (`schemas.py` con `extra="forbid"`, `service.py`, `router.py`, R15):

| Ruta (`/api/panel`) | Recepción/admin | Odontóloga (sus pacientes: ≥ 1 turno `atendido` con ella, O2) | Odontóloga (paciente ajeno) |
|---|---|---|---|
| `POST /pacientes` · `GET /pacientes?dni=` | sí | 403 | 403 |
| `GET /pacientes/{id}` | completo (`PacienteOut`) | `PacienteVistaClinicaOut`: nombre, apellido, DNI, obra social, número de afiliado; sin teléfono ni email (O3) | 403 `paciente_ajeno` |
| `PUT /pacientes/{id}` | sí | 403 | 403 |
| `PUT /turnos/{turno_id}/paciente` | sí | 403 | 403 |
| `GET /pacientes/{id}/ficha` · `PUT …/ficha` | lee y escribe | **lee y escribe** (O4, con `version`/409 de O6) | 403 `paciente_ajeno` |
| `GET …/odontograma` · `GET …/odontograma/historial` · `POST …/odontograma` | lee y escribe | **lee y escribe** (O4, solo de alta, O7) | 403 `paciente_ajeno` |
| `GET …/presupuestos` · `GET …/presupuestos/{pid}` | lee | lee sin pagos ni saldo (`PresupuestoVistaClinicaOut`) | 403 `paciente_ajeno` |
| `POST …/presupuestos` · `PUT …/presupuestos/{pid}` · `POST …/{presentar\|aceptar\|rechazar\|anular}` | sí | 403 | 403 |
| `GET/POST …/presupuestos/{pid}/pagos` · `POST …/pagos/{pago_id}/anular` | sí | 403 | 403 |

En la ficha y el odontograma, "lee y escribe" de la odontóloga vale con acceso clínico **completo**; con acceso de **solo lectura** (O16, D2) las lecturas responden igual y las escrituras 403 `acceso_clinico_vencido`. Fuera de esta tabla, `POST /turnos/{id}/atendido` pasa a aceptar a la odontóloga sobre los turnos de su profesional (O15, D12); `ausente`, `cancelar` y el alta manual siguen en 403.

Las escrituras de presupuestos, pagos, datos del paciente y vínculos responden 403 a cualquier odontóloga pura **antes** de evaluar el alcance (dependencia `require_recepcion_o_admin`), así una odontóloga no puede sondear si un paciente es suyo. En las rutas de lectura y de escritura clínica se valida primero la existencia del paciente (404) y después el alcance (403).

- `app/pacientes/`: modelo `Ficha`, registro de pacientes, vínculo de turnos, ficha y `alcance_paciente`.
- `app/clinica/`: modelos `OdontogramaRegistro`, `Presupuesto`, `PresupuestoLinea`, `PagoPresupuesto`; módulos puros `odontograma.py` (catálogo y vigente), `calculo.py` (importes) y `estados.py` (transiciones); servicios y router.
- `require_recepcion_o_admin` se mueve a `app/auth/rbac.py` (re-exportado desde `catalogo/router.py` para no romper imports).
- Errores con cuerpo `ErrorPanelBody` (`detail`, `motivo`) como en C-08: `paciente_ajeno`, `acceso_clinico_vencido`, `turno_ajeno`, `dni_duplicado`, `obra_social_inactiva`, `version_desactualizada`, `presupuesto_no_editable`, `transicion_invalida`, `presupuesto_con_pagos`, `presupuesto_no_aceptado`, `monto_excede_saldo` (con `saldo`), `referencia_duplicada`.

### D2. Alcance por paciente (O2, O3, O4, O16)
`alcance_paciente(session, contexto, paciente_id, ahora) -> AlcancePaciente(nivel, escribe_clinica, escribe_administrativo, ve_contacto, ve_pagos)`, con `nivel` en `{"total", "clinico_completo", "clinico_lectura"}` y `ahora` de `get_reloj` (UTC con zona, R4):
1. Paciente inexistente → `PacienteInexistenteError` (404). Se valida **antes** que el alcance para no filtrar existencia por timing de auditoría (no se audita un 404).
2. Recepción o admin (también si además es odontóloga: el permiso más amplio gana) → `nivel = "total"`, todo `True`.
3. Odontóloga pura: `profesional_id` de `resolver_alcance`. Una sola consulta sobre `turno` (usa el prefijo `paciente_id` de `ix_turno_paciente_inicio`) con dos agregados filtrados por `paciente_id = :p AND profesional_id = :prof`: `max(inicio) FILTER (WHERE estado = 'atendido')` y `bool_or(estado IN ('reservado','confirmado') AND fin > :ahora)`.
   - Sin ningún `atendido` → `PacienteAjenoError` (403 `paciente_ajeno`), aunque haya un turno futuro (O2: el acceso se gana al atender).
   - Último `atendido` con `inicio >= ahora - VENTANA_ACCESO_CLINICO`, **o** algún turno `reservado`/`confirmado` con `fin > ahora` → `nivel = "clinico_completo"`, `escribe_clinica = True`.
   - Si no → `nivel = "clinico_lectura"`, `escribe_clinica = False` (O16).
   - En ambos casos `escribe_administrativo = False`, `ve_contacto = False`, `ve_pagos = False` (O3).
4. Odontóloga sin `profesional_id` → `SinProfesionalAsociadoError` (403), como en C-08.

**Ventana (O16).** `VENTANA_ACCESO_CLINICO: Final = timedelta(days=365)` en `app/pacientes/alcance.py`, única fuente del valor (los tests la importan). "12 meses" se define como **365 días exactos** sobre instantes UTC: no depende del calendario, del horario de verano ni de los 29 de febrero, y no suma dependencias (`relativedelta` daría 365 o 366 según el año). El límite es inclusivo: un `atendido` que empezó hace exactamente 365 días todavía da acceso completo; uno de 365 días y 1 segundo, no. Se mide contra `turno.inicio` (el estado no guarda cuándo se marcó). "Turno pendiente" es `reservado`/`confirmado` con `fin > ahora` (futuro o en curso), así un control de hoy que ya empezó y todavía no se marcó sigue habilitando la escritura; `en_espera` no cuenta (no bloquea agenda, R8).

**Escrituras con acceso de solo lectura.** `PUT …/ficha` y `POST …/odontograma` verifican `escribe_clinica` después del alcance y antes de cualquier escritura: `clinico_lectura` → `AccesoClinicoVencidoError` (403 `acceso_clinico_vencido`, con un mensaje que indica pedir un turno a recepción), sin auditar. Las lecturas (ficha, odontograma, historial, presupuestos, datos del paciente con O3) responden igual en `clinico_completo` y `clinico_lectura` y se auditan igual. Las escrituras administrativas siguen cortándose antes por rol (D1), con 403 genérico.

`reservado`, `confirmado` y `ausente` **no** otorgan acceso por sí solos (O2 aprobada): el acceso se gana al atender, no al agendar; un turno pendiente solo **extiende** a completo un acceso ya ganado. Como `atendido` es final (RN-TU-12), el acceso de lectura solo se pierde si recepción corrige el vínculo del turno (`PUT /turnos/{id}/paciente`); el de escritura, además, vence con la ventana.

**Primera visita.** Desde O15 la odontóloga puede marcar `atendido` sus propios turnos (D12). Flujo esperado: la persona llega, recepción la registra o la busca por DNI y vincula el turno; al entrar al consultorio, la odontóloga (o recepción) marca el turno `atendido`, lo que RN-TU-12 permite desde las 00:00 del día del turno, y desde ese momento ella lee y escribe ficha y odontograma (acceso completo: el `atendido` es de hoy). Si el turno todavía no está vinculado con un `Paciente` (alta manual con solo nombre y teléfono, O1), el marcado se acepta igual pero no da acceso clínico: el alcance se calcula sobre `turno.paciente_id`, así que el acceso aparece solo, sin volver a marcar, cuando recepción vincula el turno. **Seguimiento:** un paciente atendido hace más de 12 meses que vuelve con un turno `reservado`/`confirmado` recupera el acceso completo desde que se agenda (la odontóloga puede preparar la consulta), y lo conserva 12 meses después del inicio de ese turno una vez marcado `atendido`.

**Filtrado por rol (O3).** Los routers eligen el esquema de salida según `AlcancePaciente`: `PacienteOut` (completo) o `PacienteVistaClinicaOut` (con `dni` y `numero_afiliado`, sin `telefono` ni `email`); `PresupuestoOut` o `PresupuestoVistaClinicaOut` (sin `pagos`, `total_pagado` ni `saldo`). Son clases distintas, no un `exclude` dinámico, para que un campo nuevo no se filtre por omisión (R15).

La consulta usa `ix_turno_paciente_inicio` (prefijo `paciente_id`). Ficha, odontograma, presupuestos y pagos cuelgan de `paciente_id` (no de `ficha_id`), así el alcance es uno solo. En las escrituras clínicas de la odontóloga, el chequeo de alcance y el `INSERT`/`UPDATE` corren en la misma transacción.

### D3. Auditoría (O5)
Helper `auditar(session, usuario_id, accion, entidad, entidad_id, datos)` en la misma transacción. `usuario_id` es siempre el actor (recepción, admin u odontóloga): con O4 la odontóloga escribe y queda identificada igual que en las lecturas. `datos_despues` lleva solo ids, nombres de campos, versión, cantidades, estados de presupuesto/pago y montos de pago (dato contable, no de salud). **Nunca** antecedentes, estados del odontograma, notas, nombre, DNI, número de afiliado, teléfono ni email. Acciones: `alta_paciente`, `edicion_paciente`, `vinculo_turno_paciente`, `lectura_ficha`, `edicion_ficha`, `lectura_odontograma`, `registro_odontograma`, `lectura_presupuesto`, `alta_presupuesto`, `edicion_presupuesto`, `transicion_presupuesto`, `lectura_pagos_presupuesto`, `registro_pago_presupuesto`, `anulacion_pago_presupuesto`. Las lecturas hacen `commit` (un GET escribe auditoría: aceptado). El marcado de `atendido` por la odontóloga (O15) no suma acciones: reutiliza el registro de C-08 (`marcado_atendido_panel`, con su `usuario_id`, estado anterior y nuevo, sin nombre ni teléfono).

### D4. Ficha (O6)
Tabla `ficha` 1:1 con `paciente` (creada en el primer `PUT`). `GET` sin fila → antecedentes vacíos y `version` 0. `PUT` con `version` v:
- v = 0 → `INSERT … ON CONFLICT (paciente_id) DO NOTHING RETURNING id`; sin fila → 409 `version_desactualizada`.
- v > 0 → `UPDATE ficha SET …, version = version + 1, actualizado_por = :actor WHERE paciente_id = :p AND version = :v`; `rowcount = 0` → 409.
- El control de versión es el mismo para todos los roles: con O4, recepción y la odontóloga pueden editar a la vez y la segunda recibe 409, nunca pisa.
Historia de turnos: un `SELECT` con joins a profesional y tratamiento sobre `turno.paciente_id`, excluyendo `en_espera` vencidas (mismo filtro que la agenda de C-08), orden `inicio DESC`.

### D5. Odontograma (O7, O8)
- Catálogo en `clinica/odontograma.py`: `PIEZAS_FDI` (52 piezas), `CARAS = ("O","M","D","V","L")`, `ESTADOS_CARA = ("caries","obturado")`, `ESTADOS_PIEZA = ("ausente","extraccion_indicada","corona","endodoncia","implante")`, más `sano` en ambos. Pydantic valida y la base repite la regla con `CHECK` (defensa en profundidad).
- `vigente(registros) -> dict[pieza, VigentePieza]`, pura: recorre en orden `(registrado_en, id)`; `sano` sin cara resetea pieza y caras; `sano` con cara borra esa cara; un estado de pieza reemplaza el anterior de pieza. Desempate por `id`.
- `POST` inserta el lote con un solo `INSERT … VALUES` (1–64 filas) y `registrado_en = now()` de la transacción (todas iguales; el `id` ordena).
- Historial paginado por `limite` (1–200, defecto 50) y `antes_de_id` (cursor).

### D6. Cálculo de importes (O9, O11)
`clinica/calculo.py`, puro, con `Decimal` y `quantize(Decimal("0.01"), ROUND_HALF_UP)`:
```
bruto       = precio_unitario * cantidad                (exacto, 2 decimales)
cobertura   = q(bruto * porcentaje / 100)
diferencial = arancel_diferencial * cantidad
a_cargo     = bruto - cobertura + diferencial
totales     = suma de las líneas ya redondeadas
```
- Fuente de valores: `tratamiento.precio_base` vigente y la fila de `nomenclador` de `(obra_social_id del presupuesto, tratamiento_id)`, cargadas con **una** consulta `IN` por presupuesto (sin N+1). Sin fila u obra social nula → 0 % y diferencial 0, `sin_cobertura = true`.
- Cada línea guarda el snapshot: `precio_unitario`, `cobertura_porcentaje`, `arancel_diferencial`, `codigo_prestacion`, `nomenclador_id` e importes.
- Obra social del presupuesto: la del paciente si está activa; el cliente puede indicar otra activa (o `null` para particular) en borrador. Inactiva → 422 `obra_social_inactiva`.

### D7. Estados y congelamiento (O10)
`clinica/estados.py`, puro: `TRANSICIONES = {borrador: {presentado, anulado}, presentado: {aceptado, rechazado, anulado}, aceptado: {anulado}}`; `rechazado` y `anulado` son finales. Cada transición toma `SELECT … FOR UPDATE` del presupuesto. `presentar` recalcula con valores vigentes (D6) y desde ahí ninguna ruta recalcula. `anular` desde `aceptado` cuenta pagos `registrado` bajo el mismo lock → 409 `presupuesto_con_pagos`. Timestamps `presentado_en`, `resuelto_en` (aceptado/rechazado), `anulado_en` + `anulado_motivo` (3–300).

### D8. Pagos de presupuesto (O12)
- Registro: `SELECT … FOR UPDATE` del presupuesto → valida `aceptado` → `SUM(monto) WHERE estado='registrado'` → `monto ≤ saldo` → `INSERT`. El lock serializa registros concurrentes y la anulación del presupuesto.
- `fecha_cobro ≤ ahora` (reloj inyectable `get_reloj`); por defecto `ahora`.
- Índice único parcial `(medio, referencia) WHERE referencia IS NOT NULL AND estado = 'registrado'` → `IntegrityError` 23505 traducido a 409 `referencia_duplicada`.
- Anulación: `UPDATE … SET estado='anulado', anulado_por, anulado_en, anulado_motivo WHERE id = :id AND presupuesto_id = :pid AND estado = 'registrado'` bajo el lock del presupuesto.
- **Contrato para C-12 (caja):** C-12 suma `pago_presupuesto` con `estado = 'registrado'` por `fecha_cobro` (índice propio) y medio, junto con las señas de `pago_sena`. C-12 podrá agregar en su migración `cierre_caja_id` (FK nullable con índice) y bloquear la anulación de pagos de una caja cerrada; C-11 no lo anticipa para no inventar el modelo de cierre.

### D9. Migración `008_ficha_odonto_presup` (archivo `008_ficha_odontograma_presupuestos.py`; R4, R6, R14)
Todo `BIGINT GENERATED ALWAYS AS IDENTITY`, `TIMESTAMPTZ`, `TEXT` + `CHECK` de longitud, `NUMERIC` para dinero (skill `postgresql-table-design`). FKs a datos clínicos con `ON DELETE RESTRICT`; a `usuario` con `SET NULL`.
- `ficha`: `paciente_id` UNIQUE (el índice único cubre la FK), `alergias`, `medicacion`, `antecedentes_medicos`, `observaciones` (`TEXT NOT NULL DEFAULT ''`, `≤ 2000`), `version INTEGER ≥ 1`, `actualizado_por` (+ índice), `created_at`, `updated_at`.
- `odontograma_registro`: `paciente_id`, `pieza SMALLINT` (`CHECK` de rangos FDI), `cara TEXT NULL` (`IN ('O','M','D','V','L')`), `estado TEXT` (`CHECK` catálogo), `CHECK` de coherencia cara/estado, `nota TEXT NULL ≤ 500`, `registrado_por` (+ índice), `registrado_en`. Índice `(paciente_id, registrado_en DESC, id DESC)` (cubre la FK y el historial).
- `presupuesto`: `paciente_id`, `obra_social_id NULL`, `estado` (`CHECK` de los cinco), `subtotal`, `cobertura_total`, `diferencial_total`, `total_paciente NUMERIC(12,2) ≥ 0` con `CHECK (total_paciente = subtotal - cobertura_total + diferencial_total)`, `notas ≤ 1000`, `creado_por`, `presentado_en`, `resuelto_en`, `anulado_en`, `anulado_motivo`, timestamps; `CHECK` de coherencia estado ↔ timestamps. Índices `(paciente_id, created_at DESC)`, `obra_social_id`, `creado_por`.
- `presupuesto_linea`: `presupuesto_id` (`CASCADE`: las líneas no existen sin su presupuesto; la API nunca borra presupuestos y el `PUT` de borrador reemplaza las líneas), `orden SMALLINT`, `tratamiento_id`, `nomenclador_id NULL` (`SET NULL`), `codigo_prestacion NULL`, `pieza`/`cara` NULL con los mismos `CHECK`, `cantidad SMALLINT 1–99`, `precio_unitario NUMERIC(10,2)`, `cobertura_porcentaje NUMERIC(5,2)`, `arancel_diferencial NUMERIC(10,2)`, `importe_bruto`, `importe_cobertura`, `importe_diferencial`, `importe_paciente NUMERIC(12,2)` con `CHECK` de la fórmula y `importe_cobertura ≤ importe_bruto`. Índices en las tres FKs; `UNIQUE (presupuesto_id, orden)`.
- `pago_presupuesto`: `presupuesto_id`, `medio` (`IN ('mercadopago','transferencia')`), `monto NUMERIC(12,2) > 0`, `estado` (`registrado`/`anulado`), `fecha_cobro TIMESTAMPTZ`, `referencia TEXT NULL 1–64`, `registrado_por`, `anulado_por`, `anulado_en`, `anulado_motivo`, `created_at`; `CHECK` de coherencia de anulación; índices en FKs, en `fecha_cobro` y el único parcial de D8.
- `downgrade()` borra en orden inverso. Sin cambios a tablas existentes.

### D10. Estrategia de pruebas (Strict TDD)
- **Unit (sin base):** `calculo.py` (seed Swiss 25000 → 2500; half-up 10.10 × 85 % → 8.59; diferencial por unidad; particular; totales como suma de líneas), `odontograma.py` (catálogo, coherencia, `vigente` con sano de pieza y de cara, desempate), `estados.py` (tabla completa de transiciones), esquemas Pydantic (`extra="forbid"`, DNI, E.164, longitudes).
- **Integración (pytest + PostgreSQL real, `httpx`):** migración 008 up/down/up; cada endpoint con recepción, admin, odontóloga propia (turno `atendido`) y ajena (solo `reservado`/`confirmado`/`ausente`, o atendida por otra profesional); primera visita (403 antes de marcar `atendido`, 200 después, marcando recepción o la propia odontóloga); ventana de O16 con `reloj` (atendido hace 11 meses → escribe; 13 meses sin turno pendiente → lee y escribir da 403 `acceso_clinico_vencido`; 13 meses + `confirmado` futuro → escribe; solo turno futuro → 403 `paciente_ajeno`; límite 365 días exactos vs. 365 días + 1 s); marcado de `atendido` por la odontóloga (propio 200 con auditoría, ajeno e inexistente 403 `turno_ajeno` con cuerpo idéntico, `ausente`/`cancelar` 403, reglas de RN-TU-12 en sus turnos, turno sin paciente vinculado, marcado simultáneo con recepción) y acciones de agenda por rol; claves exactas del JSON por rol (DNI y afiliado presentes, teléfono/email/pagos ausentes); un test parametrizado de toda la matriz de D1; auditoría (presencia, ausencia en rechazos, sin contenido clínico); versión de ficha; congelamiento; concurrencia de pagos con dos tareas `asyncio.gather` (201 + 409); referencia duplicada; seed aplicado (`run_seeds` + presupuesto Swiss).
- **E2E Playwright (R7):** O15 cambia un flujo de turnos: un E2E nuevo en `frontend-panel/e2e/gestion.spec.ts` (la odontóloga marca `atendido` su turno de hoy a 360 px y no ve otras acciones) y el ajuste del de `agenda.spec.ts` (turno propio a 26 h: sigue sin botones). La UI de ficha, odontograma y presupuestos la cubrirá C-16.

### D11. Decisión que reemplaza la KB (O4, aprobada 2026-11-10)
La matriz RBAC de `knowledge-base/03_actores_y_roles.md` da al odontólogo/a "Lectura (sus pacientes)" sobre fichas, y el párrafo de C-08 (O5/O6) lo define como de **solo lectura**; US-009 (`06_funcionalidades.md`) pone la carga del odontograma en recepción/admin. El usuario aprobó O4 (b): la odontóloga **escribe ficha y odontograma de sus pacientes**. Esta decisión **prevalece sobre la KB** desde C-11 y se aplica así:
- Solo datos clínicos (ficha, odontograma). Datos administrativos del paciente, vínculos de turnos, presupuestos y pagos siguen siendo de recepción/admin; en la agenda la odontóloga solo marca `atendido` sus propios turnos (O15, D12: reemplaza C-08 O5 en ese punto); alta manual, `ausente`, `cancelar` y vínculos siguen siendo de recepción/admin.
- La escritura clínica de la odontóloga dura mientras su acceso sea completo (O16, D2): un `atendido` con esa persona en los últimos 12 meses (365 días) o un turno pendiente con ella; si no, lee pero no escribe (403 `acceso_clinico_vencido`).
- Las escrituras de la odontóloga tienen las mismas garantías: `version`/409 en la ficha (O6), registros solo de alta en el odontograma (O7), auditoría con su `usuario_id` (O5) y `actualizado_por`/`registrado_por`.
- La KB se actualiza en el apply (tareas 10.2–10.4): matriz y párrafo de `03_actores_y_roles.md` (incluida la nota de C-08 O5), RN-TU-12 y RN-CL-04 en `05_reglas_de_negocio.md`, US-009 en `06_funcionalidades.md`, RN-CL-01..03 en `05_reglas_de_negocio.md` y DD-10 en `09_decisiones_y_supuestos.md`. Hasta entonces, ante conflicto vale este diseño.
- O2 y O3 también ajustan la KB: "sus pacientes" pasa a significar "con al menos un turno `atendido` con su profesional", y la odontóloga ve DNI y número de afiliado del paciente (en la agenda, C-08 O6 sigue ocultándole el teléfono; eso no cambia).

### D12. La odontóloga marca `atendido` sus propios turnos (O15)
Decisión del usuario del 2026-11-10 que modifica `turnos/gestion-panel` y `turnos/agenda-panel` de C-08 (deltas MODIFIED en este change):
- **Permiso en el router.** `POST /turnos/{id}/atendido` pasa de `require_recepcion_o_admin` a `get_current_user` + `resolver_alcance` (como la agenda): recepción/admin (o multirrol) → sin restricción de profesional; odontóloga pura → `profesional_requerido = alcance.profesional_id`; sin profesional → 403 `sin_profesional_asociado`; sin roles de panel → 403 `sin_acceso_al_panel`. `ausente`, `cancelar`, alta manual y vínculos no cambian (`require_recepcion_o_admin`).
- **Propiedad bajo el lock.** `marcar_turno` y `cambiar_estado_turno` reciben `profesional_requerido: int | None`. Con valor, tras el `SELECT … FOR UPDATE` y **antes** de validar la transición y el horario, un turno inexistente o con `profesional_id` distinto levanta `TurnoAjenoError` → 403 `turno_ajeno` con un cuerpo fijo ("Solo podés marcar tus propios turnos"). Así la odontóloga no distingue "no existe" de "es de otra" ni ve el estado de un turno ajeno (no hay 404 ni 409 para ella sobre turnos ajenos). Recepción conserva su 404.
- **Mismas reglas.** Transición `reservado`/`confirmado` → `atendido` y `habilitado_desde` de RN-TU-12 sin cambios; seña sin cambios (C-08 O19); auditoría `marcado_atendido_panel` con su `usuario_id`; sin eventos (C-08 O15). Dos marcados simultáneos se serializan por el lock: uno 200 y el otro 409 `transicion_invalida`.
- **Acciones de la agenda.** `Alcance` suma `marca_atendido: bool` y `acciones_permitidas` recibe un permiso `"total" | "solo_atendido" | "ninguno"` en lugar de `puede_escribir`: `solo_atendido` devuelve como máximo `["atendido"]`. `puede_escribir` sigue gobernando el teléfono y `opciones.puede_escribir` (sin «Nuevo turno» para la odontóloga). El panel no cambia: ya muestra lo que informa el servidor, con su diálogo de confirmación.
- **Sin vínculo no hay acceso.** Marcar un turno sin `paciente_id` se acepta; el acceso clínico depende solo de D2 y aparece al vincular.
- **Fuera de alcance (O15 aprobada, opción a):** que la odontóloga marque `ausente` (retiene la seña y toca la caja, R9, RN-SN-02) y deshacer un `atendido` (RN-TU-12 lo hace final; corregir marcados es un seguimiento para C-12).

## Decisiones del usuario (aprobadas 2026-11-10)

Aprobadas por el usuario el 2026-11-10. O1 y O5–O14 quedan con la opción recomendada; **O2, O3 y O4 cambiaron** y los specs y tareas ya las reflejan. **O15 y O16** son decisiones nuevas del mismo día: O16 está aprobada; O15 fue **aprobada por el usuario el 2026-11-10 con la opción (a)**: la odontóloga solo marca `atendido` sus turnos, no marca `ausente` y no deshace; la definición de 365 días de O16 también fue **confirmada por el usuario**. Criticidad ALTA = datos de salud o dinero.

| # | Criticidad | Pregunta | Decisión final (2026-11-10) | Alternativas descartadas |
|---|---|---|---|---|
| O1 | Media | ¿Cómo se vincula un turno (sin `Paciente`) con su ficha? | **Aprobada (a):** C-11 suma alta/consulta/edición mínima de pacientes y búsqueda exacta por DNI, más `PUT /turnos/{id}/paciente` (reemplazable, auditado). C-12 conserva listado, búsqueda libre, historial y ausentismo | (b) pacientes solo por seed/tests hasta C-12 (C-11 inutilizable); (c) crear `Paciente` en la reserva (exige DNI, rompe RN-TU-06) |
| O2 | ALTA | ¿Qué son "sus pacientes" para la odontóloga? | **CAMBIADA → (b):** al menos un turno vinculado con su profesional en estado `atendido`, de cualquier fecha. `reservado`, `confirmado` y `ausente` no cuentan. En la primera visita el acceso empieza al marcarse el turno `atendido` (D2) | (a) `reservado`/`confirmado`/`atendido`/`ausente` (recomendada original); (c) cualquier turno, incluso cancelado o en espera; (d) todos los pacientes |
| O3 | ALTA | ¿Qué datos ve la odontóloga? | **CAMBIADA:** ficha, odontograma y presupuestos de sus pacientes, más nombre, apellido, obra social, **DNI y número de afiliado**; nunca teléfono, email ni pagos. Esquemas de salida por rol (D2) | (a) sin DNI ni afiliado (recomendada original, como C-08 O6); (b) todo, incluidos contacto y pagos |
| O4 | ALTA | ¿La odontóloga escribe ficha u odontograma? | **CAMBIADA → (b):** escribe ficha (con `version`/409, O6) y odontograma (solo de alta, O7) de sus pacientes, auditado con su usuario. Presupuestos: solo lectura; pagos: sin acceso. Reemplaza la matriz RBAC y US-009 de la KB (D11) | (a) solo lectura (recomendada original: matriz RBAC, US-009, C-08 O5) |
| O5 | ALTA | ¿Se auditan las lecturas de datos de salud? | **Aprobada (a):** sí, lecturas y escrituras, sin contenido clínico ni PII | (b) solo escrituras (lecturas en C-13); (c) escrituras con `datos_antes/después` completos (copia datos de salud al log) |
| O6 | Media | Estructura y concurrencia de la ficha | **Aprobada (a):** cuatro campos de texto ≤ 2000 con `version` optimista (409 si está desactualizada) | (b) revisiones solo de alta de la ficha; (c) último que escribe gana |
| O7 | Media | Representación del odontograma e historia | **Aprobada (a):** registros solo de alta; vigente derivado; corrección = registro nuevo | (b) snapshot JSONB por paciente + tabla de historia; (c) snapshot que se pisa, sin historia |
| O8 | Media | Piezas, caras y estados | **Aprobada (a):** 32 permanentes + 20 temporales; caras O/M/D/V/L; cara: caries, obturado; pieza: ausente, extracción indicada, corona, endodoncia, implante; `sano` en ambos | (b) solo permanentes; (c) catálogo extensible en tabla (sellador, fractura, prótesis…) |
| O9 | Media | Fórmula de cobertura | **Aprobada (a):** % del nomenclador sobre el bruto, `arancel_diferencial` como copago por unidad a cargo del paciente **[SUPUESTO]**, half-up a centavos por línea, totales = suma de líneas | (b) ignorar `arancel_diferencial`; (c) redondear solo el total; (d) monto fijo de cobertura por prestación (requiere migrar el nomenclador) |
| O10 | Media | Estados y congelamiento | **Aprobada (a):** borrador → presentado → aceptado/rechazado; anulado con motivo (desde aceptado solo sin pagos); recalcula en borrador, congela al presentar | (b) sumar `vencido` por fecha de vigencia; (c) sin estados, solo total |
| O11 | Media | Obra social y precio del presupuesto | **Aprobada (a):** obra social activa del paciente por defecto, otra activa o particular editable en borrador; precio = `precio_base` vigente, sin precio manual | (b) permitir precio manual por línea con auditoría; (c) obra social fija del paciente |
| O12 | ALTA | ¿Los pagos de presupuesto viven en C-11? | **Aprobada (a):** sí, registro manual MP/transferencia sobre aceptados, tope en el total, referencia única por medio, anulación sin borrado; sin checkout online. C-12 los suma por `fecha_cobro` | (b) postergar pagos a C-12 (C-11 sin dinero, queda MEDIO puro); (c) checkout MP online reutilizando la pasarela de C-06 |
| O13 | Media | ¿UI en C-11? | **Aprobada (a):** no, solo API; registrar `C-16 panel-ficha-presupuestos-ui` (depende de C-11, sobre `frontend-panel/`, R1–R3, R7) | (b) UI mínima en C-11 a 360 px con E2E (duplica el tamaño); (c) sumarla a C-12 |
| O14 | Media | ¿La historia de turnos de la ficha muestra turnos con otras profesionales? | **Aprobada (a):** sí, todos (continuidad clínica), sin contacto | (b) la odontóloga ve solo sus turnos |
| O15 | ALTA | La odontóloga marca `atendido` sus propios turnos (decisión del usuario): ¿puede también marcar `ausente` o deshacer un `atendido`? | **APROBADA por el usuario el 2026-11-10, opción (a):** solo `atendido`, solo sus turnos, mismas reglas de RN-TU-12 y misma auditoría; turno ajeno o inexistente → 403 `turno_ajeno`. Ni `ausente` (retiene la seña y toca la caja, R9) ni deshacer (`atendido` es final; corregir marcados queda para C-12). Modifica C-08 O5 (D12) | (b) también `ausente` de sus turnos (mismas reglas de tolerancia; la seña queda retenida por una acción de la profesional); (c) también deshacer `atendido` dentro del mismo día (rompe RN-TU-12 y abre/cierra acceso clínico) |
| O16 | ALTA | ¿El acceso clínico de la odontóloga vence con el tiempo? | **Aprobada (c):** completo (lee y escribe ficha y odontograma, lee presupuestos, campos de O3) con un `atendido` en los últimos 12 meses (`VENTANA_ACCESO_CLINICO` = 365 días exactos, UTC) o un turno `reservado`/`confirmado` con ella que no terminó; con atenciones solo más viejas, solo lectura (escrituras → 403 `acceso_clinico_vencido`); sin ningún `atendido`, sin acceso (O2 sin cambios). D2 | (a) acceso permanente sin ventana (O2 original); (b) el acceso entero (también la lectura) vence a los 12 meses |

**Reglas nuevas** (aprobadas; se redactan en `05_reglas_de_negocio.md` en la tarea 10.2):
- **RN-PG-04** — cálculo de cobertura por línea (O9). **RN-PG-05** — estados del presupuesto y congelamiento al presentar (O10). **RN-PG-06** — pagos de presupuesto: solo aceptados, suma ≤ total a cargo, referencia única por medio, anulación sin borrado (O12).
- **RN-CL-01** — el odontograma solo crece (O7). **RN-CL-02** — acceso clínico de la odontóloga: solo pacientes con al menos un turno `atendido` con su profesional; lee y escribe ficha y odontograma (escritura según RN-CL-04), lee presupuestos, ve DNI y número de afiliado, nunca teléfono, email ni pagos; no escribe datos administrativos, presupuestos ni pagos (O2–O4). **RN-CL-03** — toda lectura o escritura de datos de salud queda auditada sin su contenido (O5). **RN-CL-04** — ventana de acceso clínico (O16): escritura solo con un `atendido` con esa persona en los últimos 12 meses (365 días) o un turno `reservado`/`confirmado` con ella pendiente; si no, solo lectura.
- **RN-TU-12 (enmienda, O15):** además de recepción y admin, la odontóloga marca `atendido` los turnos de su profesional con las mismas reglas; `ausente` sigue siendo solo de recepción y admin.

## Risks / Trade-offs
- [O9 interpreta `arancel_diferencial` sin fuente en la KB] → queda marcado **[SUPUESTO]**; con el seed en 0 no cambia ningún resultado actual, y un test fija la fórmula para que un cambio sea explícito.
- [El seed aplica un % único por obra social; no es un nomenclador real] → el cálculo es correcto con cualquier fila; cargar el nomenclador real queda fuera (lo aporta la clínica).
- [Las lecturas auditadas escriben en cada GET] → volumen bajo (clínica chica, SU-02); índice `created_at` existente.
- [Pagos con dinero en un change MEDIO] → O12 marcada ALTA para aprobación explícita; invariantes en la base y test de concurrencia.
- [Vincular turnos es manual] → hasta C-16 se hace por API; la historia y el alcance de la odontóloga dependen de que recepción vincule. Documentado en README.
- [Un `PUT /turnos/{id}/paciente` puede quitar el acceso de una odontóloga a una ficha] → es el efecto buscado al corregir un error; queda auditado con ambos ids.
- [Mover `require_recepcion_o_admin`] → se re-exporta desde `catalogo/router.py`; la suite existente lo verifica.
- [La odontóloga podría darse acceso a sí misma marcando `atendido` el turno de alguien que nunca vino (O15)] → mitigado: solo sus propios turnos (403 `turno_ajeno` para el resto, sin revelar existencia), nunca antes del día del turno (RN-TU-12), el marcado queda auditado con su `usuario_id` (`marcado_atendido_panel`), el estado es final (no puede "probar y deshacer") y el turno tiene que estar vinculado por recepción con ese `Paciente` para que haya acceso. El acceso que gana es el mismo que tendría si recepción marcara (O2–O4). Riesgo residual aceptado; C-13 podrá reportar marcados de la odontóloga.
- [Primera visita con turno sin vincular (O1)] → la odontóloga marca `atendido` pero recibe 403 en la ficha hasta que recepción vincule el turno. Mitigación: README documenta el orden "buscar/registrar por DNI → vincular → marcar atendido"; el acceso aparece solo al vincular, sin re-marcar.
- [O15 cambia un contrato de C-08 (403 → 200 para la odontóloga) y tests/E2E existentes] → los tests de C-08 que fijaban la regla vieja se reescriben primero (RED) en el grupo 9 y el E2E de agenda se ajusta; el resto de la suite de C-08 corre como red de seguridad.
- [La odontóloga no marca `ausente`, así que un turno de alguien que faltó queda `reservado` hasta que recepción actúe] → es el mismo comportamiento que hoy.
- [RN-TU-12 permite marcar `atendido` desde las 00:00 del día del turno] → recepción o la odontóloga (O15) podrían marcarlo antes de que la persona llegue y abrir el acceso horas antes; si después la persona falta, el turno ya es `atendido` (final) y el acceso queda. Riesgo aceptado: el marcado queda auditado con el usuario y RN-TU-12 no cambia.
- [La lectura sigue siendo permanente ("alguna vez atendido")] → con O16 la escritura vence a los 12 meses sin turno pendiente, pero la lectura no (continuidad clínica). Es la decisión aprobada (O16 (c)); toda lectura queda auditada con su usuario.
- [Ventana de O16 medida sobre `turno.inicio` y en 365 días] → un año bisiesto corre la ventana un día respecto del calendario, y un turno marcado tarde cuenta desde su inicio, no desde el marcado. Aceptado: regla simple y determinística, fijada en una constante y con test de borde.
- [Recepción puede reabrir el acceso completo agendando un turno a un paciente viejo (O16)] → es el flujo de seguimiento buscado; la odontóloga no crea turnos (solo recepción/admin) y el alta queda auditada.
- [La odontóloga escribe datos de salud (O4)] → un error clínico queda en la historia: la ficha guarda `actualizado_por` y la auditoría la versión, y el odontograma es solo de alta, así que siempre se sabe quién cargó qué y nada se pierde.
- [Carrera entre la escritura de la odontóloga y una corrección de vínculo] → el chequeo de alcance y la escritura corren en la misma transacción; si recepción re-vincula el turno en paralelo, una escritura que ya pasó el chequeo puede confirmarse. Ventana mínima sobre una acción de corrección poco frecuente: aceptado, queda auditado.
- [O4 contradice la KB hasta el apply] → D11 fija que prevalece este diseño y las tareas 10.2–10.4 sincronizan `03`, `05`, `06` y `09`.

## Migration Plan
1. Verificar con `ls backend/src/alembic/versions` que `008` sigue libre (C-09/C-10 pueden correr en paralelo) y `alembic upgrade head`.
2. Deploy del backend: solo endpoints nuevos, sin cambios de contrato.
3. **Rollback:** build anterior y `alembic downgrade -1` (borra las cinco tablas; se pierden fichas y presupuestos cargados — avisar antes de producción).

## Audit & Compliance Note (spec-rules-auditor)
**Cuarta auditoría (2026-11-10, tarea 11.4, durante el apply, con la skill `spec-rules-auditor`).** Se re-auditaron los specs contra `knowledge-base/05_reglas_de_negocio.md` ya sincronizada (RN-PG-04..06, RN-CL-01..04 y RN-TU-12 enmendada), `03_actores_y_roles.md` actualizada y la implementación. **Dictamen: APROBADO.** Observaciones anteriores: (1) la divergencia con la KB de D11 queda cerrada (tareas 10.2 a 10.4: matriz RBAC, US-009, RN-TU-12, nota de C-08 O5 y DD-10 coinciden con este diseño); (2) O15 fue aprobada por el usuario con la opción (a); (3) el supuesto de O9 (`arancel_diferencial`) sigue marcado como `[SUPUESTO]` en DD-10 y lo fija un test; (4) los 365 días de O16 fueron confirmados por el usuario. Cada requisito tiene su terna Esperado / Error de negocio / Caso de borde cubierta por tests de integración (`test_ficha_integration.py`, `test_odontograma_integration.py`, `test_presupuestos_integration.py`, `test_pagos_presupuesto_integration.py`, `test_panel_estados_integration.py`, `test_clinica_rbac_matriz.py`) y por el E2E de 9.7. Desvío menor registrado: el id de revisión de Alembic se acortó a `008_ficha_odonto_presup` porque `alembic_version.version_num` es `VARCHAR(32)` (el archivo conserva el nombre largo).

Primera auditoría el 2026-11-10 sobre los borradores; re-auditado el mismo día tras las decisiones finales O2–O4. **Tercera auditoría el 2026-11-10** tras O15 y O16, sobre las partes cambiadas: `proposal.md`, este `design.md` (contexto, D1, D2, D3, D10, D11, D12, tabla O15/O16, reglas, riesgos), los deltas MODIFIED `turnos/gestion-panel`, `turnos/agenda-panel` y `auth/panel-login`, y los requisitos tocados de `pacientes/ficha-clinica` y `clinica/odontograma`, contra `knowledge-base/05_reglas_de_negocio.md` (RN-TU-12, RN-SN-02, RN-GL-01), `03_actores_y_roles.md`, los specs principales de C-08 y R1–R20. **Dictamen: OBSERVACIONES (no bloqueantes para el apply)**: cada requisito modificado o nuevo tiene la terna Esperado / Error de negocio / Caso de borde con datos sintéticos, y no se detectan transiciones filtradas. Observaciones: (1) divergencia deliberada con la KB (D11: matriz RBAC, US-009, RN-TU-12 y nota de C-08 O5), se cierra en 10.2–10.4; (2) O15 aprobada por el usuario el 2026-11-10 con la opción (a) (solo `atendido`); (3) el supuesto de O9; (4) "12 meses = 365 días" de O16 es una precisión de diseño confirmada por el usuario, explícita y en una sola constante.

| Regla | Estado | Dónde / observación |
|---|---|---|
| RN-PG-01 (MP + transferencia) | CUBIERTA | `pagos-presupuesto` "Registro manual de un cobro" (medio `efectivo` → 422; odontóloga → 403 aunque sea su paciente) |
| RN-PG-02 (cobertura por nomenclador) | CUBIERTA | `presupuestos` "Cálculo de cada línea…" y "Totales" (seed Swiss, half-up, particular) |
| RN-PG-03 (sin ARCA) | CUBIERTA | `presupuestos` "Sin facturación electrónica" |
| RN-GL-01 (auditoría de panel) | CUBIERTA | `ficha-clinica` "Auditoría de accesos…"; `gestion-panel` "La odontóloga marca atendido su propio turno" (`marcado_atendido_panel` con su `usuario_id`); rechazos sin registro (`turno_ajeno`, `acceso_clinico_vencido`) |
| RN-GL-02 (exportación) | FUERA DE ALCANCE | C-13 |
| RN-GL-03 / R3 (mobile-first) | CUBIERTA en lo que toca | `gestion-panel` "La odontóloga marca atendido desde la agenda" a 360 px; el resto sin UI (O13 → C-16) |
| RN-TU-12 (marcar atendido) | ENMENDADA DELIBERADAMENTE (O15) | Mismas reglas de estado y horario para la odontóloga: día anterior 23:59:59 → 409 `marcado_no_habilitado`; 00:00:00 → 200; ya `atendido` → 409 `transicion_invalida`; `ausente` sigue solo para recepción/admin. Enmienda del texto en 10.2 |
| RN-SN-02 / R9 (ausente retiene la seña) | RESPETADA | La odontóloga no marca `ausente` (O15 aprobada, opción a); marcar `atendido` no toca la seña (escenario con seña `acreditado`) |
| RN-TU-01..11 | NO AFECTADAS | El vínculo turno↔paciente y el marcado no cambian horario, solape ni seña; marcado simultáneo serializado (200 + 409) |
| RN-TU-06 (reserva sin registro) | RESPETADA | O1 descarta exigir paciente; un turno sin vincular se marca igual y no da acceso (escenario) |
| RN-SN-* / R8 | NO AFECTADAS | `en_espera` no cuenta como turno pendiente en O16; `pago_presupuesto` no bloquea agenda |
| C-08 O5 (odontóloga solo lectura) | MODIFICADA DELIBERADAMENTE | Deltas MODIFIED de `gestion-panel` ("Solo recepción y admin operan la agenda", "Pantallas de alta manual y acciones sobre el turno") y `agenda-panel` ("Contenido de cada turno de la agenda"): solo `atendido` en turnos propios; ajeno o inexistente → 403 `turno_ajeno` sin filtrar existencia |
| Matriz RBAC (03) y US-009 (06) | CONTRADICHAS DELIBERADAMENTE | O4, O15, O16 (D11); delta `auth/panel-login` "RBAC authorization" con terna. La KB se sincroniza en 10.2–10.4 |
| "Sus pacientes" (03) | DEFINIDA | O2: ≥ 1 turno `atendido` con su profesional; un turno futuro solo → 403 `paciente_ajeno` |
| Ventana de acceso (RN-CL-04 nueva, O16) | CUBIERTA | `ficha-clinica` "Ventana de acceso clínico de la odontóloga": 11 meses, y 13 meses + `confirmado` futuro → escriben; 13 meses sin pendiente → lee, escribe 403 `acceso_clinico_vencido`; borde 365 días exactos vs. +1 s; reloj del servidor en UTC (R4) |
| Minimización de datos (Ley 25.326, O3) | CUBIERTA | Esquemas de salida por rol; mismos campos en acceso completo y de solo lectura; `turno_ajeno` no revela existencia ni estado |
| R1, R2 | NO APLICAN | Sin código de frontend nuevo (el panel ya muestra las acciones del servidor) |
| R4 | CUBIERTA | `NUMERIC` para dinero, `TIMESTAMPTZ`, `TEXT` + `CHECK` (D9); ventana sobre instantes UTC con zona |
| R5 | NO AFECTADA | Sin cambios en EXCLUDE; `atendido` sigue ocupando el horario |
| R6 | CUBIERTA | Índice en cada FK (D9) |
| R7 | CUBIERTA | E2E Playwright del marcado por la odontóloga (tarea 9.7) y ajuste del E2E de agenda |
| R13–R16, R18 | CUBIERTAS | Pydantic in/out (dos esquemas de salida por rol), ORM, async, Compose existente |
| R14 | CUBIERTA | `008` reversible, sin SQL crudo fuera de la migración |
| R17 | NO AFECTADA | Sin secretos nuevos; la ventana es una constante de código |
| R19 / Ley 25.326 | CUBIERTA | Datos sintéticos (DNI 99xxxxxx, afiliado "SM-SINT-0001", +54911000000xx, "Dra. Ana Ficticia", "Dr. Bruno Ficticio", "Carlos Sintético"), auditoría sin contenido clínico ni PII |
| R11, R12, R20 | CUBIERTAS | Sin commits; archivos solo en `backend/`, `frontend-panel/e2e/` y docs canónicas |

**Supuestos marcados:** `[SUPUESTO]` semántica de `arancel_diferencial` (O9). **Confirmado por el usuario (2026-11-10):** O15 (a) solo `atendido`; 365 días de O16. **Gaps:** ninguno sin escenario. **Riesgos nuevos señalados:** auto-otorgamiento de acceso marcando `atendido` un turno propio de alguien que no vino (mitigado: solo turnos propios, no antes del día, auditado, estado final, requiere el vínculo de recepción); un turno sin vincular no da acceso hasta que recepción lo vincule; cambio de contrato de C-08 con tests y E2E a reescribir; ventana de 365 días medida sobre `turno.inicio`.
