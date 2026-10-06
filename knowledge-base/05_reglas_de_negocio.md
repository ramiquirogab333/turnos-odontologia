# Reglas de Negocio

Cada regla tiene código único `RN-{DOMINIO}-{NN}` para trazabilidad. Fuente: discovery §7 más reglas derivadas de casos de uso e integraciones.

## Dominio: Turnos (RN-TU)

- **RN-TU-01**: No se puede cancelar un turno con menos de 24 horas de anticipación.
- **RN-TU-02**: No se puede reprogramar un turno con menos de 24 horas de anticipación (aplica la misma ventana que cancelación; confirmar si la ventana es idéntica — ver `10_preguntas_abiertas.md`).
- **RN-TU-03**: Ningún PROFESIONAL ni ningún SILLÓN/BOX puede tener dos turnos superpuestos desde el día 1 (multi-odontólogo/multi-sillón día 1, Resolución 2026-09-30 nº1 — cierra SU-03). Garantía en DB con dos `EXCLUDE USING gist` parciales por estado (estrategia A del DDL de C-01: `WHERE estado IN ('reservado','confirmado')`); el pre-chequeo por rango en aplicación es solo fast-fail, la DB decide. Estado `en_espera` (C-06) NO bloquea y queda fuera de los EXCLUDE (R8).
- **RN-TU-04**: La duración del turno la determina el tratamiento (fin = inicio + duración configurada), no un valor fijo global.
- **RN-TU-05**: La tabla tratamiento→duración es configurable por el admin; no va fija en código.
- **RN-TU-06**: La reserva pública no exige registro ni login: alcanza con nombre + teléfono por turno.
- **RN-TU-07**: Solo se puede reservar sobre horarios libres calculados desde disponibilidad vigente del profesional (más sillón, si aplica).

## Dominio: WhatsApp (RN-WA)

- **RN-WA-01**: Todo turno genera recordatorio(s) por WhatsApp.
- **RN-WA-02**: La confirmación por botones de WhatsApp actualiza el estado del turno (confirmado).
- **RN-WA-03**: WhatsApp MANUAL en v1 (Resolución 2026-09-30 nº2): links `wa.me/` con mensajes preformateados, sin API paga ni costo por mensaje; se mantiene la abstracción de proveedor para migrar a API después. Solo turnos que bloquean agenda reciben recordatorio (`en_espera` NO).

## Dominio: Calendario (RN-GC)

- **RN-GC-01**: La agenda sincroniza bidireccionalmente con Google Calendar del profesional.
- **RN-GC-02**: Ante conflicto entre el sistema y Google Calendar, la resolución es manual (criterio a definir — ver `10_preguntas_abiertas.md`).

## Dominio: Pagos y cobertura (RN-PG)

- **RN-PG-01**: Medios de v1: Mercado Pago + transferencia. Sin otros medios en v1.
- **RN-PG-02**: Los presupuestos contemplan cobertura de obra social según nomenclador AR precargado.
- **RN-PG-03**: Sin facturación electrónica ARCA nativa en v1.

## Dominio: Seña (RN-SN — rige desde C-06; modelado documental coherente con el GAP del header de CHANGES.md)

- **RN-SN-01** (R8): el turno nace en `en_espera` (seña pendiente) y NO bloquea agenda, no genera recordatorio ni evento de calendario; solo la seña acreditada (`reservado`) bloquea el slot con anti-solape RN-TU-03.
- **RN-SN-02** (R9): el ausente NO reembolsa la seña — queda registrada como recupero/no_reembolsada en caja (`PagoSena.estado = no_reembolsado`).
- **RN-SN-03**: seña fija configurable (ej. 30% del valor de la consulta = precio base del tratamiento); `PagoSena.monto` es `Numeric` y `ref_unica` (referencia externa única) da idempotencia al webhook.

## Dominio: Excepciones globales

- **RN-GL-01**: Toda acción de gestión interna (panel) queda registrada en auditoría básica (quién, qué, cuándo).
- **RN-GL-02**: Los datos deben poder exportarse masivamente.
- **RN-GL-03**: El sistema debe funcionar bien en celular (mobile-first) en todos los flujos del paciente.
