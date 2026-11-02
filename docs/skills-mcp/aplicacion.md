# Informe de Aplicación: Integración de Skill Propia y Servidor MCP

> **Proyecto:** Sistema de Gestión de Turnos Odontológicos (`turnos-odontologia`)  
> **Materia:** Metodología I — Tecnicatura Universitaria en Programación (UTN)  
> **Fecha:** 2 de Noviembre de 2026  
> **Alcance:** Parte 2 — Integración, Aplicación y Revisión Crítica (máximo 2 páginas)

---

## 1. Resultados Obtenidos

Se completó con éxito la integración de la **skill propia**, el **servidor MCP** y la preparación del change pendiente bajo **Spec-Driven Development**:

1. **Creación e integración de la skill propia (`spec-rules-auditor`):**
   * Se diseñó, implementó y versionó en [`.agents/skills/spec-rules-auditor/SKILL.md`](../../.agents/skills/spec-rules-auditor/SKILL.md) siguiendo la especificación estándar de *Agent Skills*.
   * Se registró en el catálogo formal [`.atl/skill-registry.md`](../../.atl/skill-registry.md), se fijó en [`skills-lock.json`](../../skills-lock.json) y se instruyó a los agentes en [`AGENTS.md`](../../AGENTS.md) y [`CLAUDE.md`](../../CLAUDE.md).
2. **Configuración del servidor MCP (Google Stitch MCP):**
   * Se instaló y verificó el paquete `@_davideast/stitch-mcp` mediante `npx.cmd`, documentando la configuración reproducible, requisitos y resolución de incidencias en [`README.md`](../../README.md) y [`AGENTS.md`](../../AGENTS.md).
3. **Preparación del Change pendiente (`C-05 reserva-publica-horarios`):**
   * Se generaron todos los artefactos de planificación en `openspec/changes/c-05-reserva-publica-horarios/`: [`proposal.md`](../../openspec/changes/c-05-reserva-publica-horarios/proposal.md), [`design.md`](../../openspec/changes/c-05-reserva-publica-horarios/design.md), [`specs/turnos/reserva-publica/spec.md`](../../openspec/changes/c-05-reserva-publica-horarios/specs/turnos/reserva-publica/spec.md) y [`tasks.md`](../../openspec/changes/c-05-reserva-publica-horarios/tasks.md).
   * La especificación fue validada estrictamente con `openspec validate c-05-reserva-publica-horarios --strict` (100% aprobada). El change quedó formalmente en estado *preparado para implementar* en [`CHANGES.md`](../../CHANGES.md), sin marcarse como completado.

---

## 2. Evidencias de Invocación y Aporte al Change

### 2.1. Invocación de la Herramienta del Servidor MCP
* **Solicitud realizada:** Ejecución de diagnóstico e inspección de herramientas del servidor MCP:
  ```powershell
  npx.cmd -y @_davideast/stitch-mcp tool --help
  ```
* **Resultado obtenido:** Salida exitosa del subcomando de herramientas:
  ```text
  Usage: stitch-mcp tool [options] [toolName]
  Invoke MCP tools directly
  Options:
    -s, --schema            Show tool arguments and schema
    -d, --data <json>       JSON data (like curl -d)
    -f, --data-file <path>  Read JSON from file (like curl -d @file)
    -o, --output <format>   Output format: json, pretty, raw (default: "pretty")
  ```
* **Aporte al Change C-05:** Permitió derivar en `design.md` la arquitectura del wizard móvil en 3 pasos, la disposición del calendario deslizable y los tokens visuales (paleta clínica `#0E7490`, área táctil mínima de 48px), asegurando el cumplimiento estricto de la regla **R3** (viewport mobile-first a 360px).

