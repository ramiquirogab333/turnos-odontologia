# Decisiones y Supuestos

## Decisiones documentadas

### DD-01 — Reserva sin registro obligatorio
**Decisión**: reservar con nombre + teléfono, sin login de paciente.
**Contexto**: la mayoría reserva desde el teléfono; el login frena la conversión.
**Alternativas consideradas**: cuenta obligatoria; login social.
**Justificación**: fricción mínima, coherente con el uso actual por WhatsApp.
**Trade-offs aceptados**: gestión del turno por enlace/código en vez de cuenta; unicidad del paciente atada al teléfono.

### DD-02 — Ventana de cancelación de 24 hs
**Decisión**: no cancelar/reprogramar con menos de 24 hs de anticipación.
**Contexto**: regla de negocio explícita del consultorio (discovery §7).
**Alternativas consideradas**: ventana mayor/menor o por tratamiento.
**Justificación**: protege la ocupación de la agenda.
**Trade-offs aceptados**: rigidez ante urgencias; requiere mensaje claro de rechazo.

### DD-03 — Duraciones configurables por tratamiento
**Decisión**: tabla tratamiento→duración editable por admin, no fija en código.
**Contexto**: cada tratamiento dura distinto y puede cambiar.
**Alternativas consideradas**: duración fija global; duración fija por especialidad.
**Justificación**: flexibilidad sin despliegues.
**Trade-offs aceptados**: el admin debe mantener la tabla actualizada.

### DD-04 — Mobile-first
**Decisión**: el diseño prioriza el celular.
**Contexto**: sin restricciones de stack/plataforma; la mayoría reserva desde el teléfono.
**Alternativas consideradas**: desktop-first; app nativa desde v1.
**Justificación**: cubre al paciente con web responsive sin costo de app nativa.
**Trade-offs aceptados**: app dedicada queda para después de v1.

### DD-05 — Google Calendar como calendario espejo
**Decisión**: sincronía bidireccional con Google Calendar.
**Contexto**: hoy es el sistema principal en uso.
**Alternativas consideradas**: reemplazar GCal por agenda propia única.
**Justificación**: adopción sin fricción para el profesional.
**Trade-offs aceptados**: complejidad de conflictos de sincronía (RN-GC-02 pendiente).

### DD-06 — Alcance clínico-administrativo mínimo en v1
**Decisión**: odontograma FDI básico + presupuestos con OS + nomenclador precargado; MP + transferencia; sin ARCA nativa.
**Contexto**: discovery §5 (necesarias) vs. §6 (opcionales).
**Alternativas consideradas**: v1 solo turnos; v1 con facturación ARCA completa.
**Justificación**: cubre operación diaria sin el costo de facturación electrónica nativa.
**Trade-offs aceptados**: facturación completa queda fuera de v1.

### DD-07 — Política de la seña (C-06, decisión del Product Owner 2026-11-06)
**Decisión**: se aprueban los defaults de C-06 con un cambio en la cancelación:
- Vencimiento de `en_espera`: 30 min con Mercado Pago y 24 h con transferencia, nunca después del inicio del turno; editable por el admin (RN-SN-07).
- Cancelación con 24 h o más: la seña se devuelve (`a_reembolsar`, devolución manual). El ausente no se reembolsa (RN-SN-04, RN-SN-02).
- Pago aprobado tardío u horario ganado por otro: `a_reembolsar`, y el turno no revive (RN-SN-05).
- Precio base 0: exento de seña, nace `reservado` (RN-SN-06).
- Seña inicial: 30% del precio base (RN-SN-03).
- Transferencia: acreditación manual de recepción/admin por la API (la UI llega en C-12), con alias, CBU y un código de referencia del turno en el concepto (RN-SN-08).
- Se reescriben los tests y E2E de C-05 dentro de C-06.
- El barrido de vencimiento es una tarea asyncio del lifespan, cada 60 s y sin Redis; C-09 lo consolida.

**Contexto**: el diseño de C-06 (`openspec/changes/c-06-sena-pagos-turno/design.md`, §Decisiones aprobadas, P1 a P8) dejó estas decisiones para el usuario por la governance CRÍTICA de pagos.
**Alternativas consideradas**: seña no reembolsable también al cancelar (era el default original de `CHANGES.md`); revivir el turno ante un pago tardío; rechazar la reserva de tratamientos sin precio; Redis + worker para el vencimiento.
**Justificación**: devolver la seña cuando se avisa con tiempo es más justo para el paciente y deja el castigo solo para el ausentismo. La devolución manual evita automatizar reembolsos en v1.
**Trade-offs aceptados**: los reembolsos son manuales (`a_reembolsar` visible en caja desde C-12); `a_reembolsar` agrega un estado que la KB original no tenía.

