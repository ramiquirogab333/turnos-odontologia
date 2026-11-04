# Design: c-05-reserva-publica-horarios

## Context
Ver motivación y alcance en `proposal.md`. C-01 estableció la base de integridad relacional en PostgreSQL mediante la constraint `EXCLUDE USING gist` que previene solapamientos por profesional y por sillón. C-05 construye la superficie pública de interacción (Frontend en React + Vite y Endpoints públicos en FastAPI) bajo la regla estricta **R3** (diseño funcional y optimizado a 360px) y las directivas **R1** (TypeScript strict, sin `any`) y **R2** (sin fetches en cascada, carga paralela con `Promise.all` y `Suspense`).

Para el diseño de interfaz y la estructura de componentes visuales mobile-first se usó el **Servidor MCP de Google Stitch** (`@_davideast/stitch-mcp`). La invocación real está documentada desde el 2026-11-03: se generaron tres pantallas con `generate_screen_from_text` en el proyecto de Stitch `7294293124768754545`. La evidencia (HTML, capturas, prompts y tema devuelto) está en [`docs/skills-mcp/evidencia-stitch/`](../../../docs/skills-mcp/evidencia-stitch/README.md).

> **Corrección (2026-11-03).** Las versiones anteriores de este documento decían que los tokens se habían extraído con Stitch (`#0E7490`, `#F8FAFC`, `#16A34A`, Inter). El repositorio no conserva evidencia de esa extracción: la única invocación documentada de esa fecha es `--help` de la herramienta, que no puede producir colores ni layouts, y no quedó ningún resultado, credencial ni referencia de proyecto. El origen de aquellos valores no está verificado. Los valores reales se obtuvieron recién el 2026-11-03, cuando Stitch se conectó y se usó por primera vez, y son los de la Decisión 1.

---

## Goals / Non-Goals

**Goals:**
- Proporcionar una interfaz web pública para pacientes rápida, accesible y utilizable con una sola mano en pantallas de 360px (mobile-first).
- Consultar y calcular en tiempo real los slots de atención disponibles según la duración del tratamiento (`GET /api/public/disponibilidad`).
- Registrar la reserva sin requerir creación de cuenta ni contraseña (`POST /api/public/turnos`), solicitando exclusivamente nombre completo y teléfono/WhatsApp.
- Entregar una confirmación inmediata con el código único de gestión. El enlace directo para gestionar el turno queda diferido a **C-07**.

**Non-Goals:**
- Cobro o procesamiento de pagos/señas online (diferido explícitamente a **C-06 `sena-pagos-turno`**).
- Cancelación o reprogramación interactiva (diferido a **C-07 `cancelacion-reprogramacion-24h`**).
- Gestión interna o edición de turnos por parte de odontólogos o recepcionistas (pertenece al panel admin en **C-08**).

---

## Decisions

### Decision 1: Estructura de Pantallas y Componentes Mobile-First asistida por Google Stitch MCP
* **Decisión:** Modelar el flujo de reserva pública en un wizard lineal de 3 pasos optimizado para pulgar (thumb-zone) en viewport de 360px × 800px:
  1. *Paso 1: Selección de Tratamiento y Profesional:* Lista de tarjetas con nombre, duración en minutos y valor base orientativo, y a continuación la elección de profesional (si hay uno solo, se informa quién atiende). El profesional se elige en este paso porque `GET /api/public/disponibilidad` se consulta por profesional: así los horarios se piden recién al elegir ambos (R2) y no en cascada. Los datos salen de dos endpoints públicos de solo lectura, `GET /api/public/tratamientos` y `GET /api/public/profesionales` (este último, solo con profesionales con franja vigente y sin matrícula). Se agregaron durante el apply porque el wizard no tenía catálogo público; están en la spec. No se adoptó la opción "Cualquier profesional disponible" que propone Stitch, porque la API no la soporta.
  2. *Paso 2: Selector de Fecha y Grilla de Horarios:* Calendario semanal deslizable horizontalmente y grilla de botones de slots de 48px de alto (touch-target accesible), con slots libres, slot seleccionado y, cuando corresponde, el aviso de horario recién tomado con alternativas libres. Los slots libres se marcan con un borde izquierdo de 4px en el color de éxito `#16806B` (el `#2E7D32` anterior ya no se usa); el seleccionado lleva fondo `#0D5C75` y texto blanco. La API pública solo devuelve horarios libres, así que no hay slots "ocupados" que dibujar.
  3. *Paso 3: Identificación Básica y Confirmación:* Formulario de 2 campos (Nombre y Teléfono con prefijo internacional), resumen del turno y, tras reservar, la confirmación con el código de gestión (solo el código, sin enlace).
