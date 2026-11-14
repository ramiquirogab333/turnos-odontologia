# Tasks: c-14-panel-catalogo-disponibilidad

> **Governance MEDIO.** Las decisiones **O1–O13** de `design.md` están **APROBADAS (a) el 2026-11-14**. Estas tareas siguen la opción recomendada; si alguna decisión cambia, se ajustan specs, diseño y tareas primero (tarea 0.1). Implementar por grupos con checkpoint: al cerrar cada grupo se informan al usuario las decisiones no obvias que aparecieron.
>
> **Strict TDD.** Cada tarea de código sigue RED → GREEN → TRIANGULAR → REFACTOR: el test se escribe primero y falla por la razón correcta (no por un import roto), se escribe el mínimo código para pasar, se agrega al menos un caso distinto (camino feliz + borde) y se refactoriza con la suite en verde. Cada requisito de los specs tiene sus tres escenarios (esperado, error de negocio, caso de borde) y los tests llevan el nombre del escenario. Datos 100 % sintéticos (R19): `recepcion@turnos.test`, `admin@turnos.test`, `dra.ficticia@turnos.test`, "Dra. Ana Ficticia", "Dr. Juan Ejemplo", matrículas `MP-990xx`, "Carlos Sintético", `+54911000000xx`. Instantes con zona y reloj inyectado (R4), sin `sleep`. Sin commits (R11).
>
> Skills a cargar antes de cada grupo: `postgresql-table-design` (grupo 1), `vercel-react-best-practices` y `frontend-design` (grupos 6–7), `playwright-cli` (grupo 8), `spec-rules-auditor` (9.3).

## 0. Aprobación y línea base

- [x] 0.1 Confirmar con el usuario la tabla O1–O13 de `design.md` y registrar la decisión final de cada fila (con fecha). Si alguna cambia, ajustar specs, diseño y estas tareas antes de seguir. Verificar: ninguna fila PENDIENTE y `openspec validate c-14-panel-catalogo-disponibilidad --strict` pasa.
- [x] 0.2 Con `docker compose up -d postgres redis` y `alembic upgrade head`, correr `python -m pytest -q` en `backend/` y `npm test` + `npm run typecheck` en `frontend/panel` y `frontend/paciente`; registrar los conteos en el acta. Si algo falla, frenar y reportarlo como falla previa (no corregirlo acá).
- [x] 0.3 Verificar con `ls backend/src/alembic/versions` que `014` está libre y, con consultas de solo lectura sobre la base de desarrollo, que no hay franjas activas superpuestas del mismo profesional y día, ni tratamientos/sillones con el mismo `lower(btrim(nombre))`, ni matrículas repetidas. Anotar los resultados en el acta; si hay casos, consultarlos con el usuario antes del grupo 1.

## 1. Migración `014_catalogo_baja_logica` (D3, D5, D6, O1, O6, O13) — spec `dominio/modelos-core`

- [x] 1.1 RED: `backend/tests/test_catalogo_migracion_014.py`: tras `upgrade head`, `tratamiento.is_active` y `profesional.is_active` existen `NOT NULL DEFAULT true` y las filas previas quedan activas; insertar dos franjas activas superpuestas del mismo profesional/día falla con SQLSTATE `23P01`; contiguas (09–13 y 13–17) se aceptan; superpuesta pero inactiva se acepta y reactivarla falla; `" limpieza DENTAL "` duplicado falla con `23505`; matrícula `mp-99001` vs `MP-99001` falla. Verificar que falla porque la migración no existe.
- [x] 1.2 GREEN: `backend/src/alembic/versions/014_catalogo_baja_logica.py` (`down_revision = "013_auditoria_exportacion"`): columnas, verificaciones previas con `RuntimeError` que nombra ids, tipo `rango_hora`, `EXCLUDE USING gist ... WHERE (is_active)`, índices únicos funcionales; `downgrade` en orden inverso. Modelos: `ActiveMixin` en `Tratamiento` y `Profesional`, `ExcludeConstraint`/`Index` declarados en `Disponibilidad`, `Tratamiento`, `Sillon`, `Profesional`. Verificar 1.1 en verde y `test_models_metadata.py` en verde.
- [x] 1.3 TRIANGULAR: escenarios "Datos existentes que violan una restricción" (base en `013` con dos franjas superpuestas → `upgrade` aborta nombrando ambos ids y la base queda en `013`) y reversibilidad (`downgrade -1` sin perder filas, `upgrade head` vuelve) con `alembic_helpers`. Actualizar los tests que fijaban `013` como head. Verificar en verde.

