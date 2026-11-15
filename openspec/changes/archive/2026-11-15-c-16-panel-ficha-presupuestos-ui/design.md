# Design: c-16-panel-ficha-presupuestos-ui

> Governance **MEDIO** (datos de salud y cobros: se respeta el alcance por rol de C-11 sin ampliarlo). Se implementa con checkpoints. Las decisiones no obvias están en la tabla **O1–O15** al final, cada una con opciones y una recomendada. **Todas APROBADAS el 2026-11-14 con la opción (a); los specs y `tasks.md` siguen la opción recomendada (a) y se ajustan primero si alguna cambia (tarea 0.1).

## Context

Motivación en `proposal.md`. Estado relevado en el código (HEAD `29638c0`, última migración `014_catalogo_baja_logica`, ningún change activo):

**API disponible (C-11, C-12; verificada en `app/pacientes/router.py` y `app/clinica/router.py`):**

| Ruta (`/api/panel`) | Recepción/admin | Odontóloga (sus pacientes) | Esquema de salida |
|---|---|---|---|
| `POST /pacientes`, `GET /pacientes?dni=`, `GET /pacientes/listado`, `PUT /pacientes/{id}` | sí | 403 | `PacienteOut`, `ListadoOut` |
| `GET /pacientes/{id}` | completo | vista clínica (sin teléfono ni email) | `PacienteOut \| PacienteVistaClinicaOut` |
| `PUT /turnos/{id}/paciente` | sí | 403 | `VinculoTurnoOut` (reemplazable, sin desvincular) |
| `GET/PUT /pacientes/{id}/ficha` | lee y escribe | lee; escribe con acceso completo | `FichaOut` (`version`, `historia`) |
| `GET …/odontograma`, `GET …/odontograma/historial`, `POST …/odontograma` | lee y escribe | ídem | vigente por pieza (`estado_pieza`, `caras`), historial con cursor `antes_de_id` (1–200, def. 50), lote 1–64 |
| `GET …/presupuestos[/{pid}]` | `PresupuestoOut` (con pagos, saldo) | `PresupuestoVistaClinicaOut` | — |
| `POST/PUT …/presupuestos`, `POST …/{presentar,aceptar,rechazar,anular}` | sí | 403 | `PresupuestoOut` |
| `GET/POST …/pagos`, `POST …/pagos/{id}/anular` | sí | 403 | `PagosPresupuestoOut`, `PagoRegistradoOut` |

Errores con `ErrorPanelBody` (`detail`, `motivo`): `paciente_ajeno`, `acceso_clinico_vencido`, `dni_duplicado`, `obra_social_inactiva`, `version_desactualizada`, `presupuesto_no_editable`, `transicion_invalida`, `presupuesto_con_pagos`, `presupuesto_no_aceptado`, `monto_excede_saldo` (con `saldo`), `referencia_duplicada`, `caja_cerrada` (C-12, RN-CJ-03). Toda lectura aceptada de datos de pacientes o de salud se audita (RN-CL-03, C-13); un 404/403 no deja rastro.

**Huecos que impiden construir las pantallas** (detalle en `proposal.md`): `TurnoAgenda` no trae `paciente_id` (`paciente_nombre` es `turno.contacto_nombre`); `AlcancePaciente.nivel` no se expone en ninguna respuesta; no existe endpoint de obras sociales (solo el seed: OSDE, Swiss Medical, Galicia Salud, Omint y **"Particular"** como obra social al 0 %, que convive con `obra_social_id = null` = particular → O5).

**Panel (`frontend/panel`):** navegación por hash (`lib/ruta.ts`: 8 secciones; la odontóloga ve `agenda` y `google-calendar`), patrón de pestañas por `?pestana=` (`Datos`, `Catalogo`), carga con `iniciar()` + `use()` + `Suspense` + `ErrorBoundary` (`Pacientes.tsx`), `Dialogo.tsx`, `useEnvio.ts` (envío único con estado), cliente `lib/api.ts` con guardas (`guardas.ts`) que ignoran campos desconocidos, `ErrorApiPanel` con `motivo`, `lib/formato.ts` (montos), `lib/tiempo.ts` (hora de la clínica). `Pacientes.tsx` lista y busca (C-12) pero sin alta ni detalle, y su texto vacío dice "Se cargan al dar de alta un turno" (incorrecto: el alta manual no crea `Paciente`). E2E con `e2e/datos.ts` (siembra por SQL: `sembrarPaciente`, `sembrarPresupuestoAceptado`, `sembrarTurno`) y `ayudas.ts` (`verificarPantalla`, `verificarSinScrollHorizontal`, `verificarObjetivosTactiles`), proyectos `chromium-360` y `chromium-1280`, navegador en `Asia/Tokyo`.

