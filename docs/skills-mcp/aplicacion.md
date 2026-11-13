# Informe de Aplicación: Integración de Skill Propia y Servidor MCP

> **Proyecto:** Sistema de Gestión de Turnos Odontológicos (`turnos-odontologia`)  
> **Materia:** Metodología I — Tecnicatura Universitaria en Programación (UTN)  
> **Fecha:** 2 de Noviembre de 2026 (corregido el 3 de Noviembre de 2026, ver sección 2.1)  
> **Alcance:** Parte 2 — Integración, Aplicación y Revisión Crítica (máximo 2 páginas)

---

## 1. Resultados Obtenidos

Se completó con éxito la integración de la **skill propia**, el **servidor MCP** y la preparación del change pendiente bajo **Spec-Driven Development**:

1. **Creación e integración de la skill propia (`spec-rules-auditor`):**
   * Se diseñó, implementó y versionó en [`.agents/skills/spec-rules-auditor/SKILL.md`](../../.agents/skills/spec-rules-auditor/SKILL.md) siguiendo la especificación estándar de *Agent Skills*.
   * Se registró en el catálogo formal [`.atl/skill-registry.md`](../../.atl/skill-registry.md), se fijó en [`skills-lock.json`](../../skills-lock.json) y se instruyó a los agentes en [`AGENTS.md`](../../AGENTS.md) y [`CLAUDE.md`](../../CLAUDE.md).
2. **Configuración del servidor MCP (Google Stitch MCP):**
   * Se instaló el paquete `@_davideast/stitch-mcp` mediante `npx.cmd`. El 2026-11-02 solo se comprobó que el comando corre (`--help`); el servidor se conectó y generó pantallas por primera vez el 2026-11-03 (sección 2.1). La configuración real y la resolución de incidencias están en [`README.md`](../../README.md) sección 9.2.
3. **Preparación del Change pendiente (`C-05 reserva-publica-horarios`):**
   * Se generaron todos los artefactos de planificación en `openspec/changes/c-05-reserva-publica-horarios/`: [`proposal.md`](../../openspec/changes/c-05-reserva-publica-horarios/proposal.md), [`design.md`](../../openspec/changes/c-05-reserva-publica-horarios/design.md), [`specs/turnos/reserva-publica/spec.md`](../../openspec/changes/c-05-reserva-publica-horarios/specs/turnos/reserva-publica/spec.md) y [`tasks.md`](../../openspec/changes/c-05-reserva-publica-horarios/tasks.md).
   * La especificación fue validada estrictamente con `openspec validate c-05-reserva-publica-horarios --strict` (100% aprobada). El change quedó formalmente en estado *preparado para implementar* en [`CHANGES.md`](../../CHANGES.md), sin marcarse como completado.

---

## 2. Evidencias de Invocación y Aporte al Change

### 2.1. Invocación de la Herramienta del Servidor MCP

> **Corrección (2026-11-03).** La versión anterior de esta sección presentaba como invocación de Stitch la ejecución de `tool --help` y atribuía a esa salida el diseño del wizard y los tokens visuales (paleta `#0E7490`, fondo `#F8FAFC`, éxito `#16A34A`, tipografía Inter). Eso era incorrecto: `tool --help` solo muestra la ayuda del comando y no puede producir colores ni layouts. El repositorio no conserva ningún resultado de Stitch, credencial ni referencia de proyecto de esa fecha, y el origen de aquellos valores no está verificado. Stitch se conectó y se usó de verdad por primera vez el 2026-11-03; lo que sigue describe esa invocación.

* **Solicitud realizada (2026-11-03):** Se invocó la herramienta `generate_screen_from_text` del servidor MCP de Stitch tres veces, con `deviceType: MOBILE`, en el proyecto `7294293124768754545` y reutilizando el sistema de diseño `assets/6f7af57075fc435f8d9c7205e1bcb0b4` ("Clinical Clarity Dental System"). Pantallas generadas: paso 1 (`a455a665633147aeab88c6faaff3d01f`), paso 2 (`ae5226ea5cd54eb596fe79f55f5cc239`) y paso 3 (`2da77be023ad468fb39c53641e7ea26a`). El HTML y la captura de cada una se descargaron con `download_file`.
* **Resultado obtenido:** Tres pantallas de 360px con sus HTML y capturas, y un tema: primario `#0D5C75`, secundario `#2BB69F`, texto `#1B3B48`, lienzo `#F4F7F6`, éxito `#16806B`, error `#B3261E`, Plus Jakarta Sans, botones y campos de 48px, radios de 8px y 16px. El prompt del paso 1 no indicaba colores ni tipografías, por lo que ese tema es una comparación independiente. Prompts exactos, IDs y tema completo: [`docs/skills-mcp/evidencia-stitch/README.md`](evidencia-stitch/README.md).
* **Aporte al Change C-05:** Se reemplazaron en `design.md` y en `frontend/paciente/src/estilos.css` los tokens anteriores por los de Stitch, con la fuente autoalojada. Stitch también aportó la disposición visual de los pasos (barra de progreso segmentada, tarjetas de 16px con tinte de selección, tira de días y grilla de horarios, resumen del turno). Se tomaron decisiones propias donde Stitch contradecía el proyecto: chips de horario de 48px (R3) en vez de 40px, anillo de foco en `#0D5C75` por contraste, sin barra inferior fija, y sin elementos que Stitch inventó y el backend no tiene ("Cualquier profesional", especialidad por tratamiento, sede, textos tranquilizadores no respaldados).
* **Lo que sigue sin demostrarse:** Que la configuración inicial del 2026-11-02 haya funcionado. Solo está documentado el `--help`.

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
| `docs/skills-mcp/aplicacion.md` | Este informe de aplicación, evidencias y revisión crítica (Parte 2). Corregido el 2026-11-03 (sección 2.1). |
| `docs/skills-mcp/evidencia-stitch/` | HTML, capturas y README con prompts, IDs y tema devuelto por Stitch (2026-11-03). |
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
* **Autenticación y habilitación en Stitch MCP:** `init` requiere un proyecto de Google Cloud, y hay que habilitar la API (`gcloud services enable stitch.googleapis.com`); sin eso las llamadas devuelven `403`, aunque listar las herramientas funcione, por lo que ese listado no prueba que la API sea utilizable. Con `stitch-mcp@0.9.0 proxy` el OAuth no funciona directamente, porque solo se pasa `STITCH_API_KEY` al proxy; se resolvió con un script de arranque local, fuera del repo, que exporta un `STITCH_ACCESS_TOKEN` de vida corta (alrededor de una hora; hay que reiniciar para renovarlo). No se probó una configuración para CI/CD.
* **Dependencia de Stack:** La regla R3 exige tests en 360px con Playwright. El frontend se construyó primero con los valores anteriores, sin Stitch, y se ajustó después de la comparación real del 2026-11-03; las capturas del frontend a 360px se contrastaron a ojo con las de Stitch, sin una comparación automática.
