# Proposal: c-08-agenda-profesional-panel

## Why
El backend ya tiene autenticación (C-03), reserva (C-05), seña (C-06) y cancelación (C-07), pero nadie de la clínica puede ver la agenda: no existe ninguna pantalla interna ni un endpoint que la devuelva. US-005 y el Flujo 4 piden que cada odontóloga u odontólogo vea su día y su semana, y que recepción opere la agenda: cargar turnos que llegan por teléfono y registrar quién vino y quién no. C-06 dejó lista la regla del ausente (la seña no se devuelve, R9) esperando un punto de entrada, y C-12 depende de la base de panel que crea este change.

## What Changes
- **Agenda:** `GET /api/panel/agenda` por día o semana, con filtro por profesional y por sillón. La odontóloga u odontólogo ve solo su agenda; recepción y admin ven todas. Las pre-reservas `en_espera` se devuelven marcadas como no bloqueantes y nunca cuentan como ocupación (R8, RN-TU-03).
- **Alta manual:** `POST /api/panel/turnos` para recepción y admin, con la misma garantía anti-solape de la base (R5, RN-TU-03), `fin` derivado de la duración del tratamiento (RN-TU-04), origen manual y sin seña (excepción aprobada a R8, O7).
- **Marcar atendido y ausente:** `atendido` desde el inicio del día local del turno, y sigue ocupando el horario hasta su `fin` (O19: pasa a ser estado que ocupa agenda, en la base y en todos los cálculos de libres); `ausente` desde el inicio más una tolerancia configurable de 10 minutos, con la seña en `no_reembolsado` (R9). Regla nueva RN-TU-12 (O14).
- **Cancelar desde el panel:** `POST /api/panel/turnos/{id}/cancelar`, con la ventana de 24 h de C-07 y evento `turno_cancelado` (O12).
- **`frontend-panel/` nuevo** (React + TypeScript + Vite estricto, R1): pantalla de ingreso, agenda día y semana, filtros, alta manual y acciones sobre el turno. Mobile-first a 360 px, con una grilla semanal en escritorio.
- **Cambio de autenticación aprobado (O2, **BREAKING** para clientes de `/api/auth`):** el refresh pasa a viajar solo en la cookie HttpOnly. `POST /api/auth/refresh` deja de aceptarlo por body y exige una cabecera anti-CSRF; login y refresh dejan de devolverlo en el JSON. El access sigue en memoria y la sesión se restaura sola al recargar o abrir otra pestaña. El logout revoca el refresh hasta su vencimiento real.
- **`POST /api/turnos` exige recepción o admin (O3, **BREAKING**).**
- **Comando para crear usuarios del panel (O4).**
- **CI y E2E Playwright (R7):** job de frontend y job E2E para el panel, a 360 px y en escritorio, incluida la carrera 201/409 diferida desde C-01.
- **Migración `007_turno_origen_ocupacion`:** agrega `Turno.origen` (O10), que la KB define pero no existe, y suma `atendido` al predicado de los dos EXCLUDE (O19).
- Las decisiones O1–O18 quedaron resueltas por el usuario el 2026-11-09 (`design.md`).

## Capabilities

### New Capabilities
- `turnos/agenda-panel`: consulta de la agenda por día o semana, aislamiento por rol, distinción de pre-reservas, filtros y pantalla de agenda.
- `turnos/gestion-panel`: operación interna del turno: alta manual, ausente, atendido, cancelación desde el panel, auditoría y pantallas de esas acciones.
- `auth/panel-acceso-web`: ingreso, sesión y salida del panel en el navegador, y alta de usuarios del panel.

### Modified Capabilities
- `auth/panel-login`: el refresh viaja solo por cookie, con protección CSRF, y el logout revoca el refresh hasta su vencimiento (O2).
- `turnos/creacion-sin-solape`: el alta interna `POST /api/turnos` exige rol recepción o admin (O3), y `atendido` pasa a ocupar el horario hasta su `fin` (O19).
- `turnos/reserva-publica`: la disponibilidad pública cuenta `atendido` como ocupado (O19).
- `pagos/sena-turno`: el requisito "La pre-reserva en espera no dispara notificaciones" suma el alta manual bloqueante como segundo disparador (O7, O15).

## Impact
- **Backend:** módulo nuevo `app/panel/`; `app/auth/router.py`, `schemas.py` y `service.py` (O2); `app/turnos/router.py` (O3); `app/pagos/service.py` y `estados.py` (marcado habilitado, O14); `app/turnos/models.py` (`origen`); `app/turnos/service.py` (`ESTADOS_BLOQUEANTES` suma `atendido`, y toda la cadena de libres y ocupación lo hereda); `app/shared/settings.py` (`AUSENTE_TOLERANCIA_MINUTOS`); `app/main.py`; comando de usuarios en `app/db/`.
- **API:** cuatro endpoints de escritura y dos de lectura bajo `/api/panel`. Cambian los contratos de `/api/auth/login`, `/refresh` y `/logout`, y `POST /api/turnos` pasa a requerir token.
- **Base de datos:** migración `007_turno_origen_ocupacion`, reversible: columna `origen` y EXCLUDE con `atendido`.
- **Frontend:** paquete nuevo `frontend-panel/` en el puerto 5174. `frontend-paciente/` no cambia.
- **CI y Compose:** `.github/workflows/ci.yml` suma dos jobs; `docker-compose.yml` expone la tolerancia.
- **Tests existentes:** dos tests de `test_auth_integration.py` cambian de contrato y unas 25 llamadas a `POST /api/turnos` necesitan token.
- **Docs/KB:** RN-TU-12, excepción en RN-SN-01 y R8 (`AGENTS.md` y `CLAUDE.md`), `README.md` y `CHANGES.md`, como tareas del apply.
- **Fuera de alcance:** resto del endurecimiento de C-03 (C-15, O17), UI de catálogo y disponibilidad (C-14, O18), reprogramar desde el panel (O13), pacientes, ocupación y caja (C-12), resolución de `a_reembolsar` y `en_revision` (C-12), confirmación por WhatsApp (C-09), Google Calendar (C-10).