## Goals / Non-Goals

**Goals:**
- Que la odontóloga escriba ficha y odontograma de sus pacientes desde el celular, y que recepción arme presupuestos y registre cobros, sin usar la API a mano.
- Que el vínculo turno ↔ paciente sea una acción de la agenda de un minuto, para que el ausentismo por paciente y el acceso clínico empiecen a funcionar.
- La UI nunca amplía el alcance de C-11: muestra lo que el servidor entrega para el rol, y el servidor sigue siendo la única barrera.
- Ningún dato clínico sale del navegador fuera de la API: nada en `localStorage`/`sessionStorage`, nada en la URL salvo ids.

**Non-Goals:**
- Cambiar reglas, permisos o auditoría de C-11/C-12 (solo se agregan tres datos de lectura).
- Listado propio de pacientes de la odontóloga (O1 b), desvincular turnos, control optimista de datos administrativos (O13), impresión/PDF de presupuestos, devolución de cobros (backlog C-12 O2), imágenes o adjuntos clínicos, editar obras sociales o nomenclador.

## Decisions

### D1. Backend mínimo y aditivo (O2, O3, O4) — R13, R14, R15

Sin migraciones. Tres cambios de lectura, cada uno con su esquema Pydantic y tests de integración:
- **`paciente_id: int | None` en `TurnoAgenda`** (`app/panel/schemas.py`, `consultar_agenda`): se toma de `turno.paciente_id`, ya cargado. No suma joins ni datos personales; el aislamiento por rol de la agenda no cambia.
- **`acceso_clinico: AccesoClinicoOut` (`nivel`, `puede_escribir`) en `PacienteOut` y `PacienteVistaClinicaOut`**: el router ya calcula `alcance_paciente` antes de responder; se mapea `nivel` y `escribe_clinica`. Una sola fuente de verdad (la misma función que decide las escrituras), así la UI no reimplementa RN-CL-04. Se agrega a las dos clases (no un `exclude` dinámico, criterio de C-11 D2). `POST`/`PUT /pacientes` devuelven `PacienteOut` y también lo llevan (`total`).
- **`GET /api/panel/obras-sociales`** → `list[Ref]` activas ordenadas por nombre, `require_recepcion_o_admin`, en `app/pacientes/router.py` (es dato del alta del paciente; el presupuesto lo reutiliza). Consulta ORM (R14). En `app/plataforma/politica_auditoria.py` como **exenta** con motivo "catálogo de obras sociales sin datos de pacientes (C-16)"; el test de contrato de C-13 falla si se olvida.

*Alternativas:* (b) que la UI deduzca el acceso del 403 `acceso_clinico_vencido` (la odontóloga escribe y se entera al guardar); (c) una ruta propia `GET /pacientes/{id}/acceso` (un pedido más, otra lectura a auditar o exentar).

### D2. Rutas y navegación (O1, O6)

- `lib/ruta.ts` suma `leerDetallePaciente(hash) → { pacienteId: number, pestana: PestanaPaciente } | null` para `#/pacientes/{id}` (id entero positivo) y `pestanaDePaciente` (`ficha | odontograma | presupuestos | datos`, inválida → `ficha`). `leerSeccion` sigue devolviendo `pacientes` para esa ruta (la navegación marca Pacientes).
- `App.tsx/Secciones`: si hay detalle de paciente, se muestra `DetallePaciente` en lugar de la lista. **La odontóloga puede abrir el detalle aunque `pacientes` no esté en `SECCIONES_ODONTOLOGA`** (su navegación no cambia); la pestaña `datos` se ignora para ella (abre `ficha`). Quién puede ver qué lo decide el servidor (403/404 → mensajes de los specs).
- Entradas: fila del listado (recepción/admin), "Ver ficha" en `TarjetaTurno` cuando `paciente_id !== null` (todos los roles), "Nuevo paciente" en la sección Pacientes, y el alta dentro del diálogo de vínculo.
- "Volver" usa `history.back()` cuando se llegó desde el panel y si no, `#/pacientes` (recepción) o `#/agenda` (odontóloga).

