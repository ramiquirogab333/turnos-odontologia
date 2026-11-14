# Design: c-14-panel-catalogo-disponibilidad

> Governance **MEDIO** (configuración del negocio con efecto sobre la reserva pública y la agenda): se implementa con checkpoints. Las decisiones no obvias están en la tabla **O1–O13** al final, cada una con opciones y una recomendada. **Todas APROBADAS (a) por el usuario el 2026-11-14** (O12: el rango de duración sigue `[SUPUESTO]` hasta confirmación de la clínica); los specs y `tasks.md` siguen la opción (a).

## Context

Motivación en `proposal.md` (Why). Estado relevado en el código (HEAD `db6632d`, última migración `013_auditoria_exportacion`):

**API de C-04** (`app/catalogo/router.py`, `service.py`, `schemas.py`): 20 rutas `GET/POST/PUT/DELETE` bajo `/api/admin/{tratamientos,profesionales,sillones,disponibilidad}`, todas con `require_recepcion_o_admin` (la odontóloga recibe 403 también en lectura). `BaseCatalogoService` hace `create/update/delete` con auditoría `CREATE/UPDATE/DELETE` vía `plataforma.auditoria.registrar` en la misma transacción, IP real y sin `nombre`/`matricula` (C-13 D2). `delete` es **físico**. Los `PUT` son parciales (`exclude_unset`). La política por ruta de C-13 ya declara las 20 rutas (`_catalogo()` en `politica_auditoria.py`: `GET` exentas por "configuración o catálogo sin datos de pacientes").

**Modelo:**

| Tabla | Activo hoy | Referencias entrantes |
|---|---|---|
| `tratamiento` (nombre, `duracion_minutos > 0`, `precio_base NUMERIC(10,2) >= 0`) | — | `turno` RESTRICT, `presupuesto_linea` RESTRICT, `nomenclador` CASCADE |
| `profesional` (nombre, matrícula, especialidad) | — | `turno` RESTRICT, `gcal_conexion` RESTRICT, `disponibilidad` CASCADE, `usuario.profesional_id` SET NULL |
| `sillon` (nombre, `estado IN (activo, inactivo, mantenimiento)`) | `estado` | `turno` RESTRICT, `disponibilidad.sillon_defecto_id` SET NULL |
| `disponibilidad` (profesional, `dia_semana 0–6`, `hora_inicio`, `hora_fin`, sillón preferido) | `is_active` (ActiveMixin), **no expuesto en la API** | ninguna (`turno` no la referencia) |

No hay manejador de `IntegrityError` en el catálogo: borrar un ítem referenciado o un `PUT` de franja con solo `hora_fin < hora_inicio` guardada termina en **500**. No hay unicidad de nombres ni matrículas. Nada impide franjas superpuestas.

**Quién lee el catálogo:** reserva pública (`/api/public/tratamientos` lista todos; `/profesionales` filtra por franja activa; `_slots_libres` usa franjas activas y sillones `activo`, paso = duración vigente desde el inicio de cada franja), alta manual y opciones de la agenda (`panel/service.py`: profesionales y tratamientos todos, sillones activos), gestión del paciente (reprogramar usa la **duración vigente**, `gestion/service.py:248`), indicadores (franjas activas, sillones activos). `Turno` guarda `inicio`/`fin` propios y `PagoSena.monto` propio: los cambios de catálogo no los tocan.

**Panel:** navegación por hash con 7 secciones (`lib/ruta.ts`; la odontóloga ve `agenda` y `google-calendar`), patrón de pestañas en `Datos.tsx` (`selector` + `role="tablist"`, pestaña en `#/datos?pestana=`), `Dialogo.tsx` para confirmaciones, `useEnvio.ts` para envíos con estado, cliente `lib/api.ts` con guardas de tipos (`guardas.ts`) y `ErrorApiPanel`/`ErrorDeRespuesta`, renovación de sesión en `lib/sesion.ts`. La navegación (`.secciones ul`) ya hace `flex-wrap`.

## Goals / Non-Goals