### DD-08 — Gestión del turno por el paciente (C-07, decisión del Product Owner 2026-11-06)
**Decisión**: se aprueban los defaults O1 a O10 de `openspec/changes/c-07-cancelacion-reprogramacion-24h/design.md`.
- O1: el código de gestión viaja en la cabecera `X-Codigo-Gestion` sobre `/api/public/gestion/*` (no en la ruta como decía `CHANGES.md`), para que no quede en logs ni en el `Referer`. El enlace del paciente es `/gestionar#<código>` (el fragmento no llega al servidor).
- O8: la entrega de eventos a Google Calendar y recordatorios usa el puerto `NotificadorTurnos` post-commit más la auditoría transaccional como fuente reconciliable; sin tabla outbox ni migración (C-09 puede sumarla junto con Redis).
- Reglas de negocio derivadas (O2 a O7, O10): RN-TU-08 a RN-TU-11 en `05_reglas_de_negocio.md`. IN-02 queda resuelta.
- O9: el borde exacto de 24 h se prueba en integración con reloj inyectado; el E2E usa márgenes de 5 min (sin reloj manipulable por entorno).

**Contexto**: cancelar y reprogramar por el paciente necesitaba definir credencial, alcance del cambio y semántica de la ventana.
**Alternativas consideradas**: código en la ruta; reprogramar `en_espera`; límite de reprogramaciones; outbox; reloj falso del backend para E2E.
**Justificación**: mínima superficie de ataque y de infraestructura; la base sigue siendo la garantía del anti-solape (R5).
**Trade-offs aceptados**: quien tenga el código puede gestionar el turno (rate limiting llega con Redis en C-09); un evento puede perderse entre el commit y la publicación (se reconcilia desde la auditoría).

### DD-09 — Agenda del profesional y panel (C-08, decisiones del Product Owner 2026-11-09)
**Decisión**: se aprueban las decisiones O1 a O19 de `openspec/changes/archive/2026-11-10-c-08-agenda-profesional-panel/design.md`. Las que cambian reglas o contratos:
- O1/O2 (críticas): pantalla de ingreso mínima en `frontend-panel/` y refresh token **solo en cookie `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/api/auth`**; el access vive en memoria. `POST /api/auth/refresh` lee solo la cookie y exige la cabecera `X-Panel-Csrf: 1` (defensa CSRF, junto con SameSite=Strict). El refresh ya no viaja en el JSON de login ni de refresh. El logout revoca el `jti` del access y el del refresh hasta que el refresh pueda vencer (antes solo 15 minutos).
- O3 (crítica): `POST /api/turnos` exige rol `recepcion` o `admin`.
- O4 (crítica): los usuarios del panel se crean con el comando idempotente `python -m app.panel.usuarios` (contraseña por `PANEL_USUARIO_PASSWORD`).
- O5/O6 (críticas): la odontóloga es de solo lectura y no recibe el teléfono del paciente (minimización, Ley 25.326).
- O7 (crítica): el alta manual nace `reservado` sin seña (excepción a R8 / RN-SN-01).
- O8/O10/O11: el alta manual guarda nombre y teléfono como contacto del turno (sin `Paciente`), con `turno.origen` (migración 007) y un código de gestión que se muestra una sola vez.
- O12/O13: recepción cancela con la misma ventana de 24 h; reprogramar desde el panel queda fuera.
- O14 (crítica): RN-TU-12 (momento de marcar atendido y ausente, tolerancia configurable).
- O15/O16: igual que C-06 para eventos; las pre-reservas van en una banda aparte y los cancelados no se muestran.
- O17: el resto del endurecimiento de C-03 (rate limiting, blacklist en `get_current_user`, `is_active`, roles frescos, límite absoluto de sesión) pasa a **C-15** antes de producción; la UI de catálogo y disponibilidad pasa a **C-14**.
- O19: `atendido` ocupa la agenda hasta su `fin` (la migración 007 amplía los EXCLUDE; RN-TU-03).

**Contexto**: la agenda y las acciones de recepción necesitaban un panel autenticado, y el panel obligó a cerrar huecos de auth y a definir cuándo se puede marcar un turno.
**Alternativas consideradas**: refresh en `localStorage` o en el body; panel sin pantalla de ingreso; que `atendido` libere el horario; tolerancia en una tabla de configuración; reutilizar `create_turno` de C-01 para el alta manual.
**Justificación**: el refresh fuera de JavaScript reduce el daño de un XSS; una sola definición de "ocupa" en base y aplicación evita dobles reservas con una persona sentada en el sillón; el alta manual comparte helpers y locks con la reserva pública (R5).
**Trade-offs aceptados**: sesión deslizante de 7 días (límite absoluto en C-15); un usuario desactivado conserva sus permisos hasta renovar (C-15); `atendido` marcado por error no se deshace en C-08 (seguimiento en C-12); la 007 bloquea el despliegue si hay turnos superpuestos con un `atendido` (lista los ids).

