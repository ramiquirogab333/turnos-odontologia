# Reglas de Negocio

Cada regla tiene código único `RN-{DOMINIO}-{NN}` para trazabilidad. Fuente: discovery §7 más reglas derivadas de casos de uso e integraciones.

## Dominio: Turnos (RN-TU)

- **RN-TU-01**: No se puede cancelar un turno con menos de 24 horas de anticipación.
- **RN-TU-02**: No se puede reprogramar un turno con menos de 24 horas de anticipación (aplica la misma ventana que cancelación; confirmar si la ventana es idéntica — ver `10_preguntas_abiertas.md`).
- **RN-TU-03**: Un profesional no puede tener dos turnos superpuestos (sin superposición).
- **RN-TU-04**: La duración del turno la determina el tratamiento (fin = inicio + duración configurada), no un valor fijo global.
- **RN-TU-05**: La tabla tratamiento→duración es configurable por el admin; no va fija en código.
- **RN-TU-06**: La reserva pública no exige registro ni login: alcanza con nombre + teléfono por turno.
- **RN-TU-07**: Solo se puede reservar sobre horarios libres calculados desde disponibilidad vigente del profesional (más sillón, si aplica).

## Dominio: WhatsApp (RN-WA)

- **RN-WA-01**: Todo turno genera recordatorio(s) por WhatsApp.
- **RN-WA-02**: La confirmación por botones de WhatsApp actualiza el estado del turno (confirmado).
- **RN-WA-03**: Modalidad pendiente: manual vs. automática vía API con costo por mensaje (ver `10_preguntas_abiertas.md`).

## Dominio: Calendario (RN-GC)

- **RN-GC-01**: La agenda sincroniza bidireccionalmente con Google Calendar del profesional.
- **RN-GC-02**: Ante conflicto entre el sistema y Google Calendar, la resolución es manual (criterio a definir — ver `10_preguntas_abiertas.md`).

## Dominio: Pagos y cobertura (RN-PG)

- **RN-PG-01**: Medios de v1: Mercado Pago + transferencia. Sin otros medios en v1.
- **RN-PG-02**: Los presupuestos contemplan cobertura de obra social según nomenclador AR precargado.
- **RN-PG-03**: Sin facturación electrónica ARCA nativa en v1.

## Dominio: Excepciones globales

- **RN-GL-01**: Toda acción de gestión interna (panel) queda registrada en auditoría básica (quién, qué, cuándo).
- **RN-GL-02**: Los datos deben poder exportarse masivamente.
- **RN-GL-03**: El sistema debe funcionar bien en celular (mobile-first) en todos los flujos del paciente.