**Goals:**
- Que recepción cambie duraciones, precios, profesionales, sillones y horarios desde el celular, y que los horarios públicos se recalculen solos (US-008 CA-1/CA-2).
- Que ningún cambio del catálogo rompa un turno ya tomado ni un dato histórico.
- Cero 500 previsibles en el CRUD del catálogo: todo rechazo es 404/409/422 con motivo.
- Invariantes del catálogo garantizadas en la base, no solo en la aplicación (mismo criterio que R5).

**Non-Goals:**
- Excepciones por fecha (vacaciones, feriados, cierre de un día puntual) (O8).
- Reprogramar o avisar automáticamente a los pacientes alcanzados por un cambio (O2 b/c).
- Historial de precios o vigencias futuras ("desde el 1/12 cuesta X").
- Control de concurrencia optimista (O11).
- Que la odontóloga vea o edite el catálogo (O5).

## Decisions

### D1. Baja lógica en lugar de borrado (O1)

Se agrega `ActiveMixin` (`is_active BOOLEAN NOT NULL DEFAULT true`) a `Tratamiento` y `Profesional`, igual que `Disponibilidad` y `Usuario`. En la API el campo se llama `activo` (lectura, `Create` opcional, `Update`), mapeado a `is_active`; en franjas se expone el `is_active` que ya existe. Sillones conservan `estado` (sin columna nueva): `activo` = se ofrece; `inactivo` y `mantenimiento` = no se ofrece.

"Inactivo" significa **no se ofrece para turnos nuevos**: se excluye de `/api/public/tratamientos`, `/api/public/profesionales`, la consulta de horarios libres y la reserva pública (422 `no_reservable`), y del alta manual (422 `no_reservable`). Sigue visible en `/api/admin/*`, en la agenda, en los filtros (marcado "(inactivo)"), en presupuestos, exportaciones y auditoría.

`DELETE` se mantiene para corregir una carga equivocada: antes de borrar, el servicio comprueba referencias (`turno`, `presupuesto_linea`, `gcal_conexion` según la entidad) y responde **409 `en_uso`**; además se captura `IntegrityError` (FK) como red de seguridad ante una carrera → mismo 409. Sin auditoría cuando se rechaza. Borrar un profesional sin turnos sigue arrastrando sus franjas (CASCADE de C-02), y eso se audita solo como `DELETE` del profesional (las franjas dependientes se listan en `antes`).

*Alternativas:* (b) solo convertir el 500 en 409 sin baja lógica: no hay forma de retirar un tratamiento con historia del catálogo público; (c) borrado en cascada: destruye historia clínica-administrativa, descartado.

### D2. Los turnos tomados se respetan; impacto informado (O2, O3)

Ningún cambio del catálogo cancela, mueve ni modifica turnos (estado, horario, sillón, seña). Coherente con RN-TU-04 tal como ya está implementado: `fin` se fija al crear o reprogramar con la duración vigente en ese momento. Un precio nuevo solo afecta la seña de reservas nuevas (RN-SN-03); poner precio 0 vuelve exentas de seña solo a las nuevas (RN-SN-06).

Una pre-reserva `en_espera` dentro de una franja que se quita puede acreditarse después y quedar `reservado` fuera de la franja vigente: se acepta (el paciente ya eligió y está pagando; R8 no se toca) y se cuenta en el impacto.

**Consulta de impacto** `GET /api/admin/{recurso}/{id_}/impacto` → `ImpactoRead { turnos_futuros: int, primero: datetime | None }` (Pydantic, R15). Cuenta turnos con `inicio > ahora` y estado en (`en_espera`, `reservado`, `confirmado`):
- tratamiento / profesional / sillón: por FK;
- franja: turnos del profesional cuyo inicio, convertido a `APP_TZ`, cae ese `dia_semana` y en `[hora_inicio, hora_fin)`. Consulta con `extract(isodow ...)` y `::time` en la zona de la clínica (SQLAlchemy, sin SQL crudo, R14).
Sin datos de pacientes en la respuesta. Política de auditoría: **exenta**, motivo "conteo agregado sin datos de pacientes (C-14)". El panel lo pide al abrir cada diálogo de desactivar / borrar / pausar / cambiar horario; si falla, el diálogo lo dice y permite seguir (el impacto informa, no bloquea).

