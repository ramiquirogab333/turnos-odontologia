# Modelo de Datos

Entidades inferidas de las fuentes (discovery + state). Diseño físico sobre el stack congelado (Resoluciones 2026-09-30): PostgreSQL vía SQLAlchemy + Alembic (`DateTime(timezone=True)`, `Numeric` p/ dinero, `EXCLUDE USING gist` p/ anti-solape).

## Dominios

- **Agenda**: profesionales, sillones, disponibilidad, turnos, recordatorios.
- **Pacientes**: ficha, historia de turnos, ausentismo.
- **Clínica**: tratamientos y duraciones, odontograma básico, presupuestos, cobertura OS.
- **Pagos**: cobros por Mercado Pago / transferencia, caja y liquidaciones.
- **Plataforma**: usuarios y roles, auditoría, sincronización Google Calendar, exportación.

## ERD (textual)

```
Profesional 1───* Turno *───1 Paciente
Sillón 1───* Turno
Tratamiento 1───* Turno (duración configurable por tratamiento)
Paciente 1───0..1 Ficha (antecedentes, 1:1, con `version`)
Paciente 1───* OdontogramaRegistro (FDI, solo se agregan registros)
Paciente 1───* Presupuesto 1───* PresupuestoLinea (snapshot de precio y cobertura)
Presupuesto 1───* PagoPresupuesto (MP / transferencia, desde C-11)
CierreCaja 1───* CierreCajaLinea (foto inmutable de la caja de un día, desde C-12)
Turno 1───* Recordatorio (WhatsApp)
Profesional 1───* Disponibilidad (franjas configurables)
Usuario *───1 Rol (paciente-público / odontólogo / recepción-admin)
Turno *───* EventoCalendar (sincronía bidireccional GCal)
*───* RegistroAuditoria (quién, qué, cuándo)
ObraSocial 1───* Nomenclador (precargado AR)
```

## Entidades

### Paciente
- Atributos (según el código, C-02/C-11): id, nombre, apellido, **DNI** (único, 7 u 8 dígitos), teléfono E.164 (identificador operativo, sin login), email (opcional), obra social (opcional) y número de afiliado (opcional). No existe `notas`.
- Relaciones: 1───* Turno (`turno.paciente_id` nulo en reservas públicas y altas manuales hasta que recepción lo vincula, C-11); 1───0..1 Ficha; 1───* OdontogramaRegistro; 1───* Presupuesto.
- Constraints: DNI único; la reserva pública no crea `Paciente` (no pide DNI): el turno lleva solo nombre y teléfono de contacto.

### Ficha (desde C-11)
- Atributos: id, `paciente_id` (único: 1:1, se crea en la primera edición), `alergias`, `medicacion`, `antecedentes_medicos`, `observaciones` (texto, hasta 2000 caracteres cada uno), `version` (control de edición optimista), `actualizado_por` (usuario), timestamps. La historia de turnos no se guarda: se deriva de `Turno`.
- Relaciones: *───1 Paciente. Odontograma y presupuestos cuelgan del paciente, no de la ficha.

### OdontogramaRegistro (desde C-11)
- Atributos: id, `paciente_id`, `pieza` (FDI: permanentes 11-18, 21-28, 31-38, 41-48; temporales 51-55, 61-65, 71-75, 81-85), `cara` (O, M, D, V, L; opcional), `estado` (`sano`, `caries`, `obturado`, `ausente`, `extraccion_indicada`, `corona`, `endodoncia`, `implante`), `nota` (hasta 500), `registrado_por` (usuario), `registrado_en`.
- Solo se agregan registros (nunca se modifican ni se borran): el estado vigente por pieza y cara se deriva del historial. `caries` y `obturado` exigen cara; los estados de pieza la rechazan.

