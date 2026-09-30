# Funcionalidades

Organizadas por **épica** y luego por **historia de usuario** (formato US-NNN). Derivadas de discovery §3 y §5 y de `state.discovery`.

## Épica 1: Reserva online (núcleo MVP)

### US-001 — Ver horarios libres y reservar sin llamar
**Como** paciente
**Quiero** ver los horarios libres y reservar un turno sin llamar ni escribir por WhatsApp
**Para** conseguir turno rápido desde el celular

**Criterios de aceptación**:
- [ ] CA-1: Veo horarios libres por profesional/tratamiento desde el celular.
- [ ] CA-2: Reservo con nombre + teléfono, sin crear cuenta.
- [ ] CA-3: No se me ofrecen horarios superpuestos (RN-TU-03, RN-TU-07).

**Reglas relacionadas**: RN-TU-03, RN-TU-04, RN-TU-06, RN-TU-07, RN-GL-03

### US-002 — Cancelar turno
**Como** paciente
**Quiero** cancelar mi turno
**Para** liberar el horario cuando no puedo asistir

**Criterios de aceptación**:
- [ ] CA-1: Puedo cancelar con ≥ 24 hs de anticipación.
- [ ] CA-2: Con < 24 hs el sistema rechaza la cancelación e informa el motivo.

**Reglas relacionadas**: RN-TU-01

### US-003 — Reprogramar turno
**Como** paciente
**Quiero** reprogramar mi turno
**Para** cambiarlo de horario sin perder la reserva

**Criterios de aceptación**:
- [ ] CA-1: Elijo un nuevo horario libre disponible.
- [ ] CA-2: Respeta la ventana de 24 hs (RN-TU-02 a confirmar).

**Reglas relacionadas**: RN-TU-02, RN-TU-07

## Épica 2: Recordatorios WhatsApp (núcleo MVP)

### US-004 — Recibir recordatorio por WhatsApp
**Como** paciente
**Quiero** recibir recordatorios por WhatsApp
**Para** no olvidar mi turno

**Criterios de aceptación**:
- [ ] CA-1: Recibo recordatorio antes del turno.
- [ ] CA-2: Puedo confirmar con botones y el turno queda confirmado.

**Reglas relacionadas**: RN-WA-01, RN-WA-02

## Épica 3: Agenda profesional

### US-005 — Ver agenda por profesional
**Como** odontólogo/a
**Quiero** ver mi agenda del día/semana por profesional
**Para** saber a quién atiendo y cuándo

**Criterios de aceptación**:
- [ ] CA-1: Vista día y semana con pacientes y tratamientos.
- [ ] CA-2: Sin turnos superpuestos visibles.

**Reglas relacionadas**: RN-TU-03

### US-006 — Sincronizar con Google Calendar
**Como** odontólogo/a
**Quiero** que mi agenda sincronice con Google Calendar
**Para** tener un solo calendario actualizado

**Criterios de aceptación**:
- [ ] CA-1: Los turnos aparecen en Google Calendar y viceversa.

**Reglas relacionadas**: RN-GC-01, RN-GC-02

## Épica 4: Panel admin

### US-007 — Gestionar pacientes y ausentismo
**Como** recepción/admin
**Quiero** gestionar pacientes, ausentes, ocupación por sillón y cierres de caja desde un panel
**Para** operar el consultorio sin papel ni planillas dispersas

**Criterios de aceptación**:
- [ ] CA-1: Consulto fichas, marco ausentes, veo ocupación por sillón.
- [ ] CA-2: Genero cierres de caja y liquidaciones.

**Reglas relacionadas**: RN-GL-01, RN-GL-02

### US-008 — Configurar tratamientos y disponibilidad
**Como** recepción/admin
**Quiero** configurar duraciones por tratamiento y disponibilidad
**Para** que la agenda refleje la realidad del consultorio

**Criterios de aceptación**:
- [ ] CA-1: Edito la tabla tratamiento→duración sin tocar código.
- [ ] CA-2: Los horarios libres se recalculan con la nueva configuración.

**Reglas relacionadas**: RN-TU-04, RN-TU-05

## Épica 5: Ficha clínica y pagos

### US-009 — Ficha + odontograma + presupuesto con OS
**Como** recepción/admin
**Quiero** ficha de paciente con odontograma FDI básico y presupuestos con cobertura de obra social
**Para** registrar lo clínico-administrativo mínimo en v1

**Criterios de aceptación**:
- [ ] CA-1: Cargo odontograma FDI básico por paciente.
- [ ] CA-2: El presupuesto descuenta cobertura según nomenclador AR precargado.

**Reglas relacionadas**: RN-PG-02

### US-010 — Cobrar por Mercado Pago o transferencia
**Como** recepción/admin
**Quiero** cobrar por Mercado Pago o transferencia
**Para** registrar el pago del tratamiento

**Criterios de aceptación**:
- [ ] CA-1: Registro pagos con ambos medios y su estado.

**Reglas relacionadas**: RN-PG-01

## Épica 6: Plataforma

### US-011 — Roles y auditoría básica
**Como** recepción/admin
**Quiero** roles diferenciados y auditoría básica
**Para** saber quién hizo cada cambio

**Criterios de aceptación**:
- [ ] CA-1: Acciones del panel quedan auditadas (quién, qué, cuándo).

**Reglas relacionadas**: RN-GL-01

### US-012 — Exportación masiva
**Como** recepción/admin
**Quiero** exportar los datos masivamente
**Para** respaldar o migrar la información

**Criterios de aceptación**:
- [ ] CA-1: Exporto turnos/pacientes en formato tabular descargable.

**Reglas relacionadas**: RN-GL-02