*Alternativas:* (b) bloquear con 409 si hay turnos futuros (obliga a reprogramar uno por uno antes de tocar un horario; recepción no podría cargar vacaciones de larga duración sin ir turno por turno); (c) cancelar automáticamente con devolución de seña (efectos en caja, WhatsApp y Google; governance más alto; fuera de alcance).

### D3. Franjas sin superposición con garantía en la base (O6)

Migración `014`: `CREATE TYPE rango_hora AS RANGE (subtype = time)` y
`EXCLUDE USING gist (profesional_id WITH =, dia_semana WITH =, rango_hora(hora_inicio, hora_fin, '[)') WITH &&) WHERE (is_active)` (`btree_gist` ya está instalado desde `001`). Rango semiabierto: 09–13 y 13–17 conviven. El servicio hace un pre-chequeo (fast-fail, para devolver la franja con la que choca) y captura la violación de exclusión (SQLSTATE `23P01`) → 409 `franja_superpuesta`. Aplica a crear, editar y reactivar.

*Alternativas:* (b) solo validación en la aplicación (carrera entre dos altas); (c) aceptarlas y deduplicar en `_slots_libres` (oculta datos inconsistentes y desfasa los pasos).

### D4. Validación combinada en la edición de franjas

El servicio de franjas, antes del `flush`, combina lo guardado con `cambios` y valida `hora_fin > hora_inicio` (y `dia_semana`) → 422 con el formato de error de validación de FastAPI (`loc: ["body", "hora_fin"]`). Además captura `IntegrityError` de `ck_disponibilidad_horas` como red de seguridad → 422. Igual criterio para FK inexistentes en `profesional_id`/`sillon_defecto_id` (hoy 500): 422 vía `ReferenceNotFoundError`, que ya tiene manejador.

### D5. Topes y unicidad (O12, O13) — `postgresql-table-design`

- Pydantic (borde, R15): `duracion_minutos` 5–480 y múltiplo de 5; `precio_base` 0–99999999.99 con 2 decimales como máximo; `nombre` sin espacios en los extremos (`strip`) antes de validar longitudes.
- Base (migración `014`): índices únicos `ux_tratamiento_nombre` sobre `lower(btrim(nombre))`, `ux_sillon_nombre` ídem, `ux_profesional_matricula` sobre `lower(btrim(matricula))`. Sin `WHERE is_active`: un nombre retirado no se reutiliza para otra cosa (se reactiva el existente), así el histórico no queda ambiguo. Violación (SQLSTATE `23505`) → 409 `duplicado` con el campo; pre-chequeo para el mensaje.
- No se agrega `CHECK` de rango de duración en la base (los datos existentes podrían no cumplirlo y la regla es de UX, no de integridad). `[SUPUESTO / ABIERTO]` el rango 5–480 en múltiplos de 5 (O12).

### D6. Migración `014_catalogo_baja_logica` (reversible, R14)

`upgrade`: (1) columnas `is_active` en `tratamiento` y `profesional` con `server_default true`; (2) **verificaciones previas** con consultas de solo lectura que, si encuentran franjas activas superpuestas o duplicados, abortan con `RuntimeError` nombrando los ids (no se corrigen datos solos); (3) tipo `rango_hora`, `EXCLUDE`, índices únicos. `downgrade`: quita en orden inverso sin perder filas. No hay FK nuevas (R6 no aplica). Los tests de migración que fijan `013` como head pasan a `014`. Antes del apply se verifica que `014` siga libre.

### D7. Opciones de la agenda y alta manual

`GET /api/panel/agenda/opciones`: `Ref`/`TratamientoRef` de profesionales y tratamientos suman `activo: bool` (aditivo; sillones ya llegan solo activos). `AltaManual.tsx` filtra activos; los filtros de `Agenda.tsx` muestran inactivos con "(inactivo)". `POST /api/public/gestion/reprogramar` también responde 422 `no_reservable` si el profesional o el tratamiento del turno están inactivos (aprobado 2026-11-14; `frontend/paciente` muestra un aviso propio). `crear_turno_manual` responde 422 `no_reservable` para tratamiento/profesional inactivo o sillón no `activo` (hoy un sillón elegido inactivo responde "sin sillón libre"; se unifica el motivo).