### Profesional (odontólogo/a)
- Atributos: id, nombre, matrícula, especialidad.
- Relaciones: 1───* Turno; 1───* Disponibilidad.
- Constraints: sin superposición de turnos por profesional desde el día 1 — multi-odontólogo día 1 (Resolución 2026-09-30 nº1); garantía en DB con `EXCLUDE USING gist` parcial por estado (estrategia A del DDL de C-01: dos EXCLUDE —profesional + rango y sillón/box + rango— con `WHERE estado IN ('reservado','confirmado','atendido')` desde la migración 007 de C-08, porque un `atendido` ocupa el horario hasta su `fin`), RN-TU-03.

### Sillón
- Atributos: id, nombre/identificador, estado.
- Relaciones: 1───* Turno (ocupación por sillón).
- Constraints: sin superposición de turnos por sillón/box desde el día 1 — multi-sillón día 1 (Resolución 2026-09-30 nº1); garantía en DB con `EXCLUDE USING gist` parcial por estado (estrategia A del DDL de C-01), RN-TU-03.

### Tratamiento
- Atributos: id, nombre, costo base (`Numeric`, no float), duración_minutos (duración estimada en minutos, configurable por admin, no fija en código).
- Relaciones: 1───* Turno.
- Constraints: duración > 0 (`CHECK`); tabla tratamiento→duración editable por admin (RN-TU-05); seed inicial aportado por la clínica (si falta, placeholder explícito documentado — C-02/C-04).

### Turno
- Atributos: id, paciente_id, profesional_id, sillon_id, tratamiento_id, inicio, fin (derivado de duración), estado (reservado / confirmado / cancelado / ausente / atendido; más `en_espera` desde C-06 —ver GAP en `CHANGES.md` header—), origen (`web` / `manual` / `whatsapp`; columna `NOT NULL DEFAULT 'web'` con `CHECK`, migración 007 de C-08; los turnos sin código de gestión se rellenaron como `manual`), código de gestión pública.
- Relaciones: 1───* Recordatorio; *───* EventoCalendar; 1───* PagoSena (desde C-06).
- Constraints: fin = inicio + duración del tratamiento; no solape por profesional NI por sillón/box desde día 1 (RN-TU-03, EXCLUDE parciales por estado, estrategia A); cancelación/reprogramación solo con ≥ 24 hs de anticipación. Estado `en_espera` (C-06): pre-reserva con seña pendiente que NO bloquea agenda ni genera recordatorio/calendario; solo la seña acreditada (`reservado`) bloquea el slot (R8), con la excepción del alta manual de recepción/admin (C-08, O7), que nace `reservado` sin seña. Ocupan agenda `reservado`, `confirmado` y `atendido` (O19).
- Índices: (profesional_id, inicio), (sillon_id, inicio), (paciente_id, inicio), estado; índice sobre cada FK.

### PagoSena (desde C-06)
- Atributos: id, turno_id, medio (Mercado Pago / transferencia), monto (`Numeric`, seña fija configurable, 30% del precio base por defecto), estado (pendiente / acreditado / vencido / no_reembolsado / a_reembolsar / en_revision / reembolsado desde C-12), acreditado_en (desde C-12 significa «momento en que la clínica recibió el dinero»: también lo tiene todo `a_reembolsar`, y es el día en que la seña entra en la caja), reembolsado_en + reembolsado_por_usuario_id + reembolso_referencia (los tres presentes si y solo si el estado es `reembolsado`, estado final; referencia de 3 a 64 caracteres), monto_reportado y moneda_reportada (lo que informó la pasarela cuando no coincidió con la seña, RN-SN-09), referencia externa única (`ref_unica`, idempotencia del webhook; en transferencia es el código corto del concepto).
- Relaciones: *───1 Turno.
- Constraints: referencia externa única; ausente NO reembolsa (queda como recupero/no_reembolsado, R9); `a_reembolsar` = devolución manual pendiente por cancelación con ≥ 24 h (RN-SN-04) o por un pago aprobado tardío o un horario perdido (RN-SN-05). `en_revision` = la pasarela aprobó un monto o una moneda distintos de la seña: no bloquea agenda y espera acreditación manual o devolución (RN-SN-09).

