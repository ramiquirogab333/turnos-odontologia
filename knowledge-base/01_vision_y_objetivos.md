# Visión y Objetivos

Fuente: ingest de `docs/discovery/informe-discovery.md`, `docs/discovery/Validación Discovery.md` y sección `discovery` de `.active-orchestrator-state.json` (2026-09-29). `docs/discovery/informe-discovery.pdf` excluido (ver `10_preguntas_abiertas.md`).

## Propósito del sistema

Sistema de gestión de turnos odontológicos para consultorios y clínicas chicas de Argentina.

Coordinar turnos hoy es un caos: WhatsApp, papel, teléfono y Google Calendar dispersos generan dobles reservas, ausentismo alto y tiempo perdido confirmando manualmente cada turno. El sistema unifica reserva online, agenda por profesional, recordatorios por WhatsApp y panel de gestión en un solo lugar.

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|-------|--------------------|----------------------|
| Paciente | Reservar, cancelar y reprogramar turnos sin llamar ni escribir por WhatsApp | Recibir recordatorios para no olvidar el turno; ver horarios libres en el celular |
| Odontólogo/a | Ver su agenda del día/semana por profesional | Saber a quién atiende y cuándo; evitar superposiciones |
| Recepción/admin | Gestionar agenda, pacientes, ausentismo y liquidaciones desde un panel | Medir ocupación por sillón, recupero de ausentes y cierres de caja |

## Alcance v1

- Reserva online de turnos con horarios libres visibles, sin registro obligatorio (nombre + teléfono).
- Cancelación y reprogramación por el paciente respetando anticipación mínima de 24 hs.
- Recordatorios y confirmación por WhatsApp (con botones de confirmación).
- Agenda multi-profesional por día/semana con control anti-solape (profesional y sillón).
- Gestión de disponibilidad y duraciones por tratamiento configurables por el admin.
- Panel admin: pacientes, ocupación, ausentismo, recupero, caja.
- Ficha de paciente + odontograma FDI básico + presupuestos con cobertura de obra social.
- Nomenclador de obras sociales AR precargado.
- Cobro por Mercado Pago + transferencia.
- Sincronía bidireccional con Google Calendar.
- Roles y auditoría básica + exportación masiva de datos.

Núcleo priorizado por el usuario (MVP primero): reserva (1), cancelación/reprogramación (2), recordatorios WhatsApp (3); luego agenda por profesional y panel admin.

## Fuera de alcance

- Facturación electrónica ARCA nativa completa (v1 solo nomenclador precargado + Mercado Pago).
- Periodontograma avanzado, imágenes/RX con IA.
- Portal del paciente con historia clínica completa y cuotas.
- Campañas de recupero y controles periódicos automatizados.
- API pública y webhooks.
- App móvil nativa dedicada (v1 es web mobile-first).
- Multi-sucursal, laboratorio e inventario.
- Firma digital y consentimientos informados.
- IA de secretaría 24/7 (chatbot con IA).

## Métricas de éxito

- Reducción del ausentismo (referencia de mercado: DentalSoft AR declara −82%; sin auditoría — ver `10_preguntas_abiertas.md`).
- Cero dobles reservas (turnos superpuestos por profesional/sillón).
- Tiempo ahorrado en confirmación manual de turnos.
- Ocupación por sillón y tasa de recupero de ausentes visibles en el panel.