### D8. Reserva pública

`/tratamientos` filtra `is_active`; `/profesionales` exige profesional activo además de franja activa; `consultar_disponibilidad` y la reserva lanzan una excepción `NoReservableError(campo)` → 422 `no_reservable` (manejador nuevo junto a `referencia_handler`). `frontend/paciente`: el 422 `no_reservable` al reservar muestra "Ese tratamiento ya no se ofrece. Elegí otro." y vuelve al paso 1 conservando nombre y teléfono (cambio chico, con test unitario; sin E2E nuevo del paciente más allá del existente).

### D9. Frontend del panel (O4, O9, O10) — `vercel-react-best-practices`, `frontend-design`

- **Ruta:** `SECCIONES` suma `'catalogo'` (título "Catálogo"), fuera de `SECCIONES_ODONTOLOGA`; `pestanaDeCatalogo(hash)` → `'tratamientos' | 'profesionales' | 'sillones' | 'horarios'` (inválido → tratamientos), igual que `pestanaDeDatos`.
- **Carga (R2):** `Catalogo.tsx` pide las cuatro listas con `Promise.all` al montar (un solo estado `cargando | error | listo`), y las pestañas reciben los datos por props; después de cada escritura se actualiza solo la lista tocada (respuesta del servidor), sin recargar todo. El impacto se pide al abrir el diálogo, en paralelo con nada más.
- **Componentes** (uno por archivo, PascalCase, sin componentes definidos dentro de otros): `Catalogo` (pestañas, patrón de `Datos`), `TratamientosCatalogo`, `ProfesionalesCatalogo`, `SillonesCatalogo`, `HorariosCatalogo` (selector nativo de profesional + bloque por día lunes→domingo; formulario de franja con `<input type="time" step="300">` y `select` de sillón preferido opcional), `ConfirmarCambioCatalogo` (sobre `Dialogo`, muestra el impacto). Formularios con `useEnvio` (botón deshabilitado mientras envía: un solo pedido).
- **Cliente:** `lib/api.ts` suma `catalogo()` (las cuatro lecturas en paralelo), `crear/actualizar/borrar` por recurso e `impacto(recurso, id)`, con guardas (`esTratamientoAdmin`, …) y `ErrorApiPanel` con `motivo` (`en_uso`, `franja_superpuesta`, `duplicado`, `no_reservable`) — sin `any` (R1). `lib/catalogo.ts` con funciones puras: agrupar franjas por día, ordenar, formatear `"$ 18.500"` y "45 min", traducir errores 409/422 a mensajes por campo, validar el formulario antes de enviar (mismos topes que el backend).
- **Copia (sentence case, verbos claros):** "Agregar tratamiento", "Guardar cambios", "Desactivar" / "Reactivar", "Borrar", "Agregar franja", "Pausar franja" / "Reactivar franja", "Quitar franja"; estados "Activo"/"Inactivo", "Activa"/"Pausada", "Disponible"/"En mantenimiento"/"Fuera de uso"; notas "No se ofrece para reservar", "Sin seña", "Sin atención este día". Errores con qué pasó y cómo seguir (p. ej. "No se puede borrar porque tiene turnos registrados. Podés desactivarlo para que no se ofrezca más.").
- **360 px (R3):** listas de una columna, cada acción en un botón de ≥ 48 px en una fila propia bajo los datos (no íconos de 32 px), pestañas del catálogo con `flex-wrap` (las cuatro entran en dos filas), sin barra fija. A 1280 px las filas de la lista muestran datos y acciones en una sola línea y el editor de horarios muestra los días en dos columnas; no hay grilla semanal arrastrable (O10).
- **Pantallas de referencia (Stitch MCP, 2026-11-14):** `projects/7294293124768754545/screens/a23de3d83bf045a4898af512f50b2701` (Catálogo - Tratamientos, móvil) y `projects/7294293124768754545/screens/1f96eb576a644329a4c6e308e9b909fe` (Catálogo - Horarios de atención, móvil, con el diálogo "Quitar franja"). Evidencia, prompts textuales y lo que se adopta o descarta en `docs/skills-mcp/evidencia-stitch/c-14/README.md`. **El frontend no copia los textos ni el HTML de Stitch tal cual**: la UI real usa los tokens y componentes existentes de `frontend/panel` (`estilos.css`, `Dialogo`, `.selector`) y los textos de los specs. Se descarta lo que Stitch agregó sin pedirlo (marca, buscador, barra inferior, etiquetas en mayúsculas, id visible, "Crear prestación manual", botones de 32 px, pestañas que desbordan a 360 px).