### D3. Carga sin cascadas y auditoría (O7) — R2, `vercel-react-best-practices`

- Al montar `DetallePaciente` se crean **en paralelo** la promesa del paciente y la de la pestaña activa (patrón `iniciar()` del panel, una promesa por recurso, `use()` dentro de límites `Suspense` separados: la cabecera no espera a la pestaña ni al revés). Ninguna pestaña depende de la respuesta del paciente para empezar su pedido.
- Odontograma: vigente; el historial recién al elegir "Ver historial". Presupuestos: lista (ya trae líneas y, para recepción, pagos y saldo). El formulario de presupuesto pide **en paralelo** `GET /agenda/opciones` (tratamientos con `activo`) y `GET /obras-sociales` al abrirse (`Promise.all`).
- Cada pestaña se carga al abrirla por primera vez y se cachea en el estado del detalle (volver no repite el pedido; "Actualizar" lo fuerza). Así la auditoría (`lectura_ficha`, `lectura_odontograma`, `lectura_presupuesto`) refleja lo que la persona abrió, no todo el expediente.
- Después de cada escritura se reemplaza el recurso con la respuesta del servidor (ficha nueva, lote → se vuelve a pedir el vigente, presupuesto devuelto, `PagoRegistradoOut` con saldo), sin recargar la página.

### D4. Ficha (O10)

- `FichaClinica`: lectura → "Editar ficha" (si `puede_escribir`) → cuatro `textarea` con contador `n/2000` y `maxLength` → "Guardar ficha" vía `useEnvio` con la `version` leída.
- **409 `version_desactualizada`:** se vuelve a pedir la ficha; los campos muestran la versión vigente y lo que la persona escribió queda en un bloque "Lo que escribiste" (solo en memoria) con "Copiar" por campo; nunca se reintenta solo. **403 `acceso_clinico_vencido`:** mismo bloque, la pestaña pasa a solo lectura y la cabecera se actualiza.
- **Cambios sin guardar:** un hook `useCambiosPendientes` registra en el detalle si la pestaña tiene cambios; cambiar de pestaña o salir del detalle pide confirmación con `Dialogo`; `beforeunload` solo cuando hay cambios. Sin persistencia en el navegador (O9).
- Historia: tabla de una columna a 360 px (fecha/hora de la clínica con `lib/tiempo.ts`, estado como texto, profesional, tratamiento).

### D5. Odontograma (O8, O9)

- `lib/odontograma.ts` (puro, probado): catálogo FDI espejo del backend (`PIEZAS_PERMANENTES` por cuadrante 1–4 × 8, `PIEZAS_TEMPORALES` 5–8 × 5), caras `O M D V L` con nombres ("oclusal", "mesial", "distal", "vestibular", "lingual/palatina"), estados de cara/pieza y `sano`, `combinacionValida(pieza, cara, estado)` (la misma regla que `registro_valido`), `textoVigente(pieza)` y operaciones del lote (agregar con tope 64 y sin duplicados exactos, quitar). El backend sigue siendo la barrera (422).
- `GrillaPiezas`: un `fieldset` por cuadrante con botones de pieza (número + resumen de estado en texto y un símbolo; nunca solo color), de 44 × 44 px mínimo. A 360 px hay 328 px útiles (16 px de margen por lado): 8 piezas por fila darían 41 px, así que cada cuadrante permanente se muestra en **2 filas de 4** (los temporales, 5 por fila); desde 768 px, 8 por fila. Conmutador "Permanentes / Temporales". Navegación con flechas dentro del cuadrante (roving `tabIndex`).
- `LoteOdontograma`: al elegir pieza → selector de cara (solo si el estado la admite) → estado → nota opcional → "Agregar al lote". Lista del lote con "Quitar". "Registrar N hallazgos" envía un `POST` con todos (todo o nada en el servidor). Corregir = registrar un hallazgo nuevo (texto de ayuda; RN-CL-01).
- `HistorialOdontograma`: páginas de 50 con `antes_de_id`; "Cargar más" agrega sin duplicar (dedupe por `id`).

*Alternativa (O8 b):* diagrama SVG con caras cliqueables: más fiel a la ficha en papel pero con objetivos de < 20 px a 360 px y difícil con teclado.

### D6. Presupuestos y cobros (O11, O14)

