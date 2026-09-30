# Flujos Principales

## Flujo 1: Reserva online de turno
**Disparador**: el paciente quiere un turno.
**Actor**: Paciente (sin login).

**Pasos**:
1. Paciente abre la reserva pública desde el celular y elige tratamiento/profesional.
2. Frontend pide horarios libres; API los calcula desde disponibilidad + turnos existentes (anti-solape).
3. Paciente elige horario e ingresa nombre + teléfono.
4. API crea el turno en estado reservado (fin = inicio + duración del tratamiento).
5. Sistema agenda recordatorio WhatsApp y sincroniza el evento a Google Calendar.

**Casos de error**:
- Horario tomado en simultáneo por otro paciente → se rechaza y se ofrecen alternativas.
- Datos incompletos (falta nombre o teléfono) → se pide completar, no se crea el turno.

## Flujo 2: Cancelación / reprogramación por el paciente
**Disparador**: el paciente no puede asistir o quiere cambiar el horario.
**Actor**: Paciente.

**Pasos**:
1. Paciente accede con su enlace/código de gestión del turno.
2. API valida anticipación ≥ 24 hs; si es menor, rechaza con el motivo.
3. Cancelación: el turno pasa a cancelado y el horario se libera. Reprogramación: elige nuevo horario libre y el turno se mueve.
4. Sistema actualiza Google Calendar y cancela/reprograma recordatorios pendientes.

**Casos de error**:
- Anticipación < 24 hs → rechazo con mensaje (RN-TU-01/RN-TU-02).
- Nuevo horario ya ocupado → se ofrecen alternativas.

## Flujo 3: Recordatorio y confirmación por WhatsApp
**Disparador**: turno próximo (trabajo programado).
**Actor**: Sistema → Paciente.

**Pasos**:
1. Scheduler detecta turnos próximos sin recordar.
2. API envía recordatorio por WhatsApp con botones (confirmar / cancelar).
3. Paciente confirma → turno pasa a confirmado. Si cancela, aplica Flujo 2 (ventana 24 hs).

```
Scheduler → WhatsApp API → Paciente
Paciente → (botón) → API → DB (estado actualizado)
```

**Casos de error**:
- Envío fallido → se reintenta y queda registrado (estado fallido).
- Modalidad manual vs. automática aún sin definir (ver `10_preguntas_abiertas.md`).

## Flujo 4: Consulta de agenda por el profesional
**Disparador**: el odontólogo/a quiere ver a quién atiende.
**Actor**: Odontólogo/a (autenticado).

**Pasos**:
1. Ingresa al panel y selecciona día/semana.
2. API devuelve sus turnos con paciente, tratamiento y estado.
3. La vista refleja la sincronía con Google Calendar.

## Flujo 5: Gestión admin (pacientes, ausentismo, caja)
**Disparador**: operación diaria del consultorio.
**Actor**: Recepción/admin (autenticado).

**Pasos**:
1. Gestiona pacientes (alta, ficha, ausentes) y ocupación por sillón.
2. Configura disponibilidad y duraciones por tratamiento.
3. Registra presupuestos con cobertura OS y cobros (MP/transferencia).
4. Genera cierres de caja y exporta datos; todo queda auditado.
