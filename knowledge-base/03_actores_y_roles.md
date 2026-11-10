# Actores y Roles

## Actores del sistema

| Actor | Descripción | Cómo interactúa |
|-------|-------------|-----------------|
| Paciente | Persona que reserva atención odontológica | Reserva pública web (sin login: nombre + teléfono); cancela/reprograma; confirma por WhatsApp |
| Odontólogo/a | Profesional que atiende | Panel de control: ve su agenda por día/semana |
| Recepción/admin | Personal del consultorio/clínica | Panel de control: gestiona agenda, pacientes, ausentismo, ocupación por sillón, caja y liquidaciones |

Duda abierta: si opera uno o varios odontólogos desde el día 1 (impacta agenda por profesional y sillones) — ver `10_preguntas_abiertas.md`.

## RBAC — Matriz de permisos

| Rol | Turnos | Pacientes | Agenda/disponibilidad | Tratamientos y duraciones | Caja/liquidaciones | Nomenclador OS | Auditoría/exportación |
|-----|--------|-----------|----------------------|---------------------------|--------------------|----------------|----------------------|
| Paciente (sin login) | Crear (propios) / cancelar / reprogramar (propios, regla 24 hs) | Ver y editar solo sus datos del turno | Lectura de horarios libres | — | Pagar (MP/transferencia) | — | — |
| Odontólogo/a | Lectura (su agenda) + marcar atendido (sus turnos) | Lectura (sus pacientes: turno atendido) y escritura clínica (ficha y odontograma) con atención en los últimos 12 meses o turno pendiente; presupuestos: lectura; pagos: — | Lectura | Lectura | — | Lectura | — |
| Recepción/admin | CRUD total | CRUD total | CRUD total | CRUD total | CRUD total | Lectura/administración | Lectura/generación |

Desde C-08 (decisiones O5 y O6, 2026-11-09): el odontólogo/a ve únicamente la agenda de la profesional asociada a su usuario (`usuario.profesional_id`) y no recibe el teléfono del paciente; recepción y admin ven todas las agendas, dan de alta turnos manuales y marcan atendido, ausente o cancelan. Si una persona tiene más de un rol, vale el permiso más amplio.

Desde C-11 (decisiones O2-O4, O15 y O16, 2026-11-10) el odontólogo/a deja de ser de solo lectura: **marca `atendido` sus propios turnos** (O15; no marca `ausente`, no cancela ni da altas manuales, y nadie deshace un `atendido`) y **escribe ficha y odontograma de sus pacientes** (los que tienen un turno `atendido` con su profesional, O2) mientras tenga una atención en los últimos 12 meses (365 días) o un turno pendiente con ellos (O16); fuera de esa ventana solo lee. Ve DNI y número de afiliado pero nunca teléfono ni email (O3), lee presupuestos sin pagos y no escribe datos administrativos, presupuestos ni pagos (O4). Ver RN-CL-01 a RN-CL-04 y RN-TU-12.

## Rutas públicas

- Ver horarios libres y reservar turno (nombre + teléfono, sin registro obligatorio).
- Cancelar / reprogramar turno propio (con enlace o código por turno, respetando 24 hs).
- Confirmación vía botones de WhatsApp.

Todo lo demás (panel, agenda por profesional, caja, administración) requiere autenticación con rol.
