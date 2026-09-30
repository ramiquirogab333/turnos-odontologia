# Decisiones y Supuestos

## Decisiones documentadas

### DD-01 — Reserva sin registro obligatorio
**Decisión**: reservar con nombre + teléfono, sin login de paciente.
**Contexto**: la mayoría reserva desde el teléfono; el login frena la conversión.
**Alternativas consideradas**: cuenta obligatoria; login social.
**Justificación**: fricción mínima, coherente con el uso actual por WhatsApp.
**Trade-offs aceptados**: gestión del turno por enlace/código en vez de cuenta; unicidad del paciente atada al teléfono.

### DD-02 — Ventana de cancelación de 24 hs
**Decisión**: no cancelar/reprogramar con menos de 24 hs de anticipación.
**Contexto**: regla de negocio explícita del consultorio (discovery §7).
**Alternativas consideradas**: ventana mayor/menor o por tratamiento.
**Justificación**: protege la ocupación de la agenda.
**Trade-offs aceptados**: rigidez ante urgencias; requiere mensaje claro de rechazo.

### DD-03 — Duraciones configurables por tratamiento
**Decisión**: tabla tratamiento→duración editable por admin, no fija en código.
**Contexto**: cada tratamiento dura distinto y puede cambiar.
**Alternativas consideradas**: duración fija global; duración fija por especialidad.
**Justificación**: flexibilidad sin despliegues.
**Trade-offs aceptados**: el admin debe mantener la tabla actualizada.

### DD-04 — Mobile-first
**Decisión**: el diseño prioriza el celular.
**Contexto**: sin restricciones de stack/plataforma; la mayoría reserva desde el teléfono.
**Alternativas consideradas**: desktop-first; app nativa desde v1.
**Justificación**: cubre al paciente con web responsive sin costo de app nativa.
**Trade-offs aceptados**: app dedicada queda para después de v1.

### DD-05 — Google Calendar como calendario espejo
**Decisión**: sincronía bidireccional con Google Calendar.
**Contexto**: hoy es el sistema principal en uso.
**Alternativas consideradas**: reemplazar GCal por agenda propia única.
**Justificación**: adopción sin fricción para el profesional.
**Trade-offs aceptados**: complejidad de conflictos de sincronía (RN-GC-02 pendiente).

### DD-06 — Alcance clínico-administrativo mínimo en v1
**Decisión**: odontograma FDI básico + presupuestos con OS + nomenclador precargado; MP + transferencia; sin ARCA nativa.
**Contexto**: discovery §5 (necesarias) vs. §6 (opcionales).
**Alternativas consideradas**: v1 solo turnos; v1 con facturación ARCA completa.
**Justificación**: cubre operación diaria sin el costo de facturación electrónica nativa.
**Trade-offs aceptados**: facturación completa queda fuera de v1.

## Supuestos inferidos

### SU-01 — El PDF equivale a los .md
**Supuesto**: `docs/discovery/discovery.pdf` contiene lo mismo que `docs/discovery/discovery.md` ya ingerido.
**Origen**: mismo nombre y tamaño similar; el PDF no pudo parsearse (ver `10_preguntas_abiertas.md`).
**Riesgo si es falso**: pérdida de contenido exclusivo del PDF.
**Cómo validar**: revisión manual del PDF contra esta KB.

### SU-02 — Un consultorio/clínica chica, una sede
**Supuesto**: despliegue para una sola sede; multi-sucursal fuera de v1.
**Origen**: "consultorio/clínica chica AR"; multi-sucursal listado como opcional.
**Riesgo si es falso**: modelo de datos sin sede desde el inicio cuesta migrar.
**Cómo validar**: confirmar con el decisor (ver `10_preguntas_abiertas.md`).

### SU-03 — Anti-solape también por sillón
**Supuesto**: el control anti-solape cubre profesional y sillón (ocupación por sillón aparece en casos de uso).
**Origen**: state.discovery (ocupación por sillón) + discovery §5 (agenda multi-profesional + sillones con anti-solape).
**Riesgo si es falso**: sobredimensionar la lógica de disponibilidad.
**Cómo validar**: confirmar si v1 controla sillones o solo profesionales.

### SU-04 — Adopción de reserva online por el paciente
**Supuesto**: los pacientes usarán la reserva online en vez de WhatsApp por costumbre.
**Origen**: riesgo declarado en discovery §10 (supuesto sin probar).
**Riesgo si es falso**: baja adopción; el canal WhatsApp sigue siendo la vía real.
**Cómo validar**: piloto con pacientes reales midiendo % de reservas online vs. WhatsApp.