* **Tokens devueltos por Stitch (sistema "Clinical Clarity Dental System", proyecto `7294293124768754545`, 2026-11-03):**
  * Paleta: primario `#0D5C75` (hover `#0A4659`), secundario `#2BB69F`, texto `#1B3B48`, lienzo `#F4F7F6`, superficie `#FFFFFF`, bordes `#D8E2E1` y `#B8CBC8`, éxito `#16806B`, error `#B3261E`.
  * Tipografía: Plus Jakarta Sans, autoalojada con `@fontsource` (sin pedidos externos de fuentes).
  * Forma: botones y campos de 48px, radio base 8px, radio de tarjeta 16px; tarjeta seleccionada con borde de 2px `#0D5C75` y tinte `rgba(43,182,159,0.05)`; espaciado de 4/8px.
  * Desvíos deliberados respecto de Stitch: chips de horario de 48px (Stitch indica 40px; R3); anillo de foco `#0D5C75` en vez de `#2BB69F` (el menta da 2,35:1 sobre el lienzo, menos de 3:1); borde de campos `#70787D` (el `#B8CBC8` da 1,69:1 contra blanco); sin barra inferior fija, que tapa contenido a 360x800.
  * No adoptado por no existir en el backend o no estar respaldado: "Cualquier profesional", especialidad por tratamiento, sede y consultorio, y textos tranquilizadores (bioseguridad, "confirmación inmediata", recordatorios por SMS).
  * El detalle de contraste AA está en el comentario de cabecera de `frontend-paciente/src/estilos.css`.
* **Código de gestión:** la confirmación muestra solo el código; no hay enlace directo. El enlace para gestionar el turno queda para **C-07** (`cancelacion-reprogramacion-24h`).
* **Alternativas descartadas:** Formulario monolítico en una sola página (descartado por saturación cognitiva y scroll excesivo en móviles de 360px).

### Decision 2: Arquitectura Frontend sin Cascadas de Fetch (Regla R2)
* **Decisión:** La carga de datos iniciales (profesionales activos, catálogo de tratamientos con sus duraciones y sillones habilitados) se realiza en paralelo en la raíz del flujo mediante `Promise.all` y límites de `Suspense`. Los slots disponibles se consultan reactivamente al cambiar la fecha o el tratamiento sin bloquear la renderización.
* **Alternativas descartadas:** Encadenar el fetch de profesionales tras seleccionar tratamiento (provoca waterfall de 3 saltos de red inaceptable en conexiones móviles 3G/4G).

### Decision 3: Endpoint Público de Disponibilidad (`GET /api/public/disponibilidad`)
* **Decisión:** Implementar un algoritmo en backend que tome:
  1. La franja horaria de atención del día (ej. 09:00 a 18:00).
  2. La duración del tratamiento solicitado ($D$ minutos).
  3. Los turnos ya existentes que bloquean agenda en ese día.
  4. Genera slots candidatos cada $D$ minutos (o intervalos fijos de 30 min) y filtra aquellos donde tanto el profesional como al menos un sillón físico estén libres.
* **Alternativas descartadas:** Calcular la disponibilidad en el cliente JavaScript (inseguro y propenso a inconsistencias por zonas horarias y concurrencia).

### Decision 4: Integridad Relacional y Manejo de Concurrencia
* **Decisión:** La reserva pública utiliza la transacción atómica de Postgres con la constraint GiST ya existente de C-01. Si dos pacientes intentan reservar exactamente el mismo slot simultáneamente, el primero obtiene `201 Created` y el segundo recibe `409 Conflict` con un mensaje claro y la sugerencia de los siguientes horarios libres disponibles.

---

## Risks / Trade-offs

- **[Riesgo: Concurrencia en horarios pico]** → *Mitigación:* Manejo explícito de HTTP 409 con respuesta enriquecida (`siguientes_horarios_disponibles`) para que el frontend reoriente al paciente sin obligarlo a empezar el flujo de cero.
- **[Riesgo: Datos de teléfono mal formateados]** → *Mitigación:* Validación estricta con Pydantic y expresión regular en backend (formato E.164: código de país + código de área + número) antes de persistir.
- **[Riesgo: Paciente abandona la reserva]** → *Mitigación:* Flujo ultra-corto (3 pasos, sin creación de contraseña), autocompletado de navegador y confirmación con un solo toque.

---

## Audit & Compliance Note (spec-rules-auditor)
Este diseño fue auditado con la skill `spec-rules-auditor`:
- Cumple con `RN-TU-03` (doble anti-solape profesional/sillón).
- Cumple con `RN-TU-04` (`fin = inicio + duracion_minutos`).
- Cumple con `RN-TU-06` (reserva pública sin registro obligatorio de usuario).
- Cumple con `RN-GL-03` y `R3` (criterio de aceptación estricto a 360px mobile-first).
- Deja preparado el punto de extensión para `C-06` (donde el turno pasará a estado `en_espera` hasta la acreditación de la seña).
