# Proposal: c-14-panel-catalogo-disponibilidad

## Why
US-008 ("edito la tabla tratamiento→duración sin tocar código"; "los horarios libres se recalculan con la nueva configuración", RN-TU-04/05/07) sigue sin pantalla: C-04 entregó solo los CRUD `/api/admin/*` y la UI se movió de C-08 a C-14 (decisión O18 del 2026-11-09). Hoy recepción no puede cambiar una duración, un precio o un horario de atención sin pedírselo a quien tenga acceso a la API.

Relevado en el código (HEAD `db6632d`, última migración `013_auditoria_exportacion`), **el backend de C-04 no alcanza para operar el catálogo con turnos reales**:
- **Solo hay borrado físico.** `Tratamiento` y `Profesional` no tienen marca de activo; `Turno` (y `presupuesto_linea`, `gcal_conexion`) los referencian con `ON DELETE RESTRICT`. Borrar un tratamiento o profesional que alguna vez tuvo un turno lanza `IntegrityError` **sin manejar → 500** (el diseño de C-04 prometía 409 y nunca se implementó). No hay forma de retirar un tratamiento del catálogo público sin perder su historia.
- **`Disponibilidad.is_active` existe** (la usan la reserva pública y los indicadores) **pero la API no la expone**: no se puede pausar una franja, solo borrarla.
- **Franjas superpuestas del mismo profesional y día se aceptan** y el cálculo de horarios libres las recorre por separado (horarios duplicados o desfasados).
- **Editar solo `hora_fin` de una franja** no se valida contra la `hora_inicio` guardada: el `CHECK` de la base falla → 500.
- **Sin topes:** una duración de 10.000 minutos o un precio mayor que `NUMERIC(10,2)` pasan la validación (el segundo termina en 500).
- La reserva pública, el alta manual y las opciones de la agenda listan **todos** los tratamientos y profesionales: no hay noción de "no se ofrece más".

Lo que sí está: RBAC `recepcion`/`admin` en todas las rutas (la odontóloga recibe 403), esquemas Pydantic, auditoría `CREATE`/`UPDATE`/`DELETE` en la misma transacción con IP real y sin identidad del personal (C-13 D2), y la política de auditoría por ruta (C-13) ya declara los 20 endpoints. Los turnos guardan su propio `fin`: cambiar una duración no altera turnos existentes.

## What Changes
- **Pantalla "Catálogo" en `frontend/panel/` (recepción y admin, 360 px):** sección nueva `#/catalogo` con pestañas Tratamientos, Profesionales, Sillones y Horarios. Alta, edición, desactivación/reactivación y borrado de cada ítem; editor semanal de franjas por profesional (un bloque por día, "Agregar franja", pausar, quitar). Las cuatro listas se piden en paralelo (R2). La odontóloga no ve la sección (O4, O5).
- **Baja lógica de tratamientos y profesionales (O1):** columna `is_active` (expuesta como `activo`) en `tratamiento` y `profesional`; `activo` también se expone en las franjas. Un ítem inactivo **no se ofrece para reservar** (catálogo público, horarios libres, alta manual) pero sigue en la agenda, los históricos y los filtros.
- **Los turnos ya tomados se respetan (O2, O3):** desactivar, borrar o acortar algo del catálogo nunca cancela ni mueve turnos; un cambio de duración o precio solo vale para turnos nuevos (los existentes conservan inicio, fin y seña). Antes de confirmar, el panel muestra **cuántos turnos futuros vigentes** quedan alcanzados (`GET /api/admin/{recurso}/{id}/impacto`, sin datos de pacientes).
- **Borrado seguro:** `DELETE` de un ítem con referencias responde **409 `en_uso`** (sugiere desactivar) en lugar de 500, sin auditoría (no pasó nada).
- **Franjas sin superposición (O6):** 409 `franja_superpuesta` para franjas activas del mismo profesional y día que se pisan, con garantía en la base (`EXCLUDE USING gist`); las contiguas (13:00 y 13:00) se aceptan. La edición parcial se valida con los valores combinados (422, nunca 500).
- **Validaciones de borde (O12, O13):** duración entre 5 y 480 minutos en múltiplos de 5; precio hasta 99.999.999,99; nombre de tratamiento y de sillón únicos sin distinguir mayúsculas, matrícula única.
- **Migración `014_catalogo_baja_logica`** (reversible, R14): columnas `is_active`, tipo de rango horario y `EXCLUDE` de franjas, índices únicos; verifica los datos existentes antes de crear las restricciones.
- **Decisiones abiertas O1–O13** en `design.md`, cada una con opciones y una recomendada. **Todas PENDIENTES** de aprobación del usuario (governance MEDIO).

