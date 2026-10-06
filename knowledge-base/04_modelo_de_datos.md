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
Paciente 1───1 Ficha ───* Odontograma(FDI) / Presupuesto
Presupuesto 1───* Pago (MP / transferencia)
Turno 1───* Recordatorio (WhatsApp)
Profesional 1───* Disponibilidad (franjas configurables)
Usuario *───1 Rol (paciente-público / odontólogo / recepción-admin)
Turno *───* EventoCalendar (sincronía bidireccional GCal)
*───* RegistroAuditoria (quién, qué, cuándo)
ObraSocial 1───* Nomenclador (precargado AR)
```

## Entidades

### Paciente
- Atributos: id, nombre, teléfono (identificador operativo, sin login), obra social (opcional), notas.
- Relaciones: 1───* Turno; 1───1 Ficha.
- Constraints: teléfono requerido para reserva; unicidad operativa por teléfono (a confirmar).

### Ficha
- Atributos: id, paciente_id, antecedentes, historia de turnos.
- Relaciones: *───* Odontograma FDI básico; *───* Presupuesto.

### Profesional (odontólogo/a)
- Atributos: id, nombre, matrícula, especialidad.
- Relaciones: 1───* Turno; 1───* Disponibilidad.
- Constraints: sin superposición de turnos por profesional desde el día 1 — multi-odontólogo día 1 (Resolución 2026-09-30 nº1); garantía en DB con `EXCLUDE USING gist` parcial por estado (estrategia A del DDL de C-01: dos EXCLUDE —profesional + rango y sillón/box + rango— con `WHERE estado IN ('reservado','confirmado')`), RN-TU-03.

### Sillón
- Atributos: id, nombre/identificador, estado.
- Relaciones: 1───* Turno (ocupación por sillón).
- Constraints: sin superposición de turnos por sillón/box desde el día 1 — multi-sillón día 1 (Resolución 2026-09-30 nº1); garantía en DB con `EXCLUDE USING gist` parcial por estado (estrategia A del DDL de C-01), RN-TU-03.

### Tratamiento
- Atributos: id, nombre, costo base (`Numeric`, no float), duración_minutos (duración estimada en minutos, configurable por admin, no fija en código).
- Relaciones: 1───* Turno.
- Constraints: duración > 0 (`CHECK`); tabla tratamiento→duración editable por admin (RN-TU-05); seed inicial aportado por la clínica (si falta, placeholder explícito documentado — C-02/C-04).

### Turno
- Atributos: id, paciente_id, profesional_id, sillon_id, tratamiento_id, inicio, fin (derivado de duración), estado (reservado / confirmado / cancelado / ausente / atendido; más `en_espera` desde C-06 —ver GAP en `CHANGES.md` header—), origen (web / manual / WhatsApp), código de gestión pública.
- Relaciones: 1───* Recordatorio; *───* EventoCalendar; 1───* PagoSena (desde C-06).
- Constraints: fin = inicio + duración del tratamiento; no solape por profesional NI por sillón/box desde día 1 (RN-TU-03, EXCLUDE parciales por estado, estrategia A); cancelación/reprogramación solo con ≥ 24 hs de anticipación. Estado `en_espera` (C-06): pre-reserva con seña pendiente que NO bloquea agenda ni genera recordatorio/calendario; solo la seña acreditada (`reservado`) bloquea el slot (R8).
- Índices: (profesional_id, inicio), (sillon_id, inicio), (paciente_id, inicio), estado; índice sobre cada FK.

### PagoSena (desde C-06 — solo modelado documental; no implementado antes de C-06)
- Atributos: id, turno_id, medio (Mercado Pago / transferencia), monto (`Numeric`, seña fija configurable ej. 30% del valor de la consulta), estado (pendiente / acreditado / vencido / no_reembolsado), referencia externa única (`ref_unica`, idempotencia del webhook).
- Relaciones: *───1 Turno.
- Constraints: referencia externa única; ausente NO reembolsa (queda como recupero/no_reembolsado, R9).

### Disponibilidad
- Atributos: id, profesional_id, día_semana, hora_desde, hora_hasta, excepciones/feriados.
- Relaciones: base para el cálculo de horarios libres.

### Recordatorio
- Atributos: id, turno_id, canal (WhatsApp), estado (pendiente / enviado / confirmado / fallido), fecha_envío.
- Relaciones: *───1 Turno.

### Presupuesto
- Atributos: id, paciente_id, líneas (tratamiento + cobertura OS), total, estado.
- Relaciones: 1───* Pago.

### Pago
- Atributos: id, presupuesto_id, medio (Mercado Pago / transferencia), monto (`Numeric`), estado, referencia externa.
- Nota: el pago de SEÑA del turno vive en `PagoSena` (entidad propia desde C-06), no en `Pago` (atado a `Presupuesto`).

```
Turno 1───* PagoSena (seña: pendiente → acreditado/bloquea → vencido/no_reembolsado)
```

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
