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
| Odontólogo/a | Lectura (su agenda) | Lectura (sus pacientes) | Lectura | Lectura | — | Lectura | — |
| Recepción/admin | CRUD total | CRUD total | CRUD total | CRUD total | CRUD total | Lectura/administración | Lectura/generación |

La granularidad exacta de permisos entre odontólogo y recepción/admin no está detallada en las fuentes y debe confirmarse.

## Rutas públicas

- Ver horarios libres y reservar turno (nombre + teléfono, sin registro obligatorio).
- Cancelar / reprogramar turno propio (con enlace o código por turno, respetando 24 hs).
- Confirmación vía botones de WhatsApp.

Todo lo demás (panel, agenda por profesional, caja, administración) requiere autenticación con rol.