- `lib/presupuestos.ts` (puro): acciones válidas por estado (`borrador`: editar, presentar, anular; `presentado`: aceptar, rechazar, anular; `aceptado`: anular, registrar cobro; finales: ninguna), textos de estado, traducción de motivos a mensajes de los specs, validación de líneas (1–50, cantidad 1–99, cara exige pieza), validación de cobro (monto > 0 y ≤ saldo, referencia ≤ 64, motivo 3–300).
- **Importes solo del servidor:** "Guardar borrador" (`POST`/`PUT`) devuelve líneas e importes calculados; el formulario muestra "Guardá el borrador para ver los importes" hasta entonces. El panel no implementa RN-PG-04 (una sola fuente de la fórmula).
- Obra social del presupuesto: el campo se **omite** para usar la del paciente (contrato de `PresupuestoCreate`), o se envía otra activa o `null` ("Sin obra social", O5). Selector de tratamientos con los activos de `/agenda/opciones`; una línea existente con tratamiento inactivo se muestra con "(inactivo)" (criterio de C-14).
- Transiciones con `Dialogo` de confirmación; presentar avisa el congelamiento (RN-PG-05). 409 `transicion_invalida`/`presupuesto_no_editable` → mensaje y recarga de la lista.
- **Cobros (O14):** dentro del presupuesto aceptado: lista de cobros (registrados y anulados con motivo), "Pagado · Saldo", formulario con medio (dos botones de selección), monto (sugerido = saldo, `inputmode="decimal"`, se envía como string decimal, R4), fecha de cobro con `input type="date"` (máximo hoy en la clínica): **hoy → se omite `fecha_cobro`** (el servidor usa su reloj); **día pasado → instante de las 12:00 de ese día en la zona de la clínica con offset explícito** (`lib/tiempo.ts`), para caer en el día de caja correcto. 409 `monto_excede_saldo` actualiza el saldo y el monto sugerido con el `saldo` del cuerpo.
- La odontóloga ve la misma lista con `PresupuestoVistaClinicaOut`: el componente recibe el tipo discriminado por la guarda (`'pagos' in p`) y no renderiza ninguna acción ni pagos.

### D7. Pacientes: alta, edición y vínculo (O12, O13)

- `lib/pacientes.ts` (puro): validación del formulario igual que `PacienteCreate` (DNI `^[0-9]{7,8}$` tras quitar puntos y espacios, teléfono E.164 con ayuda para `+549…`, email simple, longitudes), `separarContacto("Carlos Sintético") → { nombre: "Carlos", apellido: "Sintético" }` como sugerencia editable (la última palabra es el apellido), traducción de `dni_duplicado` (con búsqueda por DNI para obtener el enlace al existente) y `obra_social_inactiva`.
- `FormPaciente` (alta y edición, `PUT` reemplazo completo precargado; última escritura gana, O13). `Pacientes.tsx` suma "Nuevo paciente", filas que enlazan al detalle y corrige el texto vacío ("Todavía no hay pacientes cargados" + "Nuevo paciente").
- `VincularPaciente` (diálogo desde `AccionesTurno`/`TarjetaTurno`, solo si el usuario es recepción/admin — se decide con los roles de `me()`, y el servidor responde 403 igual): paso 1 DNI → `GET /pacientes?dni=` → paso 2a "Vincular a {nombre}" o 2b "Dar de alta y vincular" (alta precargada con DNI, teléfono de contacto y nombre separado). Si el alta funciona y el vínculo falla, el diálogo conserva el `paciente_id` creado y ofrece "Reintentar vínculo" (nunca un segundo alta). "Cambiar paciente" en un turno vinculado agrega un paso de confirmación con el aviso de acceso clínico (C-12 O9). Al terminar, la agenda se vuelve a pedir (la tarjeta muestra "Ver ficha").
- La odontóloga no ve "Vincular"/"Cambiar paciente": la acción depende del rol y no de `acciones` del servidor (el vínculo no es una transición de estado del turno).

### D8. Componentes, tipos y estilo — R1, R3, `frontend-design`

