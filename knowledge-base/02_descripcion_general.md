# Descripción General

## Stack tecnológico

Stack **sin definir** (libertad total según discovery §9). No inventar elección de stack: ver `10_preguntas_abiertas.md`.

| Capa | Tecnologías | Versión mínima |
|------|--------------|----------------|
| Frontend | Sin definir (requisito: mobile-first, la mayoría reserva desde el teléfono) | — |
| Backend | Sin definir | — |
| Base de datos | Sin definir (se requiere persistencia: turnos, pacientes, agenda, auditoría) | — |
| Mensajería WhatsApp | A definir: manual vs. API (tipo Twilio/Meta) — ver `10_preguntas_abiertas.md` | — |
| Calendario | Google Calendar API (sincronía bidireccional) | — |
| Pagos | Mercado Pago SDK + transferencia bancaria | — |

## Arquitectura general

Aplicación web con dos superficies:

```
Paciente (móvil, sin login) → Reserva pública → API → DB
Recepción / Odontólogo (panel) → Gestión + agenda → API → DB
API → WhatsApp (recordatorios/confirmación) · Google Calendar (sincronía) · Mercado Pago (cobros)
```

- **Reserva pública**: acceso sin autenticación, identifica al paciente por nombre + teléfono por turno.
- **Panel de control**: agenda por profesional/día/semana, pacientes, ocupación, ausentismo, caja.
- **Trabajos programados**: envío de recordatorios WhatsApp y sincronización con Google Calendar.
- Diseño mobile-first como criterio transversal (sin restricciones de plataforma).

## Integraciones externas

| Servicio | Propósito | Tipo |
|----------|-----------|------|
| WhatsApp (Twilio / Meta API, o manual — a definir) | Recordatorios y confirmación de turnos con botones | API / manual |
| Google Calendar | Sincronía bidireccional con la agenda del profesional (hoy es el sistema principal en uso) | API REST / OAuth |
| Mercado Pago | Cobro de turnos/presupuestos | SDK / API |

Sin obra social/facturación electrónica en v1 más allá del nomenclador precargado y Mercado Pago.

## API REST (orientativo, a diseñar cuando se defina el stack)

Recursos principales: disponibilidad/horarios libres, turnos (crear, cancelar, reprogramar, confirmar), pacientes, profesionales, sillones, tratamientos (con duración), recordatorios, presupuestos, pagos, sincronización de calendario, auditoría, exportación masiva.