## 2. Esquemas y validaciones de borde (D4, D5, O12) — spec `catalogo/tratamientos-disponibilidad`

- [x] 2.1 RED: `backend/tests/test_catalogo_schemas.py` (unit): duración 5 y 480 aceptadas, 0/-5/7/485 rechazadas nombrando el campo; precio `99999999.99` aceptado, `100000000.00`, `-1` y `1.005` rechazados; `nombre` con espacios en los extremos se recorta; `activo` acepta bool y rechaza `"quizas"`; `Read` de tratamiento, profesional y franja expone `activo`. Verificar que falla.
- [x] 2.2 GREEN: `app/catalogo/schemas.py` (constantes `DURACION_MIN/MAX/PASO`, `PRECIO_MAX`; `activo` con alias a `is_active`). Verificar 2.1 en verde y que `test_catalogo_integration.py` sigue en verde (ajustar solo los tests que usen duraciones fuera de rango, si hay).
- [x] 2.3 RED → GREEN: "Edición de franjas validada con los valores guardados" (solo `hora_fin` 14:00 → 200; `hora_fin` 08:00 → 422 sin cambios; `hora_inicio` igual al fin → 422) y FK inexistente en `profesional_id`/`sillon_defecto_id` → 422, en `backend/tests/test_catalogo_franjas_integration.py`. Implementar la validación combinada en el servicio de franjas (D4). Verificar en verde.

## 3. Servicio: baja lógica, 409 y unicidad (D1, D3, D5, D10, O1, O6, O7, O13) — spec `catalogo/tratamientos-disponibilidad`

- [x] 3.1 RED: `backend/tests/test_catalogo_baja_logica_integration.py`: los tres escenarios de "Baja lógica" (desactivar tratamiento con turnos pasados → 200 y auditoría `UPDATE` con `is_active` true→false e IP; `"quizas"` → 422 sin auditoría; reactivar franja → 200 o 409 si se superpone) y de "Borrar un ítem en uso responde 409" (sillón sin uso 204 auditado; profesional con un `cancelado` → 409 `en_uso` sin auditoría y con sus franjas; franja con 3 turnos futuros → 204 y turnos intactos), más presupuesto y conexión de Google como referencias. Verificar que fallan.
- [x] 3.2 GREEN: `app/catalogo/service.py`: chequeo de referencias por entidad, `CatalogoEnUsoError` → 409 `en_uso`, captura de `IntegrityError` de FK como red de seguridad; manejadores en `app/main.py`. Verificar 3.1 en verde.
- [x] 3.3 RED → GREEN: "Franjas activas sin superposición" (otro día/otro profesional 201; superpuesta 409 con id y horario de la que choca; dos altas simultáneas con `asyncio.gather` → un 201 y un 409, nunca 500) y "Nombres y matrículas únicos" (nuevo 201; `" limpieza DENTAL "` 409 `duplicado` campo `nombre`; renombrar al mismo nombre 200). Implementar pre-chequeo + captura de `23P01`/`23505`. Verificar en verde.
- [x] 3.4 REFACTOR: un solo traductor de errores de integridad del catálogo (`motivo`, `campo`, detalle) usado por los cuatro servicios; sin cambio de comportamiento. Verificar el grupo 3 y `test_catalogo_integration.py` en verde.

## 4. Consulta de impacto y turnos intactos (D2, O2, O3) — spec `catalogo/tratamientos-disponibilidad`

