# Sistema de Gestión y Reserva de Turnos Odontológicos

> **Proyecto Académico**  
> **Cátedra:** Metodología de Sistemas — 2° Año, Semestre 1  
> **Autor:** Ramiro Quiroga ([@ramiquirogab333](https://github.com/ramiquirogab333))

---

## 1. Visión y Problema que Resuelve

En consultorios y clínicas odontológicas pequeñas y medianas, la coordinación de turnos suele realizarse de forma fragmentada y manual: mensajes dispersos de WhatsApp, llamadas telefónicas, planillas en papel y calendarios no sincronizados (como Google Calendar).

Esta falta de centralización genera:
- **Ausentismo elevado** por olvido de turnos o falta de recordatorios oportunos.
- **Dobles reservas y superposición** de horarios entre profesionales o por disponibilidad de sillones.
- **Pérdida de tiempo operativo** en recepción confirmando turnos uno por uno.
- **Dificultad para auditar y gestionar** la caja diaria, historias clínicas y coberturas de obras sociales.

El presente proyecto tiene como propósito desarrollar una plataforma integral, moderna y orientada a dispositivos móviles (mobile-first) que automatice la reserva, confirmación y gestión de turnos odontológicos, adaptada a las particularidades operativas de Argentina.

---

## 2. Usuarios y Roles del Sistema

| Rol | Responsabilidad y Casos de Uso Clave |
|---|---|
| **Paciente** | - Visualizar disponibilidad horaria en tiempo real.<br>- Reservar turnos online sin registro obligatorio previo (nombre y teléfono).<br>- Recibir recordatorios y confirmaciones automáticas por WhatsApp.<br>- Cancelar o reprogramar turnos con anticipación mínima de 24 horas. |
| **Odontólogo/a** | - Consultar agenda diaria y semanal por profesional.<br>- Registrar evolución de tratamientos en ficha del paciente.<br>- Evitar solapamiento de consultas y sobreturnos descontrolados. |
| **Recepción / Administración** | - Gestionar disponibilidad de agendas y asignación de sillones de atención.<br>- Administrar pacientes, inasistencias y lista de espera / recupero.<br>- Registrar cobros (Mercado Pago, efectivo, transferencia) y cierres de caja.<br>- Configurar nomenclador y aranceles según obras sociales o particulares. |

---

## 3. Alcance del MVP y Reglas de Negocio

### Funcionalidades Núcleo (MVP)
1. **Reserva online para pacientes:** Flujo ágil en pocos pasos, optimizado para celulares, sin fricción de contraseñas obligatorias.
2. **Políticas de cancelación y reprogramación:** Regla de negocio estricta de **24 horas de anticipación mínima** para liberar el turno y habilitarlo a otros pacientes.
3. **Notificaciones y recordatorios por WhatsApp:** Alertas automáticas previas a la cita con botones de confirmación rápida.
4. **Agenda multi-profesional y sillones con anti-solape:** Control de concurrencia que impide reservar si el profesional o el sillón asignado ya están ocupados.
5. **Panel administrativo:** Monitoreo de ocupación, ausentismo, caja diaria y gestión básica de historias clínicas y odontograma.

### Reglas de Negocio Fundamentales
- **Anticipación de cancelación:** Ningún turno puede ser cancelado o modificado por el paciente con menos de 24 horas de anticipación.
- **Anti-solape estricto:** Un profesional no puede tener dos turnos en el mismo horario, ni dos profesionales pueden compartir el mismo sillón físico en forma simultánea.
- **Duración parametrizable:** La duración de cada turno se calcula según el tipo de tratamiento o consulta programada.

---

## 4. Relevamiento y Estudio de Mercado (Discovery)

Como parte de la fase inicial de análisis, se realizó un relevamiento exhaustivo de más de 18 plataformas nacionales e internacionales del sector odontológico y de salud:

- **Nacionales (Argentina):** DentalSoft Argentina, Bilog, DentalSaaS/DelRioTech, Dentiqa.
- **Latinoamérica:** Dentalink (Chile), DentiDesk (Chile), Doctocliq (Perú), AgendaPro (Chile), Doctoralia (AR/ES), SaludTools (Colombia), Simples Dental (Brasil).
- **Internacionales de referencia:** Open Dental (USA), Curve Dental (USA), tab32 (USA), CareStack / Dentrix Ascend (USA/UK).

### Oportunidad y Diferenciación Local
La mayoría de las herramientas internacionales o genéricas fallan en cubrir la realidad del consultorio en Argentina:
- Integración directa con **Mercado Pago** y transferencias bancarias.
- Nomenclador odontológico argentino y liquidación de **Obras Sociales y Prepagas**.
- Costo y canal de comunicación prioritario a través de **WhatsApp** automatizado.
- Restricción física de **sillones odontológicos** compartidos entre varios especialistas.

El informe completo de relevamiento y la matriz comparativa detallada pueden consultarse en:
- Documento Markdown: [docs/discovery/discovery.md](docs/discovery/discovery.md)
- Documento PDF: [docs/discovery/discovery.pdf](docs/discovery/discovery.pdf)

---

## 5. Estructura del Repositorio

```text
turnos-odontologia/
├── .active-orchestrator-state.json # Estado estructurado del proceso de relevamiento
├── .gitignore                      # Configuración de exclusiones de Git
├── .opencode/                      # Comandos y habilidades para flujo guiado por agentes IA
│   ├── commands/                   # Comandos /opsx-* para el ciclo spec-driven
│   └── skills/                     # Habilidades integradas de OpenSpec
├── docs/
│   └── discovery/
│       ├── discovery.md            # Informe detallado de relevamiento de requerimientos y competidores
│       └── discovery.pdf           # Versión compilada en PDF del estudio de mercado
├── openspec/
│   ├── config.yaml                 # Configuración del workflow de especificaciones
│   ├── changes/                    # Cambios propuestos y archivados
│   └── specs/                      # Especificaciones vigentes del sistema
└── README.md                       # Documentación general del repositorio
```

---

## 6. Metodología de Trabajo

El proyecto utiliza un enfoque **Spec-Driven Development** gobernado por **OpenSpec**:
1. **Discovery:** Identificación del problema, usuarios, reglas de negocio y benchmarking competitivo.
2. **Proposals y Specs:** Redacción formal de propuestas (`proposal.md`), especificaciones del comportamiento del sistema (`spec.md`), arquitectura técnica (`design.md`) y desglose de tareas (`tasks.md`).
3. **Apply e Implementación:** Implementación guiada por especificaciones validadas y pruebas de aceptación.
4. **Archive y Sync:** Sincronización del estado de las especificaciones y archivo de cambios completados.

---

## 7. Estado del Proyecto y Próximos Pasos

- [x] **Fase 1 — Discovery y Relevamiento:** Requerimientos, casos de uso, estudio de competidores y definición de reglas iniciales.
- [ ] **Fase 2 — Arquitectura y Stack Tecnológico:** Selección de framework (ej. Next.js / TypeScript, Tailwind CSS), base de datos (PostgreSQL/Supabase o SQLite), y diseño de modelos de datos.
- [ ] **Fase 3 — Diseño UX/UI:** Mockups del flujo de reserva del paciente y panel de administración.
- [ ] **Fase 4 — Implementación del MVP:** Desarrollo de la agenda, reserva sin registro y módulo de cancelación/reprogramación con regla 24 hs.
- [ ] **Fase 5 — Integraciones:** Notificaciones por WhatsApp y pasarela de pagos.
