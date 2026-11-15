# Proposal: c-16-panel-ficha-presupuestos-ui

## Why
C-11 entregó la ficha clínica, el odontograma FDI, los presupuestos con cobertura y sus cobros **solo por API** (decisión O13 del 2026-11-10), y C-12 dejó fuera de su pantalla de Pacientes el alta, la edición y el vínculo turno ↔ paciente (C-12 O16). Hoy nadie puede usar US-009 ni US-010 desde el panel: la odontóloga no puede escribir la ficha ni el odontograma de sus pacientes (O4, O16 de C-11), recepción no puede armar un presupuesto ni registrar su cobro, y como ningún turno se vincula con un `Paciente` desde la UI, **el ausentismo por paciente y el acceso clínico de la odontóloga nunca se activan** (ambos se calculan sobre `turno.paciente_id`).

Relevado en el código (HEAD `29638c0`, última migración `014_catalogo_baja_logica`), la API de C-11/C-12 cubre casi todo, pero **faltan tres datos para poder construir las pantallas sin adivinar**:
- **La agenda no informa el paciente vinculado.** `TurnoAgenda` trae `paciente_nombre` (que es el contacto del turno) pero no `paciente_id`: la UI no puede saber si un turno ya está vinculado ni enlazar a su ficha. La odontóloga, que no tiene listado de pacientes (403, C-12), **no tiene ningún camino para llegar a la ficha** de sus pacientes.
- **No hay forma de saber de antemano si la odontóloga puede escribir.** `alcance_paciente` calcula `clinico_completo` / `clinico_lectura` (RN-CL-04), pero ninguna respuesta lo expone: la UI solo se enteraría al guardar (403 `acceso_clinico_vencido`).
- **No hay endpoint de obras sociales.** El alta de paciente (`obra_social_id`) y el presupuesto (otra obra social o particular) necesitan la lista de obras sociales activas; hoy solo existen en el seed.

## What Changes
- **Detalle del paciente en `frontend/panel/` (360 px):** ruta `#/pacientes/{id}` con pestañas **Ficha**, **Odontograma**, **Presupuestos** y, para recepción y admin, **Datos**. La cabecera muestra los datos que el rol puede ver (O3 de C-11: la odontóloga ve DNI y afiliado, nunca teléfono ni email) y si su acceso es de solo lectura.
- **Ficha clínica:** antecedentes (alergias, medicación, antecedentes médicos, observaciones, ≤ 2000 caracteres) con control de versión: un 409 `version_desactualizada` no pisa nada y conserva lo escrito para recuperarlo; historia de turnos. Recepción, admin y la odontóloga con acceso completo editan; con acceso vencido solo lee.
- **Odontograma FDI:** estado vigente por pieza y cara (permanentes y temporales), registro **en lote** de 1 a 64 hallazgos (solo alta, RN-CL-01) e historial paginado.
- **Presupuestos y cobros (recepción y admin):** armado de borrador (tratamientos, cantidad, pieza/cara opcional, obra social o particular), importes calculados por el servidor (RN-PG-04), transiciones presentar / aceptar / rechazar / anular con motivo (RN-PG-05), registro y anulación de cobros con saldo (RN-PG-06, 409 `caja_cerrada`). La odontóloga los lee sin pagos ni saldo.
- **Pacientes:** «Nuevo paciente» y edición de datos administrativos desde la sección Pacientes; cada fila del listado abre el detalle.
- **Vínculo turno ↔ paciente desde la agenda (recepción y admin):** «Vincular paciente» en la tarjeta del turno → búsqueda exacta por DNI → alta prellenada si no existe → vínculo. Corregir un vínculo existente pide confirmación (puede cambiar el acceso clínico, C-12 O9). Los turnos vinculados muestran «Ver ficha» (también a la odontóloga).
- **Backend mínimo y aditivo (sin migraciones):** `paciente_id` en cada turno de `GET /api/panel/agenda`; `acceso_clinico` (`nivel`, `puede_escribir`) en `GET /api/panel/pacientes/{id}`; nuevo `GET /api/panel/obras-sociales` (activas, recepción y admin).
- **E2E Playwright a 360 y 1280 px (R7):** edición de ficha (incluido el 409), registro de odontograma en lote, ciclo de presupuesto con cobro y vínculo turno ↔ paciente.
- **Decisiones abiertas O1–O15** en `design.md`, cada una con opciones y una recomendada. **Todas PENDIENTES** de aprobación del usuario (governance MEDIO, datos de salud).