## Capabilities

### New Capabilities
- `catalogo/catalogo-panel`: pantallas del panel para administrar tratamientos, profesionales, sillones y horarios de atención (listas, formularios, confirmación con impacto, mensajes de error, permisos por rol, 360 px).

### Modified Capabilities
- `catalogo/tratamientos-disponibilidad`: baja lógica (`activo`), borrado con referencias → 409, consulta de impacto, franjas sin superposición, validación combinada en la edición de franjas, topes de duración y precio, unicidad de nombres y matrícula, cambios de duración/precio solo para turnos nuevos.
- `turnos/reserva-publica`: el catálogo público y los horarios libres excluyen tratamientos y profesionales inactivos.
- `turnos/gestion-panel`: el alta manual rechaza tratamientos y profesionales inactivos; las opciones de la agenda informan si cada uno está activo.
- `dominio/modelos-core`: `tratamiento` y `profesional` con `is_active`; franjas activas sin superposición garantizada en la base; unicidad de nombres y matrícula.

## Impact
- **Backend:** `app/catalogo/` (esquemas con `activo` y topes, servicio con 409 `en_uso`/`franja_superpuesta`/`nombre_duplicado`, validación combinada de franjas, consulta de impacto, router), `app/turnos/models.py` y `app/models/core.py` (`ActiveMixin`), `app/public/` (filtro de activos), `app/panel/service.py` (opciones con `activo`, alta manual), `app/plataforma/politica_auditoria.py` (las cuatro rutas `impacto`, exentas con motivo).
- **API:** nuevo `GET /api/admin/{tratamientos|profesionales|sillones|disponibilidad}/{id}/impacto`; campo `activo` en lectura y escritura de tratamientos, profesionales y franjas; `activo` en `tratamientos`/`profesionales` de `GET /api/panel/agenda/opciones` (aditivo). **BREAKING (contrato):** `DELETE` de un ítem referenciado pasa de 500 a 409; un `POST`/`PUT` con duración fuera de 5–480 o no múltiplo de 5, nombre duplicado o franja superpuesta pasa a 409/422 (verificar el seed y los tests que usan duraciones como 1 o 7 minutos).
- **Base de datos:** migración `014_catalogo_baja_logica` (verificar el número antes del apply). Si hay datos existentes que violan las restricciones nuevas, la migración se detiene con un mensaje que nombra los ids (no corrige datos sola).
- **Frontend:** `frontend/panel` (sección "Catálogo", cliente de API y guardas de tipos, ruta `#/catalogo?pestana=`). La sección de la odontóloga no cambia.
- **E2E:** `frontend/panel/e2e/catalogo.spec.ts` a 360 y 1280 px (R7), incluida la verificación de que los horarios públicos se recalculan (US-008 CA-2).
- **Docs/KB:** `04_modelo_de_datos.md` (columnas y restricciones nuevas), `05_reglas_de_negocio.md` (precisión de RN-TU-04/05/07: cambios solo para turnos nuevos, ítems inactivos), `03_actores_y_roles.md` (precisión de lectura de la odontóloga según O5), `06_funcionalidades.md` (US-008), README (sección Catálogo), `CHANGES.md`.
- **Fuera de alcance:** excepciones por fecha (vacaciones, feriados, bloqueos puntuales) (O8), control de concurrencia optimista (O11), historial de precios, nomenclador y obras sociales (C-11/C-16), vínculo usuario↔profesional desde la UI, edición del catálogo por la odontóloga.