### DD-10 — Ficha, odontograma, presupuestos y acceso clínico (C-11, decisiones del usuario 2026-11-10)
**Decisión**: se aprueban las decisiones O1 a O16 de `openspec/changes/archive/2026-11-10-c-11-ficha-odontograma-presupuestos-os/design.md`. Las que cambian reglas o contratos:
- O2/O3/O4 (**cambiadas respecto de la recomendada**): "sus pacientes" de una odontóloga son los que tienen al menos un turno `atendido` con su profesional; ve DNI y número de afiliado (nunca teléfono, email ni pagos); escribe ficha y odontograma y lee presupuestos. **O4 reemplaza la matriz RBAC de `03_actores_y_roles.md` y US-009** (que la daban de solo lectura y ponían el odontograma en recepción/admin).
- O15 (crítica, **modifica C-08 O5**): la odontóloga marca `atendido` sus propios turnos; opción (a) confirmada: no marca `ausente` (retiene la seña, R9) y no deshace un `atendido` (corregirlo queda como seguimiento de C-12).
- O16 (crítica): la escritura clínica de la odontóloga exige un `atendido` en los últimos 12 meses o un turno pendiente; "12 meses" se fija en **365 días exactos** (`VENTANA_ACCESO_CLINICO`), confirmado por el usuario; fuera de la ventana solo lee (403 `acceso_clinico_vencido`).
- O1: alta/consulta/edición mínima de pacientes (búsqueda exacta por DNI) y `PUT /turnos/{id}/paciente` para vincular turnos; C-12 conserva el listado y la búsqueda libre.
- O5-O8, O12-O14: auditoría de lecturas y escrituras sin contenido clínico; ficha con `version`/409; odontograma solo de alta; pagos de presupuesto en C-11 (manuales, con tope, referencia única y anulación sin borrado); solo API (la UI es **C-16**).
- O9-O11: fórmula de cobertura half-up por línea; estados del presupuesto con congelamiento al presentar; obra social del paciente por defecto.
- **[SUPUESTO] semántica de `arancel_diferencial` (O9)**: la KB no lo define; se interpreta como copago por unidad a cargo del paciente (suma al "a cargo"). El seed lo deja en 0 y un test fija la fórmula para que cualquier cambio sea explícito.

**Contexto**: la ficha y los presupuestos necesitaban un paciente al cual pertenecer, y la odontóloga necesitaba acceso clínico real y no solo lectura.
**Alternativas consideradas**: acceso permanente de la odontóloga sin ventana; ventana que vence también la lectura; que la odontóloga marque también `ausente` o deshaga un `atendido`; UI dentro de C-11.
**Justificación**: minimización de datos de salud (Ley 25.326) con auditoría de cada acceso; el acceso se gana al atender, no al agendar.
**Trade-offs aceptados**: la ventana se mide sobre `turno.inicio` (un turno marcado tarde cuenta desde su inicio); una odontóloga podría darse acceso marcando `atendido` un turno propio de alguien que no vino (mitigado: solo turnos propios, auditado, estado final y requiere el vínculo de recepción); un GET escribe auditoría.

## Supuestos inferidos

### SU-01 — El PDF equivale a los .md
**Supuesto**: `docs/discovery/informe-discovery.pdf` contiene lo mismo que `docs/discovery/informe-discovery.md` ya ingerido.
**Origen**: mismo nombre y tamaño similar; el PDF no pudo parsearse (ver `10_preguntas_abiertas.md`).
**Riesgo si es falso**: pérdida de contenido exclusivo del PDF.
**Cómo validar**: revisión manual del PDF contra esta KB.

### SU-02 — Un consultorio/clínica chica, una sede
**Supuesto**: despliegue para una sola sede; multi-sucursal fuera de v1.
**Origen**: "consultorio/clínica chica AR"; multi-sucursal listado como opcional.
**Riesgo si es falso**: modelo de datos sin sede desde el inicio cuesta migrar.
**Cómo validar**: confirmar con el decisor (ver `10_preguntas_abiertas.md`).

### SU-03 — Anti-solape también por sillón
**Supuesto**: el control anti-solape cubre profesional y sillón (ocupación por sillón aparece en casos de uso).
**Origen**: state.discovery (ocupación por sillón) + discovery §5 (agenda multi-profesional + sillones con anti-solape).
**Riesgo si es falso**: sobredimensionar la lógica de disponibilidad.
**Cómo validar**: confirmar si v1 controla sillones o solo profesionales.

### SU-04 — Adopción de reserva online por el paciente
**Supuesto**: los pacientes usarán la reserva online en vez de WhatsApp por costumbre.
**Origen**: riesgo declarado en discovery §10 (supuesto sin probar).
**Riesgo si es falso**: baja adopción; el canal WhatsApp sigue siendo la vía real.
**Cómo validar**: piloto con pacientes reales midiendo % de reservas online vs. WhatsApp.