### PagoSenaAprobacion (desde C-06, RN-SN-10)
- Atributos: id, pago_id (FK indexada), mp_payment_id (único), estado (aplicado / en_revision / a_reembolsar / reembolsado desde C-12), monto_reportado (`Numeric`), moneda_reportada, reembolsado_en + reembolsado_por_usuario_id (FK indexada) + reembolso_referencia (devolución de un pago excedente, C-12), created_at.
- Un registro por cada pago aprobado de la pasarela: garantiza la idempotencia por id y deja trazabilidad de los sobrantes y de los pagos en revisión para la devolución manual.

### ConfiguracionSena (desde C-06)
- Singleton (`id = 1`, migración `006_sena_pagos`) editable por recepción/admin con auditoría: `sena_porcentaje` (`Numeric(5,2)`, 30.00 por defecto, mayor que 0 y hasta 100), `medios_habilitados` (subconjunto no vacío de `mercadopago` y `transferencia`, RN-PG-01), `texto_politica_reembolso`, `expiracion_mp_minutos` (30) y `expiracion_transferencia_minutos` (1440) —RN-SN-07—, y los datos de la cuenta para transferir (`transferencia_alias`, `transferencia_cbu` de 22 dígitos, `transferencia_titular`; RN-SN-08).
- El `PagoSena` guarda `porcentaje_aplicado` y `monto` al iniciar la seña: cambiar la configuración después no altera las señas ya iniciadas (RN-SN-03). La transferencia solo se ofrece al paciente si alias y CBU están cargados.
- Turno agrega `en_espera_vence_en` (`TIMESTAMPTZ`, obligatorio mientras el turno está `en_espera`).

### Disponibilidad
- Atributos: id, profesional_id, día_semana, hora_desde, hora_hasta, excepciones/feriados.
- Relaciones: base para el cálculo de horarios libres.

### Recordatorio
- Atributos (desde C-09, migración `010_recordatorios`): `id`, `turno_id`, `canal` (`whatsapp`), `estado` (`pendiente` / `enviado` / `confirmado` / `fallido` / `anulado`), `turno_inicio` (foto del horario que se recuerda, `TIMESTAMPTZ`), `generado_en`, `enviado_en` (la "fecha_envío": último envío; en v1 manual, cuando recepción abre WhatsApp), `enviado_por_usuario_id`, `confirmado_en`, `intentos_fallidos`, `proximo_intento_en`, `motivo` y `ultimo_error` (≤ 500, sanitizado, sin datos personales). El mensaje NO se guarda.
- Estado `anulado` (C-09 O7, agrega un quinto estado a los cuatro originales): el turno se canceló o se reprogramó (el recordatorio del horario anterior) o empezó sin que se avisara. Motivos: `sin_telefono`, `numero_invalido`, `sin_whatsapp`, `otro`, `error_proveedor` (estado `fallido`) y `turno_cancelado`, `turno_reprogramado`, `turno_iniciado` (estado `anulado`).
- Constraints: un solo recordatorio no `anulado` por (`turno_id`, `turno_inicio`) (índice único parcial); `confirmado` ⇔ `confirmado_en`; `enviado` ⇒ `enviado_en`; `fallido`/`anulado` ⇒ `motivo`. Marcar `ausente` o `atendido` NO anula el recordatorio (historial).
- Relaciones: *───1 Turno; *───0..1 Usuario (quien lo marcó enviado).

