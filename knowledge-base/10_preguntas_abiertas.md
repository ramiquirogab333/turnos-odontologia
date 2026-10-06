# Preguntas Abiertas

## Aviso de ingest

- **PDF no ingerido**: `docs/discovery/informe-discovery.pdf` NO fue parseado (fallo previo de parser). Se asumió que equivale a `docs/discovery/informe-discovery.md` (SU-01 en `09_decisiones_y_supuestos.md`). Su contenido debe validarse manualmente contra esta KB; si trae material exclusivo, incorporarlo a los canónicos correspondientes.
- **Fuente raíz ausente**: no existe `discovery/discovery.md` en la raíz (la discovery de discovery-research del 2026-09-29 vive en `docs/discovery/informe-discovery.md` + sección `discovery` de `.active-orchestrator-state.json`, ambas ingeridas). Sin acción requerida salvo que aparezca ese archivo.

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

## Resoluciones — decisiones del Product Owner (2026-09-30)

1. **Multi-odontólogo / multi-sillón desde el día 1.** El modelo de datos y la agenda contemplan asignación de profesional/recurso por turno. Impacta: `04_modelo_de_datos.md` (Profesional, Sillón/Recurso, Turno), `06_funcionalidades.md`, `08_arquitectura_propuesta.md`, `CHANGES.md` (C-02, C-04, C-08). ⚠️ Estos archivos aún describen el estado previo — sincronizar antes de implementar.
2. **WhatsApp MANUAL en v1.** Sin API paga de envío automático; la v1 genera links `wa.me/` con mensajes preformateados. La abstracción provider se mantiene para migrar a API después. Impacta: `02_descripcion_general.md`, `05_reglas_de_negocio.md` (RN-WA-XX), `06_funcionalidades.md`, `CHANGES.md` (C-09).
3. **Entidad Tratamientos con duración.** Cada tratamiento define nombre, costo base y duración estimada en minutos (default para el cálculo de bloques de agenda). Impacta: `04_modelo_de_datos.md` (nueva entidad), `05_reglas_de_negocio.md`, `CHANGES.md` (C-02 seed, C-04).
4. **Stack congelado.** Backend Python + FastAPI + SQLAlchemy (+Alembic) + PostgreSQL + Redis + JWT + Docker Compose; Frontend React + TypeScript + Vite; E2E Playwright — ver `AGENTS.md`. Impacta: `02_descripcion_general.md` y `08_arquitectura_propuesta.md` (aún dicen "sin definir").

## Preguntas abiertas (priorizadas)

| Prioridad | Pregunta | Bloquea | Decisor |
|-----------|----------|---------|---------|
| Alta ✅ | ¿Uno o varios odontólogos/sillones desde el día 1? | Modelo de agenda (04) y anti-solape | Product Owner |
| Alta ✅ | ¿WhatsApp manual o automático vía API (costo por mensaje)? | Diseño de notificaciones y costos (RN-WA-03) | Product Owner |
| Alta ✅ | ¿Tabla concreta tratamiento→duración para la v1? | Seed data y cálculo de horarios | Admin/clínica |
| Alta ✅ | ¿Stack tecnológico (frontend, backend, DB, hosting)? | Toda implementación (02, 08) | Equipo técnico |
| Media | ¿Login de paciente o solo nombre + teléfono por turno? | Auth y modelo Paciente/Usuario | Product Owner |
| Media | Resolución de conflictos de sincronía con Google Calendar (RN-GC-02) | Integración GCal | Equipo técnico |
| Media | ¿El anti-solape de v1 controla sillón además de profesional? | Lógica de disponibilidad (SU-03) | Product Owner |
| Media | Confirmar cifras de mercado (ej. DentalSoft "+300 clínicas / −82% ausencias" son autodeclaraciones sin auditoría) | Métricas de éxito (01) | Product Owner |
| Baja | ¿Una sola sede en v1 (SU-02)? | Modelo de datos | Product Owner |
| Baja | Granularidad de permisos odontólogo vs. recepción/admin | RBAC (03) | Product Owner |

[DISCOVERY] `stack` could not be inferred with confidence from the source docs. Please confirm: qué tecnologías (frontend, backend, DB, hosting) usará el proyecto — las fuentes declaran libertad total de stack.
