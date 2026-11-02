# Design: c-05-reserva-publica-horarios

## Context
Ver motivación y alcance en `proposal.md`. C-01 estableció la base de integridad relacional en PostgreSQL mediante la constraint `EXCLUDE USING gist` que previene solapamientos por profesional y por sillón. C-05 construye la superficie pública de interacción (Frontend en React + Vite y Endpoints públicos en FastAPI) bajo la regla estricta **R3** (diseño funcional y optimizado a 360px) y las directivas **R1** (TypeScript strict, sin `any`) y **R2** (sin fetches en cascada, carga paralela con `Promise.all` y `Suspense`).

Para el diseño de interfaz y la estructura de componentes visuales mobile-first, se utilizó la integración con el **Servidor MCP de Google Stitch** (`@_davideast/stitch-mcp`), extrayendo el layout de pantallas responsivas y los tokens de diseño clínico.

---

## Goals / Non-Goals

**Goals:**
- Proporcionar una interfaz web pública para pacientes rápida, accesible y utilizable con una sola mano en pantallas de 360px (mobile-first).
- Consultar y calcular en tiempo real los slots de atención disponibles según la duración del tratamiento (`GET /api/public/disponibilidad`).
- Registrar la reserva sin requerir creación de cuenta ni contraseña (`POST /api/public/turnos`), solicitando exclusivamente nombre completo y teléfono/WhatsApp.
- Entregar una confirmación inmediata con código único de reserva y enlace directo para futuras gestiones.

**Non-Goals:**
- Cobro o procesamiento de pagos/señas online (diferido explícitamente a **C-06 `sena-pagos-turno`**).
- Cancelación o reprogramación interactiva (diferido a **C-07 `cancelacion-reprogramacion-24h`**).
- Gestión interna o edición de turnos por parte de odontólogos o recepcionistas (pertenece al panel admin en **C-08**).

---

## Decisions

### Decision 1: Estructura de Pantallas y Componentes Mobile-First asistida por Google Stitch MCP
* **Decisión:** Modelar el flujo de reserva pública en un wizard lineal de 3 pasos optimizado para pulgar (thumb-zone) en viewport de 360px × 800px:
  1. *Paso 1: Selección de Especialidad / Tratamiento:* Lista de tarjetas compactas con nombre, descripción corta, duración en minutos y valor base orientativo.
  2. *Paso 2: Selector de Fecha y Grilla de Horarios:* Calendario semanal deslizable horizontalmente y grilla de botones de slots de 48px de alto (touch-target accesible), diferenciando visualmente slots libres (`#2E7D32`), ocupados y no laborables.
  3. *Paso 3: Identificación Básica y Confirmación:* Formulario de 2 campos (Nombre y Teléfono con prefijo internacional) y resumen con advertencia de confirmación por WhatsApp.
* **Layout y Tokens extraídos vía Stitch MCP:**
  * Paleta: Primario Clínico `#0E7490` (Cyan 700), Fondo Limpio `#F8FAFC`, Éxito/Disponible `#16A34A`, Superficie `#FFFFFF`.
  * Tipografía: `Inter, system-ui, sans-serif` con jerarquía tipográfica legible sin zoom en 360px.
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