- [x] 4.1 RED: `backend/tests/test_catalogo_impacto_integration.py`: impacto de franja lunes 14–18 con turnos lunes 14:30 `reservado`, 17:30 `en_espera`, 18:00 `reservado` → `turnos_futuros: 2` y fecha del primero, sin nombres ni teléfonos; odontóloga 403; id inexistente 404; tratamiento con solo un `atendido` pasado y un `cancelado` futuro → 0 y `null`; reloj inyectado y servidor en UTC con clínica en `America/Argentina/Buenos_Aires` (un turno a las 23:30 locales del lunes cuenta como lunes). Verificar que falla.
- [x] 4.2 GREEN: `GET /api/admin/{recurso}/{id_}/impacto` con `ImpactoRead` (R15) en `app/catalogo/router.py` y consulta ORM en el servicio (R14); política exenta con motivo en `politica_auditoria._catalogo()`. Verificar 4.1 en verde y el test de contrato de C-13 en verde.
- [x] 4.3 RED → GREEN: "Los cambios del catálogo no alteran turnos existentes": alargar duración y subir precio con un turno futuro y seña acreditada (turno y `PagoSena.monto` intactos; horarios libres nuevos de 60 min); desactivar profesional con 2 `confirmado` (siguen, sin recordatorio ni evento nuevo); reprogramar un turno viejo después del cambio usa la duración vigente. Solo tests si el comportamiento ya es correcto (documentar en el acta); implementar si alguno falla. Verificar en verde.

## 5. Reserva pública y alta manual con ítems inactivos (D7, D8) — specs `turnos/reserva-publica`, `turnos/gestion-panel`

- [x] 5.1 RED: `backend/tests/test_public_catalogo_inactivos_integration.py`: tratamiento inactivo fuera de `/api/public/tratamientos` (sin exponer `activo`); profesional inactivo con franja activa fuera de `/profesionales`; disponibilidad y `POST /api/public/turnos` con tratamiento o profesional inactivo → 422 `no_reservable` con campo, sin turno ni pago; reactivar vuelve a ofrecer horarios; único sillón en `mantenimiento` → lista vacía 200. Verificar que falla.
- [x] 5.2 GREEN: `NoReservableError` + manejador; filtros en `app/public/router.py` y `app/public/service.py`. Verificar 5.1 en verde y la suite de reserva pública (C-05/C-06/C-10) en verde.
- [x] 5.3 RED → GREEN: `backend/tests/test_panel_alta_inactivos_integration.py`: alta manual con profesional inactivo → 422 `no_reservable` sin turno ni auditoría; sillón elegido en `mantenimiento` → 422 `no_reservable` campo `sillon_id`; `GET /api/panel/agenda/opciones` trae `activo` en profesionales y tratamientos. Implementar en `app/panel/service.py` y esquemas. Verificar en verde y la suite de `gestion-panel` (C-08) en verde.
- [x] 5.4 RED → GREEN (`frontend/paciente`, Vitest): al reservar, un 422 `no_reservable` muestra "Ese tratamiento ya no se ofrece. Elegí otro." y vuelve al paso 1 conservando nombre y teléfono. Verificar `npm test` y `npm run typecheck` en verde.
- [x] 5.5 RED → GREEN (aprobado por el usuario 2026-11-14): `backend/tests/test_gestion_reprogramar_inactivos_integration.py` (todo activo 200; profesional o tratamiento inactivo → 422 `no_reservable` con turno y eventos intactos; sillones en mantenimiento → 409) y `app/gestion/service.py` reutiliza `NoReservableError`; `frontend/paciente`: tipo `no_reservable` con aviso propio (`api.gestion.test.ts`, `GestionTurno.test.tsx`). Delta `specs/turnos/gestion-paciente`.

## 6. Panel: cliente, ruta y funciones puras (D9, O4, O5, O9) — spec `catalogo/catalogo-panel`

- [x] 6.1 RED: `frontend/panel/src/lib/catalogo.test.ts`: agrupar franjas por día (lunes→domingo, ordenadas, días vacíos presentes), `formatoPrecio("18500.00") === "$ 18.500"`, `formatoDuracion(45) === "45 min"`, validación del formulario con los mismos topes del backend, traducción de `en_uso` / `franja_superpuesta` / `duplicado` / `no_reservable` / 422 de FastAPI a mensajes por campo, texto del impacto (0, 1 y N turnos; falla). Verificar que falla.
- [x] 6.2 GREEN: `frontend/panel/src/lib/catalogo.ts` y tipos en `lib/tipos.ts` sin `any` (R1). Verificar 6.1 en verde.
- [x] 6.3 RED → GREEN: `lib/api.catalogo.test.ts`: `catalogo()` dispara los cuatro `GET` antes de resolver el primero (R2), respuesta malformada → `ErrorDeRespuesta`, 409 conserva `motivo`, `impacto()` y las escrituras por recurso; implementar en `lib/api.ts`. Verificar en verde.
- [x] 6.4 RED → GREEN: `lib/ruta.test.ts`: `'catalogo'` en `SECCIONES`, fuera de `SECCIONES_ODONTOLOGA`; `pestanaDeCatalogo` (válidas, inválida → tratamientos, otra sección → tratamientos). `App.test.tsx`: la odontóloga con `#/catalogo?pestana=horarios` ve la agenda sin pedir `/api/admin/*`. Implementar. Verificar en verde.