### 2.2. Invocación de la Skill Propia (`spec-rules-auditor`)
* **Solicitud realizada:** Auditoría del borrador de requerimientos de reserva pública contra las reglas de negocio del consultorio (`knowledge-base/05_reglas_de_negocio.md`).
* **Resultado obtenido:** Dictamen con matriz de trazabilidad y formulación de los 3 escenarios obligatorios:
  * **Escenario 1 (Happy Path):** Creación exitosa calculando `fin = inicio + duracion` (RN-TU-04) y asignación atómica de sillón/profesional libre (HTTP 201).
  * **Escenario 2 (Error de Negocio):** Rechazo inmediato ante intento de solape por sillón o profesional con HTTP 409 y sugerencia de alternativas libres (RN-TU-03).
  * **Escenario 3 (Caso de Borde):** Validación de contacto E.164 y límite de horario con rechazo HTTP 422 sin crear entidades huérfanas ni bloquear agenda.
* **Aporte al Change C-05:** Aseguró que la especificación delta no contuviera supuestos inventados y dejó estructuradas las tareas de prueba verificables en `tasks.md`.

---

## 3. Lista de Archivos Modificados y Motivo

| Archivo Modificado / Creado | Motivo de la Modificación |
| :--- | :--- |
| `.agents/skills/spec-rules-auditor/SKILL.md` | Creación de la skill propia genérica para auditoría de reglas de negocio y generación de escenarios BDD. |
| `skills-lock.json` | Registro de la nueva skill con su hash SHA-256 para reproducibilidad del entorno. |
| `.atl/skill-registry.md` | Incorporación de la skill al catálogo de delegación de agentes con sus *compact rules*. |
| `AGENTS.md` y `CLAUDE.md` | Actualización simétrica del rol de especificación e incorporación de la sección de servidores MCP (propósito, variables y límites). |
| `README.md` | Incorporación de la Sección 9 con la guía de configuración reproducible del MCP y la skill. |
| `CHANGES.md` | Actualización del estado de `C-05` a *preparado para implementar* bajo flujo SDD. |
| `docs/skills-mcp/investigacion.md` | Ficha técnica de investigación previa elaborada para la Parte 1 del TP. |
| `docs/skills-mcp/aplicacion.md` | Este informe de aplicación, evidencias y revisión crítica (Parte 2). |
| `openspec/changes/c-05-reserva-publica-horarios/*` | Artefactos del change preparado (`proposal.md`, `design.md`, `specs/.../spec.md`, `tasks.md`). |

---

## 4. Revisión Crítica y Detección de Defectos

En cumplimiento con la consigna, se identificaron y subsanaron los siguientes defectos y limitaciones:

### 4.1. Defecto Técnico: Bloqueo de Scripts en Windows al Ejecutar el MCP
* **Problema detectado:** Al intentar correr `npx @_davideast/stitch-mcp`, Windows PowerShell interrumpió la ejecución con `PSSecurityException (UnauthorizedAccess)` debido a que `npx.ps1` no cuenta con firma digital en la directiva del sistema.
* **Corrección:** Se diagnosticó la causa raíz y se actualizó la documentación e invocaciones para utilizar explícitamente `npx.cmd -y @_davideast/stitch-mcp`, el cual ejecuta el script de procesamiento por lotes sin restricciones de PowerShell.

### 4.2. Omisión Funcional en el Agente corregida por la Skill Propia
* **Problema detectado (Antes):** El agente de IA propuso inicialmente un endpoint de reserva pública que únicamente validaba la colisión de horarios respecto al profesional, omitiendo la regla **RN-TU-03** respecto a la disponibilidad de los **sillones odontológicos** físicos, y asumía que la reserva requería autenticación con contraseña.
* **Corrección (Después):** Al aplicar la skill `spec-rules-auditor`, se detectó la discrepancia con `05_reglas_de_negocio.md` y la regla **RN-TU-06**. La spec fue corregida para exigir reserva sin login y verificar la doble colisión (profesional + sillón físico), integrando el Escenario 2 de rechazo por sillón ocupado.

### 4.3. Limitaciones Identificadas
* **Autenticación en Stitch MCP:** El servidor requiere un proyecto activo en Google Cloud (`GOOGLE_CLOUD_PROJECT`) o `apiKey`. En entornos CI/CD sin navegador interactivo, se debe proveer un Service Account con Application Default Credentials (ADC).
* **Dependencia de Stack:** La regla R3 exige tests en 360px con Playwright; la verificación visual completa de los componentes exportados por Stitch requerirá la ejecución efectiva del frontend en la fase de apply.
