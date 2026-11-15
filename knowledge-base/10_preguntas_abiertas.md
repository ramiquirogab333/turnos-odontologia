# Preguntas Abiertas

## Aviso de ingest

- **PDF no ingerido**: `docs/discovery/informe-discovery.pdf` NO fue parseado (fallo previo de parser). Se asumió que equivale a `docs/discovery/informe-discovery.md` (SU-01 en `09_decisiones_y_supuestos.md`). Su contenido debe validarse manualmente contra esta KB; si trae material exclusivo, incorporarlo a los canónicos correspondientes.
- **Fuente raíz ausente**: no existe `discovery/discovery.md` en la raíz (la discovery de discovery-research del 2026-09-29 vive en `docs/discovery/informe-discovery.md` + sección `discovery` de `.active-orchestrator-state.json`, ambas ingeridas). Sin acción requerida salvo que aparezca ese archivo.

## Inconsistencias detectadas

### IN-01 — Orden del MVP: dos versiones (RESUELTA 2026-09-30, roadmap)
**Resolución**: se adoptó el orden de §3 (paciente primero) con un vertical slice inicial: `CHANGES.md` implementó reserva (C-01, C-05, C-06), cancelación/reprogramación (C-07) y recordatorios (C-09) antes que el resto del panel. El roadmap se completó el 2026-11-15 con C-01..C-16 archivados.
**Documento A dice**: discovery §3 prioriza núcleo 1, 2 y 3 (reserva, cancelación/reprogramación, recordatorios).
**Documento B dice**: discovery §5 ordena "panel admin → recordatorio WhatsApp → reserva online → cancelación/reprogramación → agenda por profesional".
**Impacto**: cambia qué se construye primero.
**Resolución propuesta (aplicada)**: adoptar el orden de §3 (paciente primero) salvo indicación contraria del decisor.

### IN-02 — Reprogramación y ventana de 24 hs (RESUELTA 2026-11-06, C-07)
**Resolución**: el Product Owner confirmó la misma ventana de 24 h para reprogramar (RN-TU-02 confirmada).
**Documento A dice**: discovery §7 fija 24 hs solo para cancelación.
**Documento B dice**: casos de uso (§3, punto 2) piden cancelar o reprogramar "respetando la anticipación mínima".
**Impacto**: RN-TU-02 quedó asumida, no explícita.
**Resolución propuesta**: aplicar la misma ventana a reprogramación (ya reflejado en RN-TU-02) salvo corrección.

## Resoluciones — decisiones del Product Owner (2026-09-30)

1. **Multi-odontólogo / multi-sillón desde el día 1.** El modelo de datos y la agenda contemplan asignación de profesional/recurso por turno. Impacta: `04_modelo_de_datos.md` (Profesional, Sillón/Recurso, Turno), `06_funcionalidades.md`, `08_arquitectura_propuesta.md`, `CHANGES.md` (C-02, C-04, C-08). Sincronizado en esos archivos e implementado (C-01, C-02, C-08).
2. **WhatsApp MANUAL en v1.** Sin API paga de envío automático; la v1 genera links `wa.me/` con mensajes preformateados. La abstracción provider se mantiene para migrar a API después. Impacta: `02_descripcion_general.md`, `05_reglas_de_negocio.md` (RN-WA-XX), `06_funcionalidades.md`, `CHANGES.md` (C-09).
3. **Entidad Tratamientos con duración.** Cada tratamiento define nombre, costo base y duración estimada en minutos (default para el cálculo de bloques de agenda). Impacta: `04_modelo_de_datos.md` (nueva entidad), `05_reglas_de_negocio.md`, `CHANGES.md` (C-02 seed, C-04).
4. **Stack congelado.** Backend Python + FastAPI + SQLAlchemy (+Alembic) + PostgreSQL + Redis + JWT + Docker Compose; Frontend React + TypeScript + Vite; E2E Playwright — ver `AGENTS.md`. Impacta: `02_descripcion_general.md` y `08_arquitectura_propuesta.md` (sincronizados; versiones fijadas en `02` §Stack tecnológico).

## Preguntas abiertas (priorizadas)