## 7. Panel: pantallas del catálogo (D9, O7, O10) — spec `catalogo/catalogo-panel`

- [x] 7.1 RED → GREEN: `Catalogo.test.tsx` + `Catalogo.tsx`: carga en paralelo, error con "Reintentar" sin listas, pestañas por hash (patrón `Datos`). Verificar en verde.
- [x] 7.2 RED → GREEN: `TratamientosCatalogo.test.tsx` + componente: lista con estado como texto, "No se ofrece para reservar", "Sin seña"; cambiar duración (confirmación y aviso de turnos nuevos); 7 minutos → error de campo conservando lo escrito; precio 0 con aviso; catálogo vacío invita a cargar; doble toque → un solo pedido. Verificar en verde.
- [x] 7.3 RED → GREEN: `ProfesionalesCatalogo` y `SillonesCatalogo` con sus tests: sillón a "En mantenimiento"; matrícula repetida → error de campo; "Sin especialidad". Verificar en verde.
- [x] 7.4 RED → GREEN: `HorariosCatalogo.test.tsx` + componente: bloque por día, "Sin atención este día", agregar franja (martes 09–13), superpuesta → mensaje con la franja que choca, contiguas ok, pausar/reactivar, horas en hora de la clínica con el navegador en otra zona. Verificar en verde.
- [x] 7.5 RED → GREEN: `ConfirmarCambioCatalogo.test.tsx` + componente sobre `Dialogo`: con 3 turnos (texto de que no se cancelan), sin turnos, falla del impacto (permite seguir), borrar tratamiento usado → 409 con "Desactivar" ofrecido. Verificar en verde.
- [x] 7.6 RED → GREEN: `AltaManual.tsx` ofrece solo activos y `Agenda.tsx` marca "(inactivo)" en el filtro (tests existentes + nuevos). Verificar en verde.
- [x] 7.7 REFACTOR + estilos: clases en `estilos.css` con los tokens existentes (sin colores nuevos sueltos), acciones de ≥ 48 px en fila propia, pestañas con `flex-wrap`, foco visible. Verificar `npm test`, `npm run typecheck`, `npm run lint` y `npm run build` en verde.

## 8. E2E Playwright (R3, R7) — specs `catalogo/catalogo-panel`, `turnos/reserva-publica`

- [ ] 8.1 `frontend/panel/e2e/catalogo.spec.ts` a 360 y 1280 px contra el stack E2E (`docker compose --profile e2e up -d --wait`): (a) recepción cambia la duración de un tratamiento y luego `GET /api/public/disponibilidad` (con `request`) devuelve horarios de la nueva duración (US-008 CA-2); (b) agrega una franja el martes y aparecen horarios públicos ese martes; una superpuesta muestra el error; (c) quitar una franja con un turno tomado muestra "1 turno" en el diálogo y el turno sigue en la agenda; (d) desactivar un tratamiento lo saca de `/api/public/tratamientos`, y borrar uno usado muestra el mensaje de 409; (e) a 360 px el ancho del documento no supera la ventana en las cuatro pestañas; (f) la odontóloga no ve "Catálogo". Datos sintéticos creados por la prueba y limpiados al final. Verificar en verde en CI.
- [ ] 8.2 Correr las suites E2E completas de ambos frontends (C-05…C-15). Verificar: todo en verde, sin tests saltados nuevos. En este host Windows Playwright está restringido: la evidencia es la corrida de CI (anotar el enlace o el resultado en el acta).

## 9. Documentación, auditoría y cierre

