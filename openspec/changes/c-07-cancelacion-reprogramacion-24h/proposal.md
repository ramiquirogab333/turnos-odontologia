# Proposal: c-07-cancelacion-reprogramacion-24h

## Why
Hoy la o el paciente reserva y paga la seña, pero no tiene forma de cancelar ni de cambiar el horario sin llamar a la clínica: el código de gestión que recibe al reservar (C-05) solo sirve para pagar la seña (C-06). US-002 y US-003 piden que pueda hacerlo solo, respetando la ventana de 24 h (RN-TU-01, RN-TU-02, DD-02), y C-06 ya dejó la regla de la seña en la máquina de estados (cancelar con 24 h o más deja la seña `a_reembolsar`, RN-SN-04) esperando que C-07 la exponga. C-08, C-09 y C-10 dependen de C-07 porque consumen los estados finales y la regla de 24 h.

## What Changes
- **Consultar el turno con el código de gestión:** `GET /api/public/gestion` (código en la cabecera `X-Codigo-Gestion`, sin login) devuelve el turno (día, hora, tratamiento, profesional, estado), el estado de la seña y si todavía se puede cancelar o reprogramar, con el límite (inicio − 24 h) en hora de la clínica.
- **Cancelar:** `POST /api/public/gestion/cancelar`.
  - `reservado`/`confirmado` con 24 h o más de anticipación: el turno pasa a `cancelado`, el horario se libera y la seña acreditada pasa a `a_reembolsar` (devolución manual, RN-SN-04).
  - Con menos de 24 h: 409 `fuera_de_plazo` con el motivo y el límite; nada cambia (RN-TU-01).
  - `en_espera`: se cancela en cualquier momento antes del inicio, el pago pendiente pasa a `vencido` y no hay movimiento de caja (R8); un pago `en_revision` pasa a `a_reembolsar` (RN-SN-10).
- **Reprogramar:** `POST /api/public/gestion/reprogramar` con el nuevo inicio. Solo con 24 h o más respecto del inicio actual (RN-TU-02), solo a un horario libre dentro de la disponibilidad vigente (RN-TU-07), mismo tratamiento y mismo profesional, con el anti-solape de la base (RN-TU-03, R5). Horario ocupado → 409 con alternativas. El turno se mueve en el lugar: conserva su id, su código de gestión y la seña acreditada.
- **Punto de enganche para Google Calendar y recordatorios (Flujo 2, paso 4):** C-07 publica los eventos `turno_cancelado` y `turno_reprogramado` por un puerto (`NotificadorTurnos`) con una implementación nula y deja la auditoría con `origen` como registro durable. **C-07 no implementa Google Calendar (C-10) ni los recordatorios (C-09)**: ellos van a implementar el puerto.
- **Frontend `frontend-paciente/`:** pantalla "Gestionar mi turno" a 360px (R3), a la que se llega con el enlace de gestión (`/gestionar#<código>`, el código nunca viaja en la URL al servidor) o pegando el código; muestra el turno, el aviso de la ventana de 24 h, "Cancelar turno" con confirmación y la política de la seña, y "Cambiar horario" reutilizando el selector de horarios de la reserva. La confirmación de la reserva suma el enlace "Gestionar mi turno".
- **E2E Playwright (R7):** cancelación y reprogramación a cada lado del borde de 24 h, reprogramación a un horario ocupado con alternativas, y seña `a_reembolsar` (reservado) contra `vencido` sin caja (`en_espera`).
- **Decisiones a confirmar:** la forma de enviar el código, qué se puede cambiar al reprogramar, el borde exacto de 24 h, el estado de un `confirmado` reprogramado y otras quedan en `design.md` (O1–O10) con un default recomendado; los specs usan ese default.
- **Sin migración** con las decisiones recomendadas (los estados, el código de gestión y los EXCLUDE ya existen). Si se aprueba un límite de reprogramaciones (decisión abierta O4) se agrega la `007`.

## Capabilities

### New Capabilities
- `turnos/gestion-paciente`: gestión del turno por el propio paciente con el código de gestión: consulta, cancelación y reprogramación con la ventana de 24 h, alternativas ante un horario ocupado, eventos para calendario y recordatorios, y la pantalla de gestión a 360px.

### Modified Capabilities
- `pagos/sena-turno`: el requisito "La cancelación con 24 horas o más devuelve la seña" pasa de "C-07 la expone" a estar expuesto por el endpoint público; se agrega que cancelar una pre-reserva con un pago `en_revision` lo deja `a_reembolsar`, y que la seña acreditada acompaña al turno reprogramado.

## Impact
- **Backend:** módulo nuevo `app/gestion/` (esquemas, servicio, router, puerto de eventos); `app/pagos/service.py` (`_cambiar_estado_una_vez` también resuelve los pagos `en_revision` al cancelar un `en_espera`); `app/public/service.py` (`_cargar_bloqueos` acepta excluir el propio turno al reprogramar); `app/main.py` (router).
- **API:** tres endpoints públicos nuevos. No cambia ningún contrato existente.
- **Base de datos:** sin cambios con los defaults recomendados.
- **Frontend:** componente `GestionTurno` y cliente de API; enlace desde `Confirmacion`.
- **Docs/KB:** confirmar RN-TU-02 (IN-02: la ventana de reprogramación es la misma que la de cancelación) y registrar las decisiones aprobadas de `design.md`.
- **Fuera de alcance:** Google Calendar (C-10), recordatorios de WhatsApp y el link de cancelación desde el recordatorio (C-09), cancelación desde el panel (C-08), UI de caja para `a_reembolsar` (C-12), reembolso automático, cambio de tratamiento o de profesional al reprogramar.
