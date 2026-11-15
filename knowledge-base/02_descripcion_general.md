# Descripción General

## Stack tecnológico

Stack **congelado (Resoluciones 2026-09-30, ver `10_preguntas_abiertas.md` §Resoluciones y `AGENTS.md`)**. Toda mención previa a "sin definir" queda reemplazada por este stack.

| Capa | Tecnologías | Versión fijada (2026-11-15; fuente: `backend/requirements.txt`, `docker-compose.yml`, `frontend/*/package.json`) |
|------|--------------|----------------|
| Frontend | React + TypeScript + Vite (requisito: mobile-first, la mayoría reserva desde el teléfono) | React 19.3.1 · TypeScript 6.0.3 · Vite 8.3.5 · Node 24 (CI) |
| Backend | Python + FastAPI + SQLAlchemy (+ Alembic) | Python 3.12 · FastAPI 0.142.2 · SQLAlchemy 2.0.54 · Alembic 1.20.0 |
| Base de datos | PostgreSQL (persistencia: turnos, pacientes, agenda, auditoría) | PostgreSQL 16 |
| Colas / async | Redis (workers p/ jobs pesados) | Redis 7 · arq 0.28.0 |
| Auth | JWT (expiración corta + refresh) | PyJWT 2.15.1 |
| Mensajería WhatsApp | MANUAL v1: links `wa.me/` con mensajes preformateados, sin API paga (abstracción provider para migrar después) — ver `10_preguntas_abiertas.md` | — |
| Calendario | Google Calendar API (sincronía bidireccional) | — |
| Pagos | Mercado Pago SDK + transferencia bancaria | — |
| Contenedores | Docker / Docker Compose (healthchecks) | — |
| E2E | Playwright | `@playwright/test` 1.64.1 |

## Arquitectura general

Aplicación web con dos superficies:

```
Paciente (móvil, sin login) → Reserva pública → API → DB
Recepción / Odontólogo (panel) → Gestión + agenda → API → DB
API → WhatsApp (recordatorios/confirmación) · Google Calendar (sincronía) · Mercado Pago (cobros)
```

- **Reserva pública**: acceso sin autenticación, identifica al paciente por nombre + teléfono por turno.
- **Panel de control**: agenda por profesional/día/semana, pacientes, ocupación, ausentismo, caja.
- **Multi-odontólogo / multi-sillón desde el día 1** (Resolución 2026-09-30 nº1): cada turno asigna `profesional_id` + `sillon_id`; el anti-solape controla ambos recursos.
- **Tratamientos como entidad** (Resolución 2026-09-30 nº3): cada tratamiento define nombre, costo base y `duracion_minutos` (el `fin` del turno deriva de la duración).
- **Trabajos programados**: envío de recordatorios WhatsApp y sincronización con Google Calendar.
- Diseño mobile-first como criterio transversal (sin restricciones de plataforma).

## Integraciones externas

| Servicio | Propósito | Tipo |
|----------|-----------|------|
| WhatsApp MANUAL v1 (links `wa.me/` preformateados; abstracción provider p/ migrar a API después) | Recordatorios y confirmación de turnos con botones como links con código de gestión | manual |
| Google Calendar | Sincronía bidireccional con la agenda del profesional (hoy es el sistema principal en uso) | API REST / OAuth |
| Mercado Pago | Cobro de turnos/presupuestos | SDK / API |

Sin obra social/facturación electrónica en v1 más allá del nomenclador precargado y Mercado Pago.

## API REST (stack congelado: FastAPI; recursos a exponer por los changes C-01…C-13)

Recursos principales: disponibilidad/horarios libres, turnos (crear, cancelar, reprogramar, confirmar), pacientes, profesionales, sillones, tratamientos (con duración), recordatorios, presupuestos, pagos, sincronización de calendario, auditoría, exportación masiva.
