# Preguntas Abiertas

## Aviso de ingest

- **PDF no ingerido**: `docs/discovery/discovery.pdf` NO fue parseado (fallo previo de parser). Se asumió que equivale a `docs/discovery/discovery.md` (SU-01 en `09_decisiones_y_supuestos.md`). Su contenido debe validarse manualmente contra esta KB; si trae material exclusivo, incorporarlo a los canónicos correspondientes.
- **Fuente raíz ausente**: no existe `discovery/discovery.md` en la raíz (la discovery de discovery-research del 2026-09-29 vive en `docs/discovery/discovery.md` + sección `discovery` de `.active-orchestrator-state.json`, ambas ingeridas). Sin acción requerida salvo que aparezca ese archivo.

## Inconsistencias detectadas

### IN-01 — Orden del MVP: dos versiones
**Documento A dice**: discovery §3 prioriza núcleo 1, 2 y 3 (reserva, cancelación/reprogramación, recordatorios).
**Documento B dice**: discovery §5 ordena "panel admin → recordatorio WhatsApp → reserva online → cancelación/reprogramación → agenda por profesional".
**Impacto**: cambia qué se construye primero.
**Resolución propuesta**: adoptar el orden de §3 (paciente primero) salvo indicación contraria del decisor.

### IN-02 — Reprogramación y ventana de 24 hs
**Documento A dice**: discovery §7 fija 24 hs solo para cancelación.
**Documento B dice**: casos de uso (§3, punto 2) piden cancelar o reprogramar "respetando la anticipación mínima".
**Impacto**: RN-TU-02 quedó asumida, no explícita.
**Resolución propuesta**: aplicar la misma ventana a reprogramación (ya reflejado en RN-TU-02) salvo corrección.

## Preguntas abiertas (priorizadas)

| Prioridad | Pregunta | Bloquea | Decisor |
|-----------|----------|---------|---------|
| Alta | ¿Uno o varios odontólogos/sillones desde el día 1? | Modelo de agenda (04) y anti-solape | Product Owner |
| Alta | ¿WhatsApp manual o automático vía API (costo por mensaje)? | Diseño de notificaciones y costos (RN-WA-03) | Product Owner |
| Alta | ¿Tabla concreta tratamiento→duración para la v1? | Seed data y cálculo de horarios | Admin/clínica |
| Alta | ¿Stack tecnológico (frontend, backend, DB, hosting)? | Toda implementación (02, 08) | Equipo técnico |
| Media | ¿Login de paciente o solo nombre + teléfono por turno? | Auth y modelo Paciente/Usuario | Product Owner |
| Media | Resolución de conflictos de sincronía con Google Calendar (RN-GC-02) | Integración GCal | Equipo técnico |
| Media | ¿El anti-solape de v1 controla sillón además de profesional? | Lógica de disponibilidad (SU-03) | Product Owner |
| Media | Confirmar cifras de mercado (ej. DentalSoft "+300 clínicas / −82% ausencias" son autodeclaraciones sin auditoría) | Métricas de éxito (01) | Product Owner |
| Baja | ¿Una sola sede en v1 (SU-02)? | Modelo de datos | Product Owner |
| Baja | Granularidad de permisos odontólogo vs. recepción/admin | RBAC (03) | Product Owner |

[DISCOVERY] `stack` could not be inferred with confidence from the source docs. Please confirm: qué tecnologías (frontend, backend, DB, hosting) usará el proyecto — las fuentes declaran libertad total de stack.