### D10. Auditoría (RN-GL-01)

Sin cambios de mecanismo: `PUT` de `activo` queda como `UPDATE` con `antes`/`despues` y `campos` (`["is_active"]`), con IP real. Las cuatro rutas `impacto` se agregan a `_catalogo()` como exentas con motivo; el test de contrato de C-13 falla si se olvida. Los rechazos (409/422) no escriben auditoría porque no hubo acción.

### D11. Estrategia de pruebas (Strict TDD)

- **Unit (pytest):** esquemas (topes, `strip`, `activo`), validación combinada de franjas, cálculo de impacto de franja con zona horaria (navegador/servidor en UTC, clínica en `America/Argentina/Buenos_Aires`).
- **Integración (pytest + Postgres real):** 409 `en_uso` por cada FK, `EXCLUDE` con dos altas concurrentes (`asyncio.gather`), unicidad, migración `014` (upgrade/downgrade, abortos por datos inválidos), filtros de la reserva pública y del alta manual, turnos intactos tras cambios, auditoría del `PUT` de `activo`, contrato de política.
- **Frontend (Vitest + Testing Library):** `lib/catalogo.ts` puro, cliente con guardas (respuesta malformada → `ErrorDeRespuesta`), `Catalogo` con `Promise.all` (los cuatro pedidos salen antes de resolver el primero), cada pestaña con sus tres escenarios, diálogo de impacto (con turnos, sin turnos, falla), ruta y navegación por rol.
- **E2E Playwright (R7) a 360 y 1280 px:** `frontend/panel/e2e/catalogo.spec.ts` contra el stack de CI (detalle en `tasks.md` §8). En este host Windows Playwright está restringido (Riesgos de `CHANGES.md`): la evidencia verde es la de CI.

## Risks / Trade-offs

- [Datos existentes con duplicados o franjas superpuestas] → la migración aborta con los ids; tarea 0.3 los busca antes del apply con consultas de solo lectura y se corrigen a mano (decisión del usuario), nunca en silencio.
- [Turnos futuros que quedan fuera de toda franja o con un profesional inactivo] → se ven igual en la agenda; el diálogo de impacto lo advierte. El paciente de ese turno no podrá reprogramarlo online (no hay horarios: RN-TU-08 exige misma profesional); puede cancelar con 24 h o llamar. Se documenta en el README.
- [`en_espera` acreditada fuera de la franja vigente] → aceptado (D2); cuenta en el impacto.
- [El cálculo de impacto de una franja usa la zona de la clínica; un cambio de huso histórico] → se usa `APP_TZ` como en `_franjas_del_dia`; test con navegador en otra zona.
- [Indicadores de ocupación] → siguen contando franjas activas de profesionales inactivos; un profesional inactivo normalmente no tiene franjas activas. `[SUPUESTO]` aceptable en v1; si molesta, filtrar en un seguimiento.
- [Last-write-wins entre dos personas editando lo mismo] → baja frecuencia; la auditoría guarda antes/después (O11).
- [Límite de 480 minutos u otra granularidad que la clínica necesite] → O12 lo deja explícito; cambiarlo es tocar una constante y su test.
- [Ocho secciones en la navegación a 360 px] → la lista ya hace `flex-wrap`; E2E verifica que no haya scroll horizontal.

