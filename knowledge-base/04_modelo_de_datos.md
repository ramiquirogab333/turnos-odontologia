# Modelo de Datos

Entidades inferidas de las fuentes (discovery + state). Nombres y tipos orientativos; el diseño físico se define con el stack.

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
- Constraints: sin superposición de turnos por profesional (RN-TU-03).

### Sillón
- Atributos: id, nombre/identificador, estado.
- Relaciones: 1───* Turno (ocupación por sillón).
- Constraints: sin superposición de turnos por sillón (extensión de RN-TU-03, a confirmar si aplica desde v1).

### Tratamiento
- Atributos: id, nombre, duración_minutos (configurable por admin, no fija en código), precio base.
- Relaciones: 1───* Turno.
- Constraints: duración > 0; tabla tratamiento→duración concreta de v1 pendiente (ver `10_preguntas_abiertas.md`).

### Turno
- Atributos: id, paciente_id, profesional_id, sillon_id, tratamiento_id, inicio, fin (derivado de duración), estado (reservado / confirmado / cancelado / ausente / atendido), origen (web / manual / WhatsApp), código de gestión pública.
- Relaciones: 1───* Recordatorio; *───* EventoCalendar.
- Constraints: fin = inicio + duración del tratamiento; no solape por profesional (ni por sillón); cancelación/reprogramación solo con ≥ 24 hs de anticipación.
- Índices: (profesional_id, inicio), (sillon_id, inicio), (paciente_id, inicio), estado.

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
- Atributos: id, presupuesto_id, medio (Mercado Pago / transferencia), monto, estado, referencia externa.

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
- Tabla tratamiento→duración inicial (pendiente de definición — ver `10_preguntas_abiertas.md`).
- Profesional(es) y sillón(es) iniciales según respuesta de "uno o varios odontólogos".
