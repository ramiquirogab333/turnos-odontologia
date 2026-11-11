# Proposal: c-12-panel-admin-caja-ausentismo

## Why
La clínica ya agenda, cobra señas, registra cobros de presupuestos y marca quién vino y quién no, pero nadie puede ver ese dinero junto ni cerrar el día: no hay caja, ni cierre, ni dónde resolver las señas que C-06 dejó `en_revision` o `a_reembolsar` (promesa de C-06, C-07 y C-08). Tampoco hay forma de ver la ocupación por sillón ni el ausentismo, que son las métricas de éxito del producto (`01_vision_y_objetivos.md`), ni de buscar pacientes por nombre, ni de corregir un `atendido` marcado por error (seguimiento que dejaron C-08 y C-11 O15). US-007 y el Flujo 5 piden todo esto en un panel para recepción y admin.

## What Changes
- **Caja del día:** `GET /api/panel/caja?dia=` suma, en la hora de la clínica, las señas recibidas y los pagos de presupuesto `registrado` (contrato de C-11), menos las devoluciones hechas, por concepto y medio. La seña de un ausente sigue contando como ingreso y se muestra como retenida (R9).
- **Cierre de caja y liquidación:** `POST /api/panel/caja/cierres` congela un día terminado en un registro inmutable con sus líneas por concepto y medio; la consulta informa si el cierre **cuadra** contra los movimientos actuales. Un día cerrado rechaza movimientos nuevos con esa fecha (409 `caja_cerrada`). Corregir exige anular el cierre (solo admin, con motivo) y volver a cerrar. `GET /api/panel/caja/liquidacion` consolida los cierres por medio de pago.
- **Resolución de señas pendientes:** lista de pagos `en_revision` y de devoluciones pendientes; rechazar una revisión la deja `a_reembolsar`; registrar una devolución hecha la deja `reembolsado` (estado nuevo), con fecha y referencia. Los pagos excedentes de Mercado Pago se resuelven por separado.
- **Deshacer un `atendido` marcado por error:** `POST /api/panel/turnos/{id}/deshacer-atendido` (recepción y admin, con motivo de catálogo y plazo) devuelve el turno a `reservado`. **Modifica RN-TU-12** ("nadie deshace un `atendido`") y el acceso clínico de C-11 se recalcula solo.
- **Indicadores:** `GET /api/panel/ocupacion` (por sillón y día; solo cuentan turnos que ocupan agenda, `en_espera` excluida, R8) y `GET /api/panel/ausentismo` (tasa de ausentismo y recupero por señas retenidas).
- **Pacientes:** `GET /api/panel/pacientes/listado` paginado con búsqueda libre (nombre, apellido, DNI) y contadores de atendidos y ausentes. La búsqueda exacta por DNI de C-11 no cambia.
- **Panel:** navegación por secciones en `frontend-panel/` (Agenda, Pacientes, Indicadores, Caja) para recepción y admin, a 360 px (R3), con cargas en paralelo (R2) y E2E Playwright (R7).
- **Migración Alembic `009_caja_cierres_devol`** (reversible, R14): tablas `cierre_caja` y `cierre_caja_linea`, estado `reembolsado` y datos de devolución en `pago_sena` y `pago_sena_aprobacion`, extensión `unaccent`, índices (R6).
- Las decisiones abiertas **O1–O16** están en `design.md` con una opción recomendada cada una; las de dinero y de estados son de criticidad ALTA y **esperan aprobación del usuario antes del apply** (governance ALTO).

## Capabilities

### New Capabilities
- `caja/movimientos-caja`: caja del día por concepto y medio en la hora de la clínica, con las señas retenidas y la pantalla de caja.
- `caja/cierre-caja`: cierres inmutables por día, verificación de que el cierre cuadra, anulación con motivo, bloqueo de movimientos en días cerrados y liquidación por medio de pago.
- `pagos/devoluciones-sena`: resolución de los pagos de seña `en_revision` y `a_reembolsar` (rechazo, registro de la devolución, pagos excedentes).
- `turnos/indicadores-panel`: ocupación por sillón y ausentismo con recupero, y su pantalla.

### Modified Capabilities
- `turnos/gestion-panel`: se agrega deshacer un `atendido` marcado por error (API, auditoría y pantalla).
- `turnos/agenda-panel`: "Contenido de cada turno de la agenda" informa la acción `deshacer_atendido` a recepción y admin.
- `pagos/sena-turno`: "Transiciones de estado válidas del turno" deja de tratar `atendido` como final sin excepción: sale solo por la corrección de C-12.
- `pagos/pagos-presupuesto`: registrar o anular un cobro con fecha en un día cerrado se rechaza.
- `pacientes/registro-paciente`: se agrega el listado con búsqueda libre y ausentismo por paciente; la búsqueda por DNI deja de remitir a C-12.

## Impact
- **Backend:** módulo nuevo `app/caja/` (movimientos, cierres, liquidación), `app/pagos/devoluciones.py`, `app/panel/indicadores.py`, `app/pacientes/listado.py`; cambios acotados en `app/pagos/service.py` y `app/pagos/estados.py` (deshacer, sello de recepción del dinero), `app/panel/acciones.py` y `app/clinica/service_pagos.py` (bloqueo por día cerrado). Todo con type hints, ORM y async (R13, R14, R16).
- **API:** 14 endpoints nuevos bajo `/api/panel`, con esquemas Pydantic `extra="forbid"` (R15). Cambios de contrato: `POST .../pagos` y `POST .../pagos/{id}/anular` pueden responder 409 `caja_cerrada`; la agenda puede informar `deshacer_atendido`.
- **Base de datos:** migración `009`; cambia el `CHECK` de estado de `pago_sena` y de `pago_sena_aprobacion`.
- **Frontend:** `frontend-panel/` suma navegación y tres pantallas, sin dependencias nuevas.
- **Tests:** unitarios (cálculo de caja, ocupación, ausentismo, plazo de deshacer), integración con PostgreSQL real (permisos, concurrencia del cierre, bloqueo por día cerrado, migración) y E2E Playwright de los flujos de turnos y caja (R7).
- **Docs/KB (en el apply, tras aprobar):** `05_reglas_de_negocio.md` (RN-TU-12 enmendada, RN-CJ-01..05, RN-SN-11), `04_modelo_de_datos.md`, `03_actores_y_roles.md`, `09_decisiones_y_supuestos.md` (DD-11), `CHANGES.md`, `README.md`.
- **Fuera de alcance:** honorarios por profesional y liquidación a obras sociales, reembolsos automáticos por la pasarela, efectivo (RN-PG-01), exportación y auditoría transversal (C-13), pantallas de alta, edición y vínculo de pacientes (C-16), deshacer un `ausente`.