### Presupuesto (desde C-11)
- Atributos: id, `paciente_id`, `obra_social_id` (nula = particular), `estado` (`borrador`, `presentado`, `aceptado`, `rechazado`, `anulado`), `subtotal`, `cobertura_total`, `diferencial_total`, `total_paciente` (todos `NUMERIC(12,2)`, con `CHECK total_paciente = subtotal - cobertura_total + diferencial_total`), `notas`, `creado_por`, fechas de presentación, resolución y anulación (+ motivo).
- Relaciones: *───1 Paciente; 1───* PresupuestoLinea; 1───* PagoPresupuesto.
- Al presentarse queda congelado (las líneas guardan el precio, el porcentaje y el diferencial vigentes).

### PresupuestoLinea (desde C-11)
- Atributos: id, `presupuesto_id`, `orden`, `tratamiento_id`, `nomenclador_id` y `codigo_prestacion` (snapshot), pieza/cara opcionales, `cantidad` (1-99), `precio_unitario`, `cobertura_porcentaje`, `arancel_diferencial`, `importe_bruto`, `importe_cobertura`, `importe_diferencial`, `importe_paciente`.

### PagoPresupuesto (desde C-11; "Pago" en el ERD original)
- Atributos: id, `presupuesto_id`, `medio` (`mercadopago` / `transferencia`), `monto` (`NUMERIC(12,2)` > 0), `estado` (`registrado` / `anulado`), `fecha_cobro`, `referencia` (única por medio entre los registrados), `registrado_por`, datos de anulación (usuario, fecha, motivo). Se anula, nunca se borra.
- Contrato para C-12 (caja): se suma por `fecha_cobro` (índice propio) y medio los pagos `registrado`, junto con las señas de `PagoSena`.
- Nota: el pago de SEÑA del turno vive en `PagoSena` (entidad propia desde C-06), no en `PagoPresupuesto`.

```
Turno 1───* PagoSena (seña: pendiente → acreditado/bloquea → vencido/no_reembolsado/a_reembolsar → reembolsado)
```

### CierreCaja y CierreCajaLinea (desde C-12)
- `CierreCaja`: id, `dia` (`DATE`, día calendario de la clínica), `estado` (`vigente` / `anulado`), `total_ingresos`, `total_egresos`, `total_neto` (`NUMERIC(14,2)`, `total_neto = total_ingresos - total_egresos`), `observaciones` (≤ 500), `cerrado_por` + `cerrado_en`, y los datos de anulación (`anulado_por`, `anulado_en`, `anulado_motivo` de 3 a 300). Índice único parcial `(dia) WHERE estado = 'vigente'`: un cierre vigente por día. Un trigger rechaza cualquier cambio salvo `vigente → anulado`; corregir un día es anular el cierre y volver a cerrarlo.
- `CierreCajaLinea`: id, `cierre_id` (FK, cubierta por el único `(cierre_id, concepto, medio)`), `concepto` (`sena` / `pago_presupuesto` / `devolucion_sena`), `medio` (`mercadopago` / `transferencia`), `cantidad`, `total` (`NUMERIC(14,2)`). Las líneas son inmutables (trigger).
- Migración `009_caja_cierres_devol`; también crea la extensión `unaccent` (búsqueda de pacientes sin acentos).

### ObraSocial / Nomenclador
- Atributos: id, nombre OS, código nomenclador, descripción, cobertura.
- Seed: nomenclador OS AR precargado en v1.

### Usuario / Rol
- Atributos: id, nombre, credenciales, rol (odontólogo / recepción-admin).
- Nota: el paciente no tiene usuario (reserva pública con nombre + teléfono).

### RegistroAuditoria
- Atributos: id, usuario, acción, entidad_afectada, fecha_hora.
- Cubre roles y auditoría básica de v1.

## Seed data inicial

- Roles: odontólogo, recepción/admin.
- Nomenclador de obras sociales AR precargado.
- Tabla tratamiento→duración inicial (nombre + costo base + duración_minutos; seed aportado por la clínica, placeholder explícito si falta — C-02).
- VARIOS profesionales y sillones iniciales (multi-odontólogo/multi-sillón día 1, Resolución 2026-09-30 nº1 — no uno solo).
