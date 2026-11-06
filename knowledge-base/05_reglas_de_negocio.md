# Reglas de Negocio

Cada regla tiene código único `RN-{DOMINIO}-{NN}` para trazabilidad. Fuente: discovery §7 más reglas derivadas de casos de uso e integraciones.

## Dominio: Turnos (RN-TU)

- **RN-TU-01**: No se puede cancelar un turno con menos de 24 horas de anticipación.
- **RN-TU-02** (confirmada, cierra IN-02): No se puede reprogramar un turno con menos de 24 horas de anticipación. Es la misma ventana que RN-TU-01 (decisión del Product Owner 2026-11-06, C-07).
- **RN-TU-03**: Ningún PROFESIONAL ni ningún SILLÓN/BOX puede tener dos turnos superpuestos desde el día 1 (multi-odontólogo/multi-sillón día 1, Resolución 2026-09-30 nº1 — cierra SU-03). Garantía en DB con dos `EXCLUDE USING gist` parciales por estado (estrategia A del DDL de C-01: `WHERE estado IN ('reservado','confirmado')`); el pre-chequeo por rango en aplicación es solo fast-fail, la DB decide. Estado `en_espera` (C-06) NO bloquea y queda fuera de los EXCLUDE (R8).
- **RN-TU-04**: La duración del turno la determina el tratamiento (fin = inicio + duración configurada), no un valor fijo global.
- **RN-TU-05**: La tabla tratamiento→duración es configurable por el admin; no va fija en código.
- **RN-TU-06**: La reserva pública no exige registro ni login: alcanza con nombre + teléfono por turno.
- **RN-TU-07**: Solo se puede reservar sobre horarios libres calculados desde disponibilidad vigente del profesional (más sillón, si aplica).
- **RN-TU-08** (decisión 2026-11-06, C-07, O1/O2): el paciente gestiona su turno solo con el código de gestión, enviado en la cabecera `X-Codigo-Gestion` (nunca en la ruta ni en la query). Al reprogramar solo cambia día y hora: mismo tratamiento y misma profesional.
- **RN-TU-09** (decisión 2026-11-06, C-07, O3): un turno `en_espera` no se reprograma (409 `sena_pendiente`); se cancela y se reserva otro horario. Cancelar un `en_espera` se acepta en cualquier momento, sin ventana de 24 h (O10).
- **RN-TU-10** (decisión 2026-11-06, C-07, O4/O5): no hay límite de reprogramaciones por turno (cada cambio queda auditado); un `confirmado` que se reprograma vuelve a `reservado`.
- **RN-TU-11** (decisión 2026-11-06, C-07, O6/O7): la ventana se compara en instantes absolutos; exactamente 24 h se acepta. Se mide contra el inicio actual del turno: el nuevo horario puede estar a menos de 24 h si está libre.

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
- **RN-SN-04** (decisión 2026-11-06): si un turno `reservado`/`confirmado` con seña acreditada se cancela con 24 h o más de anticipación, la seña SE DEVUELVE: `PagoSena.estado = a_reembolsar`, con devolución manual. Con menos de 24 h no se puede cancelar (RN-TU-01). El ausente sigue sin reembolso (RN-SN-02).
- **RN-SN-05** (decisión 2026-11-06): un pago aprobado cuando el turno ya no está `en_espera` (venció o se canceló), o cuando el horario lo ganó otro turno acreditado antes, queda `a_reembolsar` (devolución manual). El turno no revive y no bloquea agenda.
- **RN-SN-06** (decisión 2026-11-06): un tratamiento con precio base 0 está exento de seña; el turno público nace directamente `reservado`, con anti-solape RN-TU-03.
- **RN-SN-07** (decisión 2026-11-06): la pre-reserva `en_espera` vence a los 30 min si el medio es Mercado Pago y a las 24 h si es transferencia, nunca después del inicio del turno; los dos plazos los edita el admin. Al vencer, el turno pasa a `cancelado` y el pago pendiente a `vencido`.
- **RN-SN-10** (decisión 2026-11-06): cada pago aprobado de la pasarela se registra por su id (único). La re-entrega del mismo id no cambia nada; un pago aprobado con otro id sobre una seña ya acreditada o resuelta queda `a_reembolsar` (devolución manual) y los pagos `en_revision` que no se aceptan quedan `a_reembolsar` cuando se acredita otro o el turno ya no está vigente.
- **RN-SN-09** (decisión 2026-11-06): un pago de Mercado Pago solo se acredita si la pasarela informa el monto y la moneda, el monto coincide EXACTAMENTE con el de la seña (comparación decimal) y la moneda es ARS. Si el monto o la moneda faltan, son ilegibles o no coinciden (falla cerrado), el pago pasa a `en_revision`, el turno sigue `en_espera` con su vencimiento normal y recepción/admin lo resuelve: lo acredita a mano o queda `a_reembolsar` (si el turno ya venció o se perdió el horario).
- **RN-SN-08** (decisión 2026-11-06): la transferencia se acredita a mano (recepción/admin). El paciente ve el alias, el CBU y un código de referencia corto del turno para poner en el concepto de la transferencia.

## Dominio: Excepciones globales

- **RN-GL-01**: Toda acción de gestión interna (panel) queda registrada en auditoría básica (quién, qué, cuándo).
- **RN-GL-02**: Los datos deben poder exportarse masivamente.
- **RN-GL-03**: El sistema debe funcionar bien en celular (mobile-first) en todos los flujos del paciente.
