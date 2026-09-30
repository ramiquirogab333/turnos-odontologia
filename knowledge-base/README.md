# turnos-odontologia — Base de Conocimiento

Base de conocimiento generada por ingest silencioso (Mode A) desde `docs/discovery/discovery.md`, `docs/discovery/Validación Discovery.md` y la sección `discovery` de `.active-orchestrator-state.json` (2026-09-29). `docs/discovery/discovery.pdf` excluido del ingest — ver `10_preguntas_abiertas.md`.

## Índice de Archivos

| Archivo | Contenido |
|---------|-----------|
| [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito, objetivos por actor, alcance v1, fuera de alcance, métricas |
| [02_descripcion_general.md](02_descripcion_general.md) | Stack (sin definir), arquitectura, WhatsApp + GCal + MP |
| [03_actores_y_roles.md](03_actores_y_roles.md) | Paciente, odontólogo/a, recepción/admin; RBAC; rutas públicas |
| [04_modelo_de_datos.md](04_modelo_de_datos.md) | Dominios, ERD, 13 entidades, seed data |
| [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | 17 reglas RN-TU/RN-WA/RN-GC/RN-PG/RN-GL |
| [06_funcionalidades.md](06_funcionalidades.md) | 6 épicas, US-001 a US-012 |
| [07_flujos_principales.md](07_flujos_principales.md) | Reserva, cancelación/reprogramación, recordatorios WA, agenda, admin |
| [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones, estructura orientativa, seguridad, env vars |
| [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | DD-01 a DD-06, SU-01 a SU-04 |
| [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | Aviso PDF, IN-01/IN-02, 10 preguntas priorizadas |
| [11_analisis_competidores.md](11_analisis_competidores.md) | Extra: relevamiento 18+ sistemas, 3 frentes |

## Quick Start para Desarrolladores

1. Entender el dominio → [01](01_vision_y_objetivos.md), [03](03_actores_y_roles.md)
2. Entender los datos → [04](04_modelo_de_datos.md)
3. Entender las reglas → [05](05_reglas_de_negocio.md)
4. Entender la arquitectura → [02](02_descripcion_general.md), [08](08_arquitectura_propuesta.md)
5. Implementar → [07](07_flujos_principales.md), [06](06_funcionalidades.md)
6. Antes de codificar → [10](10_preguntas_abiertas.md)

## Resumen Ejecutivo

Sistema de turnos odontológicos para consultorios y clínicas chicas AR: reserva online sin login, regla de 24 hs, anti-solape por profesional/sillón, recordatorios por WhatsApp y sincronía con Google Calendar. Stack sin definir, diseño mobile-first. Núcleo MVP: reserva, cancelación/reprogramación y recordatorios.