- Un componente por archivo, PascalCase, sin componentes definidos dentro de otros: `DetallePaciente`, `CabeceraPaciente`, `FichaClinica`, `Odontograma`, `GrillaPiezas`, `LoteOdontograma`, `HistorialOdontograma`, `Presupuestos`, `FormPresupuesto`, `DetallePresupuesto`, `CobrosPresupuesto`, `FormPaciente`, `VincularPaciente`. Tipos en `lib/tipos.ts`, guardas nuevas en `lib/api.ts` (`esPacienteDetalle`, `esFicha`, `esOdontogramaVigente`, `esHistorialOdontograma`, `esPresupuesto`/`esPresupuestoClinico`, `esPagos`), **sin `any`** (`tsconfig` strict, R1); montos como `string` decimal de punta a punta.
- Tono "calma clínica": tokens existentes de `estilos.css` (sin colores sueltos nuevos), una columna a 360 px, acciones de ≥ 48 px en fila propia, piezas de ≥ 44 px, foco visible, estados como texto, copy en sentence case con verbos ("Guardar ficha", "Registrar 2 hallazgos", "Guardar borrador", "Presentar", "Registrar cobro", "Vincular paciente"). Errores dicen qué pasó y cómo seguir (textos de los specs). El único momento "memorable" es la grilla de piezas; el resto, sobrio.
- **Prototipos Stitch (opcional):** no se generaron en el propose; si se usan en el apply, solo con datos sintéticos y como referencia (criterio de C-14: no se copia HTML ni textos).

### D9. Seguridad y privacidad de datos de salud

- La UI no guarda datos de pacientes en `localStorage`/`sessionStorage`/IndexedDB ni los pone en la URL (solo ids). Los borradores (ficha, lote, presupuesto) viven en memoria del componente y se descartan al cerrar sesión (el `App` ya desmonta el panel al vencer la sesión).
- Nada se oculta "por CSS": lo que el rol no puede ver no se pide o el servidor no lo envía (esquemas por rol de C-11). Los tests de componentes verifican que con `PresupuestoVistaClinicaOut` no hay texto de pagos ni botones.
- Datos 100 % sintéticos en tests, E2E y ejemplos (R19).

### D10. Estrategia de pruebas (Strict TDD)

- **Backend (pytest + PostgreSQL real):** `paciente_id` en la agenda (vinculado, `null`, corregido, aislamiento por rol); `acceso_clinico` para los cinco casos (recepción, admin, completo, lectura, límite 365 días exactos vs. + 1 s, con `reloj`) y 403 sin campo; `GET /obras-sociales` (activas ordenadas, inactiva fuera, odontóloga 403, sin token 401, lista vacía) y contrato de política de auditoría.
- **Frontend unit (Vitest):** `lib/ruta`, `lib/odontograma`, `lib/presupuestos`, `lib/pacientes`, `lib/ficha` (puros, tablas de casos); cliente de API (guardas, respuesta malformada → `ErrorDeRespuesta`, `motivo` conservado, pedidos en paralelo: los dos `GET` salen antes de resolver el primero).
- **Componentes (Testing Library):** cada requisito de los specs con sus tres escenarios, nombrados como el escenario.
- **E2E Playwright (R7) a 360 y 1280 px** contra el backend real en Docker Compose (detalle en `tasks.md` §9). Se corren en local (Playwright habilitado en este host desde 2026-11-14, ver Riesgos de `CHANGES.md`) y en CI.

## Risks / Trade-offs

- [El catálogo FDI se duplica en el frontend y puede divergir] → constante única en `lib/odontograma.ts` con test de las 52 piezas y de la tabla de combinaciones; el backend rechaza con 422 y la UI lo muestra.
- [`paciente_id` visible para la odontóloga en sus turnos] → es un id sin datos; abrirlo sigue pasando por `alcance_paciente` (403 `paciente_ajeno` en la primera visita). Aceptado en O3.
- [Dos "particular": `null` y la obra social "Particular" del seed] → O5; ambos dan cobertura 0 %. Se documenta en la KB como inconsistencia del seed.
- [Corregir un vínculo cambia el acceso clínico] → confirmación explícita (C-12 O9) y auditoría `vinculo_turno_paciente` existente.
- [Pérdida de lo escrito ante 409/403 o salida accidental] → bloque "Lo que escribiste" y confirmación de cambios pendientes; nunca persistencia local (privacidad, D9).
- [Fecha de cobro de un día pasado a las 12:00] → cae siempre en el día de caja elegido; la hora exacta del cobro no se conoce de todos modos. `[SUPUESTO]` dentro de O14.
- [Tamaño del change: 4 capacidades de UI] → grupos de tareas independientes por pantalla, cada uno con sus tests; si hace falta, presupuestos/cobros (grupos 7–8) pueden pasar a un change propio sin tocar el resto.
- [Rendimiento con historiales largos] → historial paginado (50) y lista de presupuestos sin paginar (volumen bajo por paciente) `[SUPUESTO]`.