## Migration Plan

1. Verificar con `ls backend/src/alembic/versions` que `014` está libre y correr las consultas de 0.3 (duplicados, franjas superpuestas).
2. Desplegar backend con la migración (`alembic upgrade head` en el arranque del contenedor, como hoy). Los datos existentes quedan activos: no cambia nada visible para pacientes.
3. Desplegar `frontend/panel` y `frontend/paciente`.
4. Rollback: `alembic downgrade -1` (quita restricciones y columnas sin perder filas) y volver a la imagen anterior; los ítems desactivados en el ínterin vuelven a ofrecerse (se avisa en el README).

## Open Questions

- Ninguna que cambie specs o tareas: todas las decisiones están en la tabla O1–O13.

## Decisiones (O1–O13 APROBADAS (a) 2026-11-14)

| # | Prioridad | Pregunta | Opción recomendada | Alternativas | Decisión |
|---|---|---|---|---|---|
| O1 | ALTA | ¿Cómo se retira un tratamiento, profesional o sillón que ya tiene historia? | **(a)** Baja lógica: `activo` en tratamiento y profesional (migración `014`), `estado` en sillón, `activo` expuesto en franjas; inactivo = no se ofrece para turnos nuevos, sigue en agenda e históricos. `DELETE` solo sin referencias, si no 409 `en_uso` (D1) | (b) solo convertir el 500 en 409, sin baja lógica (no se puede retirar algo usado); (c) borrado en cascada (pierde historia) | **APROBADA (a) 2026-11-14** |
| O2 | ALTA | ¿Qué pasa con los turnos futuros cuando se desactiva o borra algo o se quita/acorta una franja? | **(a)** Se respetan tal cual (no se cancelan ni mueven ni se avisa); el panel muestra antes cuántos turnos futuros vigentes alcanza el cambio (`/impacto`) y deja confirmar (D2) | (b) bloquear con 409 mientras haya turnos futuros alcanzados; (c) cancelarlos automáticamente con devolución de seña y aviso | **APROBADA (a) 2026-11-14** |
| O3 | ALTA | ¿Qué pasa con los turnos existentes si cambia la duración o el precio de un tratamiento? | **(a)** Conservan inicio, fin y seña; lo nuevo vale para turnos que se crean o reprograman después (comportamiento actual, ahora explícito en el spec y avisado en la pantalla) | (b) recalcular el `fin` de los turnos futuros (puede generar solapes que la base rechaza); (c) impedir cambiar la duración si hay turnos futuros | **APROBADA (a) 2026-11-14** |
| O4 | ALTA | ¿Quién edita el catálogo? | **(a)** Recepción y admin, todo (como la matriz de `03` y el backend de C-04) | (b) recepción edita horarios y estado de sillones; precios, duraciones y borrados solo admin (menor privilegio sobre dinero; enmienda la matriz) | **APROBADA (a) 2026-11-14** |
| O5 | Media | La matriz de `03` dice que la odontóloga tiene "Lectura" de disponibilidad y tratamientos, pero la API le responde 403. ¿Qué se hace? | **(a)** Mantener el 403 y no mostrarle la sección; precisar la matriz: su lectura es la de su agenda y el catálogo público. Sin cambios de código | (b) darle lectura de `/api/admin/*` y una pestaña de solo lectura con sus horarios; (c) lectura solo de sus propias franjas | **APROBADA (a) 2026-11-14** |
| O6 | ALTA | ¿Se permiten franjas superpuestas del mismo profesional y día? | **(a)** No: 409 `franja_superpuesta` con garantía `EXCLUDE USING gist` sobre franjas activas; contiguas sí (D3) | (b) solo validación en la aplicación; (c) permitirlas y deduplicar al calcular horarios | **APROBADA (a) 2026-11-14** |
| O7 | Media | ¿Las franjas se pausan o solo se borran? | **(a)** Las dos: "Pausar" (`activo=false`, conserva la franja para reactivarla) y "Quitar" (borrado, siempre permitido porque los turnos no dependen de ella) | (b) solo borrar, como hoy; (c) solo pausar | **APROBADA (a) 2026-11-14** |
| O8 | Media | ¿Entran excepciones por fecha (vacaciones, feriados, un día cerrado)? | **(a)** No en C-14: se cubre pausando franjas; seguimiento en `CHANGES.md` §Backlog | (b) agregar `bloqueo_agenda` (profesional/sillón, rango de fechas) a C-14: tabla, reglas en el cálculo de horarios, pantallas (alcance mucho mayor) | **APROBADA (a) 2026-11-14** |
| O9 | Media | ¿Dónde vive la UI? | **(a)** Una sección "Catálogo" (`#/catalogo`) con pestañas Tratamientos / Profesionales / Sillones / Horarios, patrón de "Datos" | (b) dos secciones: "Catálogo" y "Horarios" (nueve secciones en la navegación a 360 px) | **APROBADA (a) 2026-11-14** |
| O10 | Media | ¿Cómo se edita la disponibilidad semanal? | **(a)** Lista por profesional con un bloque por día y formularios (accesible y usable a 360 px), como el prototipo de Stitch | (b) grilla semanal con arrastrar y soltar (difícil a 360 px y con teclado) | **APROBADA (a) 2026-11-14** |
| O11 | Baja | ¿Control de edición concurrente? | **(a)** No: última escritura gana; la auditoría guarda antes/después | (b) control optimista (`updated_at` / `If-Match`, 409 `editado_por_otro`): requiere columnas en tratamiento/profesional/sillón | **APROBADA (a) 2026-11-14** |
| O12 | Media | ¿Topes de duración y precio? | **(a)** Duración 5–480 min en múltiplos de 5; precio 0–99.999.999,99 (el máximo de la columna; hoy un valor mayor da 500). `[SUPUESTO / ABIERTO]` el rango de duración a confirmar con la clínica | (b) solo el máximo de la columna para precio y duración > 0 sin tope (como hoy); (c) múltiplos de 15 | **APROBADA (a) 2026-11-14** (rango de duración `[SUPUESTO]`, a confirmar con la clínica) |
| O13 | Media | ¿Nombres y matrículas únicos? | **(a)** Sí, sin distinguir mayúsculas ni espacios: nombre de tratamiento, nombre de sillón y matrícula; índices únicos en la base, 409 `duplicado` (D5). Incluye inactivos (se reactiva el existente) | (b) únicos solo entre activos; (c) sin unicidad (como hoy) | **APROBADA (a) 2026-11-14** |