| Prioridad | Pregunta | Bloquea | Decisor |
|-----------|----------|---------|---------|
| Alta ✅ | ¿Uno o varios odontólogos/sillones desde el día 1? | Modelo de agenda (04) y anti-solape | Product Owner |
| Alta ✅ | ¿WhatsApp manual o automático vía API (costo por mensaje)? | Diseño de notificaciones y costos (RN-WA-03) | Product Owner |
| Alta ✅ | ¿Tabla concreta tratamiento→duración para la v1? | Seed data y cálculo de horarios | Admin/clínica |
| Alta ✅ | ¿Stack tecnológico (frontend, backend, DB, hosting)? | Toda implementación (02, 08) | Equipo técnico |
| Media ✅ | ¿Login de paciente o solo nombre + teléfono por turno? — cerrada (2026-11-14): sin login de paciente; reserva con nombre + teléfono y gestión del turno por enlace (DD-01, implementado en C-05/C-07/C-09) | Auth y modelo Paciente/Usuario | Product Owner |
| Media ✅ | Resolución de conflictos de sincronía con Google Calendar (RN-GC-02) — cerrada en C-10 (2026-11-12): resolución manual con criterio visible, nunca auto-sobrescritura (ver RN-GC-02 y DD-05) | Integración GCal | Equipo técnico |
| Media ✅ | ¿El anti-solape de v1 controla sillón además de profesional? — cerrada (2026-11-14): sí, controla ambos; dos `EXCLUDE USING gist` parciales (profesional y sillón) desde la migración `001_create_agenda` (C-01), ampliados en `007` (C-08). SU-03 validado | Lógica de disponibilidad (SU-03) | Product Owner |
| Media ✅ | Confirmar cifras de mercado (ej. DentalSoft "+300 clínicas / −82% ausencias" son autodeclaraciones sin auditoría) — cerrada como no bloqueante (2026-11-15): las cifras no se confirmaron y no se usan como criterio de aceptación; las métricas de éxito son las propias de `01_vision_y_objetivos.md` y `11_analisis_competidores.md` las cita como autodeclaradas | Métricas de éxito (01) | Product Owner |
| Baja ✅ | ¿Una sola sede en v1 (SU-02)? — cerrada para v1 (2026-11-14): una sola sede; el modelo no tiene entidad Sede y las pantallas del panel (C-14, C-16) no llevan selector de sede. Multi-sucursal queda fuera de v1 (requiere migración) | Modelo de datos | Product Owner |
| Baja ✅ | Granularidad de permisos odontólogo vs. recepción/admin — cerrada (2026-11-14): matriz de `03_actores_y_roles.md` §RBAC, implementada en C-03, ampliada en C-11 (D1, rutas por rol) y enmendada en C-13 (O6 auditoría solo admin, O7 exportación de pacientes solo admin) | RBAC (03) | Product Owner |

## Preguntas pendientes para la clínica (post-roadmap)

Surgieron como seguimientos de los changes archivados. El roadmap C-01..C-16 está cerrado (2026-11-15) y ninguna de estas preguntas lo bloqueó; no se implementan sin decisión explícita. El backlog técnico asociado está en `CHANGES.md` §Backlog post-roadmap.

| Prioridad | Pregunta | Origen | Bloquea | Decisor |
|-----------|----------|--------|---------|---------|
| Alta | ¿Cuánto tiempo se conserva el registro de auditoría y cuándo se purga? Plazo legal a confirmar con asesoría (Ley 25.326; la historia clínica tiene plazo mínimo propio por Ley 26.529). Hasta decidir: no se purga nada | C-13 O16 | Retención/purga (exige excepción al trigger de solo agregado) | Clínica + asesoría legal |
| Media | ¿Se puede deshacer un `ausente` marcado por error? Implicaría devolver una seña retenida a `acreditado` (toca R9 / RN de ausentismo) | C-12 O10 | Change de corrección de ausentes | Product Owner |
| Media | ¿Qué pasa con un pago `en_revision` vencido: se rechaza solo, se acredita o sigue manual? Hoy se lista y se resuelve a mano | C-09 O12, C-12 O6 b | Barrido automático en el worker de C-09 | Product Owner |
| Media | ¿Cómo se registra la devolución de un cobro de presupuesto hecha fuera del sistema (egreso de caja)? Ya decidido que va en un change propio (2026-11-11); falta definir la regla | C-12 O2 | Change de devolución de cobros | Product Owner |
| Baja | ¿Se necesitan honorarios por profesional y liquidación a obras sociales? Hoy la "liquidación" es solo el consolidado por medio de pago | C-12 O3 | Funcionalidad nueva (fuera de v1) | Product Owner |
| Baja | ¿Es correcto el rango de duración de un tratamiento (5 a 480 min, múltiplos de 5)? Hoy es un supuesto del equipo; cambiarlo es tocar una constante y su test | C-14 O12 | Ajuste de topes del catálogo | Admin/clínica |
| Media | La obra social "Particular" del seed (cobertura 0 %) convive con `obra_social_id = null` (también particular): ¿se desactiva la fila del seed, se oculta en la UI o se deja? Hoy el panel muestra `null` como "Sin obra social" y "Particular" como una obra social más (mismo resultado, 0 %) | C-16 O5 | Limpieza del seed de obras sociales | Product Owner + clínica |
| Baja | ¿Un cobro de un día pasado debe registrar la hora real? Hoy el panel envía las 12:00 de la clínica del día elegido para que caiga en el día de caja correcto `[SUPUESTO]` | C-16 O14 | Cobros retroactivos con hora exacta | Product Owner |

> Nota histórica del ingest (2026-09-29): el stack no podía inferirse de las fuentes. Resuelto el 2026-09-30 (Resolución 4). El **hosting/despliegue sigue sin definir**: queda como parte de C-17 en `CHANGES.md` §Backlog post-roadmap.