## Migration Plan

1. Sin migraciones. Desplegar el backend (campos aditivos y ruta nueva): los clientes actuales ignoran los campos nuevos.
2. Desplegar `frontend/panel`.
3. Rollback: volver a las imágenes anteriores; no hay datos que revertir (las escrituras usan la API existente de C-11/C-12).

## Open Questions

- Ninguna que cambie specs o tareas fuera de la tabla O1–O15.

## Decisiones (O1–O15) — APROBADAS por el usuario el 2026-11-14 (opción recomendada (a) en todas)

Criticidad ALTA = datos de salud, acceso o dinero.

| # | Prioridad | Pregunta | Opción recomendada | Alternativas | Decisión |
|---|---|---|---|---|---|
| O1 | ALTA | ¿Cómo llega la odontóloga a la ficha de sus pacientes, si no tiene listado (C-12)? | **(a)** "Ver ficha" en sus turnos vinculados de la agenda y ruta directa `#/pacientes/{id}`; su navegación no cambia. Un listado propio queda como seguimiento | (b) endpoint y pantalla "Mis pacientes" (sus pacientes con nivel de acceso; consulta nueva y lectura auditada); (c) darle el listado general (contradice C-12 O7/O9 y RN-CL-02) | APROBADA 2026-11-14 (a) |
| O2 | ALTA | ¿Cómo sabe la UI si la odontóloga puede escribir (RN-CL-04)? | **(a)** `acceso_clinico` (`nivel`, `puede_escribir`) en `GET /pacientes/{id}`, calculado por `alcance_paciente` (D1); el 403 `acceso_clinico_vencido` se maneja igual como red | (b) sin cambio de API: la UI se entera al guardar; (c) ruta propia `GET /pacientes/{id}/acceso` | APROBADA 2026-11-14 (a) |
| O3 | Media | ¿Se expone `paciente_id` en la agenda y a quién? | **(a)** A todos los roles del panel, solo el id (sin datos nuevos) | (b) solo a recepción/admin (la odontóloga no tendría "Ver ficha", incompatible con O1 a) | APROBADA 2026-11-14 (a) |
| O4 | Media | ¿De dónde salen las obras sociales para el alta y el presupuesto? | **(a)** `GET /api/panel/obras-sociales` (activas, id y nombre; recepción y admin; exenta de auditoría con motivo) | (b) sumarlas a `/agenda/opciones` (las recibiría también la odontóloga); (c) lista fija en el frontend (se desactualiza) | APROBADA 2026-11-14 (a) |
| O5 | Media | El seed tiene una obra social "Particular" (0 %) y además `null` significa particular. ¿Cómo se muestra? | **(a)** `null` se muestra como "Sin obra social"; "Particular" del seed aparece como una obra social más (mismo resultado: 0 %). Se registra la inconsistencia en la KB para que la clínica decida | (b) la UI oculta el código `PARTICULAR` y lo trata como `null` (acopla la UI al seed); (c) desactivar la fila del seed (los pacientes que la tengan recibirían 422 `obra_social_inactiva` al editarse) | APROBADA 2026-11-14 (a) |
| O6 | Media | ¿Dónde vive la UI clínica? | **(a)** Detalle del paciente `#/pacientes/{id}?pestana=ficha\|odontograma\|presupuestos\|datos`, patrón de pestañas de Datos/Catálogo; sin secciones nuevas en la navegación | (b) secciones "Ficha" y "Presupuestos" en la navegación (diez secciones a 360 px y sin contexto de paciente) | APROBADA 2026-11-14 (a) |
| O7 | Media | ¿Qué se carga al abrir el detalle? | **(a)** Paciente y pestaña activa en paralelo; las demás al abrirlas, cacheadas (D3): la auditoría refleja lo que se miró | (b) todo en paralelo al abrir (cambio de pestaña instantáneo, pero registra lecturas de salud que nadie vio) | APROBADA 2026-11-14 (a) |
| O8 | Media | ¿Cómo se representa el odontograma a 360 px? | **(a)** Grilla accesible por cuadrante con número FDI y estado en texto, conmutador permanentes/temporales, registro en lote con formulario (D5) | (b) diagrama SVG con caras cliqueables (objetivos chicos, difícil con teclado) | APROBADA 2026-11-14 (a) |
| O9 | ALTA | ¿Se guardan borradores (ficha, lote, presupuesto) en el navegador? | **(a)** No: solo en memoria, con confirmación al salir con cambios; nada clínico en `localStorage`/`sessionStorage` (Ley 25.326) | (b) `sessionStorage` para sobrevivir a una recarga (deja datos de salud en un dispositivo compartido) | APROBADA 2026-11-14 (a) |
| O10 | Media | Ficha con 409 `version_desactualizada` | **(a)** Mostrar la versión vigente y lo escrito aparte ("Lo que escribiste", con copiar); la persona decide | (b) mezcla automática por campo (puede combinar textos clínicos contradictorios); (c) descartar lo escrito | APROBADA 2026-11-14 (a) |
| O11 | Media | ¿El panel calcula los importes del presupuesto antes de guardar? | **(a)** No: los muestra el servidor al guardar el borrador (RN-PG-04 en una sola fuente) | (b) vista previa en el cliente duplicando la fórmula y el nomenclador (requiere exponer porcentajes) | APROBADA 2026-11-14 (a) |
| O12 | ALTA | ¿Cómo se vincula un turno con su paciente? | **(a)** Desde la tarjeta del turno en la agenda: DNI exacto → vincular, o alta precargada y vincular; "Cambiar paciente" con confirmación por el acceso clínico (D7) | (b) desde el detalle del paciente eligiendo entre turnos sin vincular (requiere un endpoint nuevo de turnos sin vínculo); (c) ambos | APROBADA 2026-11-14 (a) |
| O13 | Baja | ¿Control de concurrencia en los datos administrativos del paciente? | **(a)** No: última escritura gana (auditada con `edicion_paciente`), como C-14 O11 | (b) versión optimista (migración y 409 nuevos) | APROBADA 2026-11-14 (a) |
| O14 | ALTA | ¿Cómo se registran los cobros de presupuesto en la UI? | **(a)** En el presupuesto aceptado; fecha de cobro hoy por defecto (se omite y usa el reloj del servidor) o un día pasado (12:00 hora de la clínica), nunca futura; 409 `caja_cerrada` explicado (D6) `[SUPUESTO]` las 12:00 | (b) solo cobros de hoy (sin selector de fecha); (c) cobros desde la sección Caja (sin contexto del presupuesto) | APROBADA 2026-11-14 (a) |
| O15 | Baja | ¿Qué cubren los E2E? | **(a)** Cuatro flujos a 360 y 1280 px: ficha (con 409), odontograma en lote, presupuesto completo con cobro, y vínculo turno ↔ paciente con "Ver ficha" de la odontóloga | (b) solo los dos que exige R7 (ficha y odontograma) | APROBADA 2026-11-14 (a) |