## Auditoría de reglas de negocio (`spec-rules-auditor`, 2026-11-14, sobre la propuesta)

**Dictamen: OBSERVACIONES** (sin bloqueos; dos supuestos marcados y una precisión de la matriz de `03` sujeta a O5).

| Regla | Descripción breve | Estado | Observación |
|---|---|---|---|
| RN-TU-04 | Duración la fija el tratamiento | CUBIERTA | "Los cambios del catálogo no alteran turnos existentes": duración nueva solo para turnos nuevos y reprogramaciones (O3); spec `tratamientos-disponibilidad` |
| RN-TU-05 | Tabla tratamiento→duración configurable | CUBIERTA | Pantalla de tratamientos (`catalogo-panel`) + topes O12 `[SUPUESTO]` |
| RN-TU-07 | Solo se reserva sobre disponibilidad vigente | CUBIERTA | Franjas activas sin superposición (O6), pausar/quitar (O7), inactivos no reservables (reserva pública y alta manual) |
| US-008 CA-1/CA-2 | Edito sin código / horarios se recalculan | CUBIERTA | Escenarios de pantalla + E2E que consulta `/api/public/disponibilidad` tras el cambio (tasks §8) |
| RN-TU-03 / R5 | Anti-solape en la base | NO AFECTADA | Los cambios no tocan turnos; el estado del sillón solo afecta asignaciones nuevas |
| R8 / RN-SN-01 | `en_espera` no bloquea | NO AFECTADA / precisada | Una `en_espera` en una franja quitada puede acreditarse (D2); se cuenta en el impacto |
| RN-SN-03 / RN-SN-06 | Seña sobre precio base / precio 0 exento | CUBIERTA | Precio nuevo solo para reservas nuevas; aviso "Sin seña" al poner 0 |
| RN-TU-08 | Reprogramar con misma profesional y tratamiento | CUBIERTA con riesgo | Turno de profesional inactivo no se puede reprogramar online (sin horarios); documentado en Riesgos |
| RN-GL-01 | Acciones del panel auditadas | CUBIERTA | `PUT` de `activo` audita `UPDATE`; `impacto` declarada exenta con motivo (contrato C-13); rechazos sin rastro |
| Matriz RBAC (`03`) | Recepción/admin CRUD total; odontóloga lectura | CUBIERTA con precisión | Escenarios de 403 y de navegación; la "lectura" de la odontóloga se precisa en O5 |
| R1, R2, R3, R7 | TS estricto, sin cascadas, 360 px, E2E | CUBIERTA | D9, spec `catalogo-panel` (carga en paralelo, 360 px), tasks §8 |
| R4, R6, R14 | Tipos, índices de FK, migraciones reversibles | CUBIERTA | `014` sin FK nuevas, `downgrade` probado (D6) |
| R19 | Datos sintéticos | CUBIERTA | Todos los ejemplos son ficticios (`Dra. Ana Ficticia`, `MP-99001`, `@turnos.test`) |