- [x] 9.1 Actualizar `knowledge-base/04_modelo_de_datos.md` (`is_active`, `EXCLUDE` de franjas, índices únicos), `05_reglas_de_negocio.md` (precisión de RN-TU-04/05/07: cambios solo para turnos nuevos, inactivos no reservables, franjas sin superposición), `03_actores_y_roles.md` (precisión de O5), `06_funcionalidades.md` (US-008 con lo aprobado) y el README (sección "Catálogo": cómo cargar horarios, qué pasa con los turnos tomados, que un turno de un profesional inactivo no se reprograma online). Verificar coherencia con specs y código.
- [x] 9.2 Actualizar `CHANGES.md` §C-14 (scope final, migración `014`, seguimientos: excepciones por fecha O8, control optimista O11) y §Backlog. Verificar coherencia con los specs.
- [x] 9.3 Correr `spec-rules-auditor` sobre el código y los specs finales contra `05_reglas_de_negocio.md` y `AGENTS.md`; registrar el dictamen en `design.md` y corregir lo observado. Verificar dictamen APROBADO u OBSERVACIONES sin bloqueos.
- [ ] 9.4 Verificación final: `python -m pytest -q` (backend), `npm test` + `npm run typecheck` + `npm run lint` + `npm run build` (panel y paciente), E2E completos en CI y `openspec validate c-14-panel-catalogo-disponibilidad --strict`. Registrar conteos en el acta.

## Workflow follow-up

- Archivar con `/opsx:archive c-14-panel-catalogo-disponibilidad` cuando el usuario lo apruebe y marcar `[x]` C-14 en `CHANGES.md`.
- Sin commits ni push salvo pedido explícito (R11); commits en conventional commits, sin coautoría IA (R12).

## Acta

- **Aprobación:** el usuario aprobó O1–O13 con la opción (a) el 2026-11-14; registrado en `design.md`. O12 (rango de duración 5–480 min) queda `[SUPUESTO]` y está en `10_preguntas_abiertas.md` (Baja, Admin/clínica). `openspec validate --strict` pasa.
- **Docker:** el daemon estuvo caído al inicio; el usuario lo levantó (Compose `postgres` y `redis` healthy) y el apply se reanudó en 0.2. Tests del backend desde el host contra Compose.
- **Migración (0.3):** `014` estaba libre; la base de desarrollo (también la de tests) no tenía franjas activas superpuestas ni nombres/matrículas repetidos.
- **Línea base (antes):** frontend panel 500 tests (29 archivos) y `tsc` limpio; frontend paciente 211 tests (13 archivos) y `tsc` limpio; backend 2172 pasaron en la corrida completa con 4 fallas/errores intermitentes de timing bajo carga (`test_ocupacion`, `test_gcal_conflictos`, `test_gcal_notificador`, `test_sena_inicio`) que pasan en aislamiento (pre-existentes, no se corrigieron).
- **Final (después):** backend 2278 pasaron + 1 intermitente de `test_gcal_conflictos_integration.py` que pasa en aislamiento (19/19); panel 605 tests (37 archivos), `tsc`, `lint` y `build` limpios; paciente 217 tests (13 archivos), `tsc`, `lint` y `build` limpios. **E2E no ejecutados** (Windows restringido): `frontend/panel/e2e/catalogo.spec.ts` está escrito y verificado solo con `tsc`/`lint`; la evidencia verde es la de CI (8.1 y 8.2 quedan abiertas hasta entonces; 9.4 también).
- **Ajustes a tests existentes por contrato nuevo:** los tests de migración que fijaban `013` como head pasan a `014` y el de auditoría baja a `012` explícito; `sena_helpers.sembrar_agenda` ya no duplica una franja del mismo día (la base ahora lo rechaza); `test_sillon_indicado_inactivo` pasa de 409 `sillon` a 422 `no_reservable` (D7).
- **4.3:** los tres escenarios de "turnos intactos" ya eran correctos: solo se agregaron tests (sin código).
- **Reprogramación con ítems inactivos (aprobada por el usuario 2026-11-14, tarea 5.5):** `POST /api/public/gestion/reprogramar` responde 422 `no_reservable` si el profesional o el tratamiento del turno están inactivos; el panel del paciente lo explica con un aviso propio (no "elegí otro horario"). Cierra la observación O-A de la auditoría final.
- **Hallazgo técnico:** dos altas de franjas superpuestas simultáneas pueden terminar en deadlock (40P01) en el `EXCLUDE`; se traduce a 409 `franja_superpuesta`. `Disponibilidad.updated_at` exige `refresh` tras el `UPDATE`.
- **Auditoría final (`spec-rules-auditor`):** OBSERVACIONES sin bloqueos (ver `design.md`).