## Auditoría de reglas de negocio (`spec-rules-auditor`, 2026-11-14, sobre proposal, design y specs)

**Dictamen: OBSERVACIONES** (sin bloqueos; dos supuestos marcados y una inconsistencia del seed sujeta a O5).

| Regla | Descripción breve | Estado | Observación / verificación |
|---|---|---|---|
| RN-CL-01 | El odontograma solo crece | CUBIERTA | `odontograma-panel` "El registro es solo de alta": sin editar ni borrar; corregir = hallazgo nuevo |
| RN-CL-02 | "Sus pacientes" = `atendido` con su profesional; ve DNI/afiliado, nunca contacto ni pagos; no escribe datos administrativos, vínculos, presupuestos ni pagos | CUBIERTA | `pacientes-panel` (paciente ajena, cabecera sin contacto, sin pestaña Datos, sin "Vincular"), `presupuestos-panel` (sin pagos ni acciones), "Primera visita todavía sin atender" |
| RN-CL-03 | Lecturas y escrituras de salud auditadas sin contenido | CUBIERTA / NO AFECTADA | Sin rutas clínicas nuevas; D3 evita lecturas no pedidas (O7); `obras-sociales` exenta con motivo (contrato C-13) |
| RN-CL-04 | Ventana de 365 días o turno pendiente; si no, solo lectura | CUBIERTA | `acceso_clinico` desde `alcance_paciente` (límite exacto y + 1 s en `registro-paciente`), solo lectura en ficha y odontograma, 403 durante la edición |
| RN-PG-02 / RN-PG-04 | Cobertura por nomenclador y fórmula por línea | CUBIERTA | Importes solo del servidor (O11); escenario Swiss 90 % sobre $ 25.000 → $ 2.500; línea sin nomenclador → "Sin cobertura" |
| RN-PG-03 | Sin ARCA | NO AFECTADA | La UI no ofrece facturar |
| RN-PG-05 | Estados y congelamiento al presentar | CUBIERTA | Acciones por estado, aviso de congelamiento, `presupuesto_no_editable`, `presupuesto_con_pagos`, `transicion_invalida` concurrente |
| RN-PG-06 / RN-CJ-03 | Cobros solo en aceptados, tope, referencia única, anulación sin borrado, caja cerrada | CUBIERTA | `presupuestos-panel` cobros y anulación (`monto_excede_saldo` con saldo, `referencia_duplicada`, `caja_cerrada`, motivo 3–300) |
| RN-TU-12 / C-12 O9 | Marcado `atendido` y efecto de corregir vínculos sobre el acceso | CUBIERTA | Confirmación de "Cambiar paciente"; la primera visita da acceso al marcar `atendido` |
| RN-GL-01 | Acciones del panel auditadas | CUBIERTA | Escrituras por la API existente (ya auditadas); ruta nueva exenta declarada |
| R1, R2, R3, R7 | TS estricto, sin cascadas, 360 px, E2E | CUBIERTA | D3, D8, requisitos de 360 px por pantalla, tasks §9 |
| R13–R15 | Backend tipado, ORM, Pydantic | CUBIERTA | D1: `AccesoClinicoOut`, `Ref` de obras sociales, `paciente_id` en `TurnoAgenda`; sin SQL crudo ni migración |
| R19 | Datos sintéticos | CUBIERTA | "Lucía Ejemplo", "Mateo Prueba", "Carlos Sintético", DNI 990000xx, `+54911000000xx`, textos "(sintético)" |
| Ley 25.326 | Datos de salud | CUBIERTA | D9 y O9: nada clínico en el navegador ni en la URL |