## Capabilities

### New Capabilities
- `pacientes/pacientes-panel`: pantallas del panel para el detalle del paciente (cabecera por rol, pestañas, rutas), alta y edición de datos administrativos, y vínculo turno ↔ paciente desde la agenda.
- `pacientes/ficha-panel`: pantalla de la ficha clínica (antecedentes con control de versión, historia de turnos, solo lectura según el acceso).
- `clinica/odontograma-panel`: pantalla del odontograma FDI (estado vigente, registro en lote, historial).
- `clinica/presupuestos-panel`: pantallas de presupuestos (armado, estados, vista por rol) y de sus cobros (registro, anulación, saldo).

### Modified Capabilities
- `turnos/agenda-panel`: cada turno informa el id del paciente vinculado (o `null`) a todos los roles del panel.
- `pacientes/registro-paciente`: la consulta de un paciente informa el acceso clínico de quien consulta; nuevo listado de obras sociales activas para el panel.

## Impact
- **Backend (aditivo):** `app/panel/schemas.py` y `app/panel/service.py` (`paciente_id` en `TurnoAgenda`); `app/pacientes/schemas.py` y `router.py` (`AccesoClinicoOut` en `PacienteOut` y `PacienteVistaClinicaOut`, derivado de `alcance_paciente`); router y esquema nuevos de obras sociales (ubicación en `design.md` D3); `app/plataforma/politica_auditoria.py` (ruta nueva exenta con motivo; el test de contrato de C-13 falla si se olvida).
- **API:** `GET /api/panel/obras-sociales` nuevo; campos nuevos `paciente_id` (agenda) y `acceso_clinico` (paciente). Ningún campo existente cambia ni se quita y las guardas de tipos del panel ignoran campos desconocidos, así que los clientes actuales no se rompen. Sin cambios de reglas, permisos ni auditoría de las rutas de C-11.
- **Base de datos:** ninguna migración.
- **Frontend:** `frontend/panel` (rutas `#/pacientes/{id}?pestana=`, componentes del detalle, ficha, odontograma, presupuestos y cobros, diálogo de vínculo en la agenda, alta/edición de paciente, cliente de API con guardas y funciones puras). `frontend/paciente` no cambia.
- **E2E:** `frontend/panel/e2e/ficha.spec.ts`, `odontograma.spec.ts`, `presupuestos.spec.ts` y ampliación de `pacientes.spec.ts`/`gestion.spec.ts` para el vínculo, a 360 y 1280 px; se corren en local (Playwright habilitado en este host desde 2026-11-14) y en CI.
- **Docs/KB:** `06_funcionalidades.md` (US-009, US-010 con lo entregado), `03_actores_y_roles.md` (cómo llega la odontóloga a la ficha), `09_decisiones_y_supuestos.md`, README (sección Pacientes y ficha), `CHANGES.md` (estado de C-16 y seguimientos).
- **Fuera de alcance:** listado propio de pacientes de la odontóloga (O1 b, seguimiento), desvincular un turno (dejarlo sin paciente), control de concurrencia en los datos administrativos del paciente (O13), editar nomenclador u obras sociales, devolución de un cobro de presupuesto (C-12 O2, backlog), impresión o PDF del presupuesto, imágenes y adjuntos clínicos.
