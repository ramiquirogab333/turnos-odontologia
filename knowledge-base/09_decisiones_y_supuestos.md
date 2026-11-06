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

### DD-07 — Política de la seña (C-06, decisión del Product Owner 2026-11-06)
**Decisión**: se aprueban los defaults de C-06 con un cambio en la cancelación:
- Vencimiento de `en_espera`: 30 min con Mercado Pago y 24 h con transferencia, nunca después del inicio del turno; editable por el admin (RN-SN-07).
- Cancelación con 24 h o más: la seña se devuelve (`a_reembolsar`, devolución manual). El ausente no se reembolsa (RN-SN-04, RN-SN-02).
- Pago aprobado tardío u horario ganado por otro: `a_reembolsar`, y el turno no revive (RN-SN-05).
- Precio base 0: exento de seña, nace `reservado` (RN-SN-06).
- Seña inicial: 30% del precio base (RN-SN-03).
- Transferencia: acreditación manual de recepción/admin por la API (la UI llega en C-12), con alias, CBU y un código de referencia del turno en el concepto (RN-SN-08).
- Se reescriben los tests y E2E de C-05 dentro de C-06.
- El barrido de vencimiento es una tarea asyncio del lifespan, cada 60 s y sin Redis; C-09 lo consolida.

**Contexto**: el diseño de C-06 (`openspec/changes/c-06-sena-pagos-turno/design.md`, §Decisiones aprobadas, P1 a P8) dejó estas decisiones para el usuario por la governance CRÍTICA de pagos.
**Alternativas consideradas**: seña no reembolsable también al cancelar (era el default original de `CHANGES.md`); revivir el turno ante un pago tardío; rechazar la reserva de tratamientos sin precio; Redis + worker para el vencimiento.
**Justificación**: devolver la seña cuando se avisa con tiempo es más justo para el paciente y deja el castigo solo para el ausentismo. La devolución manual evita automatizar reembolsos en v1.
**Trade-offs aceptados**: los reembolsos son manuales (`a_reembolsar` visible en caja desde C-12); `a_reembolsar` agrega un estado que la KB original no tenía.

### DD-08 — Gestión del turno por el paciente (C-07, decisión del Product Owner 2026-11-06)
**Decisión**: se aprueban los defaults O1 a O10 de `openspec/changes/c-07-cancelacion-reprogramacion-24h/design.md`.
- O1: el código de gestión viaja en la cabecera `X-Codigo-Gestion` sobre `/api/public/gestion/*` (no en la ruta como decía `CHANGES.md`), para que no quede en logs ni en el `Referer`. El enlace del paciente es `/gestionar#<código>` (el fragmento no llega al servidor).
- O8: la entrega de eventos a Google Calendar y recordatorios usa el puerto `NotificadorTurnos` post-commit más la auditoría transaccional como fuente reconciliable; sin tabla outbox ni migración (C-09 puede sumarla junto con Redis).
- Reglas de negocio derivadas (O2 a O7, O10): RN-TU-08 a RN-TU-11 en `05_reglas_de_negocio.md`. IN-02 queda resuelta.
- O9: el borde exacto de 24 h se prueba en integración con reloj inyectado; el E2E usa márgenes de 5 min (sin reloj manipulable por entorno).

**Contexto**: cancelar y reprogramar por el paciente necesitaba definir credencial, alcance del cambio y semántica de la ventana.
**Alternativas consideradas**: código en la ruta; reprogramar `en_espera`; límite de reprogramaciones; outbox; reloj falso del backend para E2E.
**Justificación**: mínima superficie de ataque y de infraestructura; la base sigue siendo la garantía del anti-solape (R5).
**Trade-offs aceptados**: quien tenga el código puede gestionar el turno (rate limiting llega con Redis en C-09); un evento puede perderse entre el commit y la publicación (se reconcilia desde la auditoría).

## Supuestos inferidos

### SU-01 — El PDF equivale a los .md
**Supuesto**: `docs/discovery/informe-discovery.pdf` contiene lo mismo que `docs/discovery/informe-discovery.md` ya ingerido.
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