**Gaps detectados y corregidos en los artefactos:** (1) faltaba el caso de alta creada con vínculo fallido (duplicaría pacientes al reintentar): agregado "El alta se crea pero el vínculo falla"; (2) el spec decía "Particular" para `null` y el seed tiene una obra social con ese nombre: se cambió a "Sin obra social" y se abrió O5; (3) faltaba el 409 `caja_cerrada` en la anulación de cobros: agregado; (4) faltaba el límite inclusivo de 365 días en la UI del odontograma: agregado. **Supuestos abiertos:** fecha de cobro de días pasados a las 12:00 (O14) y lista de presupuestos sin paginar (Riesgos). Cada requisito de los seis specs tiene sus tres escenarios (esperado, error de negocio, borde).

## Auditoría final del apply (revisión manual contra `05_reglas_de_negocio.md`, 2026-11-15)

**Dictamen: APROBADO con observaciones menores** (sin bloqueos). Matriz de trazabilidad: RN-CL-01 (lote solo de alta, sin editar ni borrar: `LoteOdontograma`, E2E "corrige con Sano" deja 3 registros); RN-CL-02 (vista clínica sin teléfono ni email, presupuestos sin pagos: tests de componente y E2E de la odontóloga); RN-CL-03 (rutas nuevas sin lecturas extra: contrato de C-13 en verde y `obras-sociales` exenta con motivo); RN-CL-04 (`acceso_clinico` del servidor, límite de 365 días exactos y +1 s en `test_pacientes_acceso_clinico_integration.py`); RN-PG-04 (importes solo del servidor, sin cálculo local de líneas); RN-PG-05 (acciones por estado, aviso de congelamiento, 409 explicados); RN-PG-06 y RN-CJ-03 (tope por saldo, referencia única, `caja_cerrada`, anulación con motivo y sin borrado); RN-TU-12 / C-12 O9 (confirmación al corregir un vínculo); RN-GL-01 (sin escrituras nuevas fuera de la API auditada). R1, R2 (pedidos en paralelo con test), R3 (E2E a 360 px), R7 (E2E de ficha y odontograma en verde), R13-R15, R19 y Ley 25.326 (nada en `localStorage`/`sessionStorage`, con test).
**Observaciones**: "Volver" no usa el historial; la confirmación de salida no intercepta la navegación principal; la fecha de cobro de días pasados a las 12:00 sigue como `[SUPUESTO]` (O14, registrada en la KB).