**Gaps detectados y corregidos en los artefactos:** (1) el spec de C-04 decía "422 por CHECK" pero no cubría `precio_base` fuera de la columna (500): agregado; (2) faltaba el escenario de carrera en franjas: agregado ("Dos altas superpuestas al mismo tiempo"); (3) faltaba qué ve la reserva pública si el tratamiento se desactiva mientras el paciente elige: agregado (422 `no_reservable`, vuelve al paso 1). Supuestos abiertos: rango de duración (O12) e indicadores con franjas de inactivos (Riesgos). Cada requisito de los cinco specs tiene sus tres escenarios (esperado, error de negocio, borde).

## Auditoría final de reglas de negocio (`spec-rules-auditor`, 2026-11-14, sobre el código y los specs implementados)

**Dictamen: OBSERVACIONES** (sin bloqueos; una observación nueva para decisión del usuario).

| Regla | Estado | Verificación |
|---|---|---|
| RN-TU-04 / RN-TU-05 | CUBIERTA | Turno tomado intacto tras alargar duración/subir precio; reprogramar después usa la duración vigente (`test_catalogo_impacto_integration.py`); topes 5–480/múltiplo de 5 `[SUPUESTO]` en `schemas.py` |
| RN-TU-07 | CUBIERTA con observación | Inactivos y sillones no `activo` → 422 `no_reservable` en reserva pública y alta manual; franjas sin superposición con `EXCLUDE` en la base (carrera 201+409 probada). Ver observación O-A |
| RN-GL-01 | CUBIERTA | `PUT activo` audita `UPDATE` con antes/después e IP; rechazos 409/422 sin rastro; `impacto` exenta con motivo (contrato C-13 en verde) |
| R4/R5/R6/R14 | CUBIERTA | `014` reversible (probado), sin FK nuevas, sin SQL crudo fuera de la migración |
| R15/R13 | CUBIERTA | `ImpactoRead`, esquemas con topes, firmas tipadas |
| R19 | CUBIERTA | Solo datos sintéticos |
| R1/R2/R3 | CUBIERTA (R3 por E2E en CI) | Sin `any`, `Promise.all` en `catalogo()`, estilos a 360 px |

**Observación O-A (RESUELTA 2026-11-14, aprobada por el usuario y implementada en la tarea 5.5):** `POST /api/public/gestion/reprogramar` no rechaza un turno cuyo profesional o tratamiento fue desactivado: hoy solo lo impide que la UI no obtiene horarios (la consulta de disponibilidad responde 422). Un pedido armado a mano podría reprogramar dentro de una franja activa. Se implementó el 422 `no_reservable` también ahí (tarea 5.5, delta `turnos/gestion-paciente`).
