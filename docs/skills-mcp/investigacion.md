# Ficha de Investigación: Integración de Skill Propia y Servidor MCP

> **Proyecto:** Sistema de Gestión de Turnos Odontológicos (`turnos-odontologia`)  
> **Materia:** Metodología I — Tecnicatura Universitaria en Programación (UTN)  
> **Fecha:** 2 de Noviembre de 2026  
> **Alcance:** Parte 1 — Investigación y Planificación en Clase (máximo 2 páginas)

---

## 1. Necesidad Detectada en el Proyecto

Al analizar el ciclo de vida del proyecto bajo la metodología **Spec-Driven Development (SDD / OPSX)** y las reglas duras consolidadas en `AGENTS.md`, se identificaron dos necesidades críticas para la preparación de los próximos changes:

1. **Tarea repetible para una Skill propia (Auditoría de Reglas de Negocio en Specs):**
   Al redactar o preparar un nuevo change (`proposal.md`, `spec.md`, `design.md`), el agente de desarrollo tiende a asumir comportamientos por defecto o a omitir casos de borde indispensables. En este dominio existen reglas estrictas e invariantes (anti-solape dual profesional/sillón `RN-TU-03`, cancelación con 24 hs de anticipación `RN-TU-01`, y la regla de seña no bloqueante en estado `en_espera` de `C-06`). Se necesita un procedimiento formal, reutilizable y agnóstico que tome las reglas de negocio del proyecto y audite la especificación, garantizando la terna obligatoria de escenarios de prueba (esperado, error de negocio y caso de borde).
2. **Acceso a herramientas externas para un Servidor MCP (Diseño e Inspección UI Mobile-First):**
   La regla dura **R3** del proyecto establece: *«NUNCA una pantalla de reserva que no funcione a 360px → mobile-first es criterio de aceptación»*. Actualmente, el agente sólo cuenta con herramientas de texto y consola local, careciendo de capacidades para concebir, explorar y extraer prototipos visuales interactivos y componentes web adaptados al flujo móvil de reserva. Un servidor MCP especializado en diseño permite salvar este gap técnico.

---

## 2. Change Elegido de `CHANGES.md`

* **Change seleccionado:** `[C-05] reserva-publica-horarios`
* **Por qué puede prepararse sin depender de código inexistente:**
  La fase de preparación en SDD comprende el análisis del problema, el diseño técnico (`design.md`) y la especificación de comportamiento con escenarios verificables (`spec.md`). Aunque la implementación posterior de `C-05` requiera los modelos base de `C-02` a `C-04`, su contrato funcional (pantalla mobile de 360px, datos de paciente sin login, selección de tratamiento y cálculo de horarios) puede especificarse exhaustivamente de manera anticipada.
* **Aporte conjunto de la Skill y el MCP en la preparación de C-05:**
  * **Stitch MCP:** Conecta al agente con la plataforma de prototipado Google Stitch, permitiendo generar e importar los layouts visuales, jerarquía visual y tokens CSS a 360px requeridos en `design.md`.
  * **Skill propia (`spec-rules-auditor`):** Audita el borrador de `spec.md` de C-05 contrastándolo contra `knowledge-base/05_reglas_de_negocio.md`, obligando a definir con exactitud los 3 escenarios verificables (reserva exitosa, intento de solape/bloqueo de agenda y límites de validación de WhatsApp).

---

## 3. Skill Creadora y Diseño de la Skill Propia

### 3.1. Skill Creadora Investigada
* **Nombre:** `skill-creator`
* **Autor / Repositorio oficial:** Anthropic (`https://github.com/anthropics/skills/tree/main/skills/skill-creator`) — Estándar *Agent Skills* (`https://agentskills.io`).
* **Compatibilidad:** Totalmente compatible con Antigravity, Claude Code y entornos que implementan el estándar de Agent Skills con frontmatter YAML.
* **Instalación y disponibilidad:** Ya disponible en el entorno del agente (`~/.gemini/config/skills/skill-creator/SKILL.md`). Permite estructurar de forma iterativa el `SKILL.md`, definiendo activación semántica, entradas y criterios de evaluación.

### 3.2. Diseño de la Skill Propia: `spec-rules-auditor`
* **Propósito:** Auditar sistemáticamente cualquier artefacto de especificación (`spec.md` o borrador de requerimientos) contra las reglas de negocio e invariantes documentadas en el proyecto, detectando ambigüedades, supuestos no justificados y generando la terna de escenarios verificables.
* **Cuándo se activa:** Durante la preparación, exploración o revisión de un change en OpenSpec/SDD, o cuando el usuario solicita «validar la spec», «auditar reglas de negocio» o «revisar escenarios de prueba».
* **Entradas necesarias:**
  1. *Fuente de Reglas de Negocio:* Archivo canónico del proyecto (ej. `knowledge-base/05_reglas_de_negocio.md` o reglas en `AGENTS.md`).
  2. *Artefacto a auditar:* Contenido del change propuesto (`proposal.md`, `spec.md` o `design.md`).
* **Procedimiento:**
  1. Extraer las entidades y flujos involucrados en el change.
  2. Contrastar contra la matriz de reglas activas (identificar qué reglas aplican y si alguna fue omitida o contradicha).
  3. Formular o validar la existencia de al menos **tres escenarios verificables** obligatorios:
     * *Escenario 1 (Comportamiento Esperado):* Flujo estándar cumpliendo todas las invariantes.
     * *Escenario 2 (Error de Negocio):* Intento de violación de una regla de dominio con su correspondiente rechazo/código de error.
     * *Escenario 3 (Caso de Borde):* Condiciones límite (ej. concurrencia, umbrales de tiempo, formatos).
  4. Emitir informe de auditoría indicando `[APROBADO]` o `[OBSERVACIONES]` junto al bloque markdown/Gherkin sugerido.
* **Resultado esperado:** Reporte estructurado de cumplimiento normativo y bloque de escenarios listo para incorporar en `spec.md`.
* **Criterios de revisión del resultado:** Ninguna regla aplicable omitida; los escenarios deben ser reproducibles con datos sintéticos y contener precondición, acción y resultado esperado concreto.
* **Ubicación y referencia:** Se almacenará en `.agents/skills/spec-rules-auditor/SKILL.md` (repositorio local del proyecto) para asegurar portabilidad y versionado en Git.

---

## 4. Comparación y Selección del Servidor MCP

| Criterio | Servidor A (Elegido): **Google Stitch MCP** | Servidor B (Comparado): **Playwright MCP** |
| :--- | :--- | :--- |
| **Nombre / Paquete** | `@_davideast/stitch-mcp` (David East / Google Labs) | `@modelcontextprotocol/server-playwright` |
| **Propósito** | Puente de diseño: conecta con Google Stitch para importar prototipos UI, pantallas y tokens. | Automatización de navegador web para scraping, inspección DOM y ejecución de tests E2E. |
| **Capacidades** | Listar proyectos UI, extraer código HTML/React, descargar capturas visuales, leer `design.md`. | Navegar URLs, hacer click, rellenar formularios, tomar screenshots de páginas activas, leer consola. |
| **Compatibilidad** | Compatible vía protocolo MCP stdio / proxy npx. | Compatible nativo MCP sobre Node.js y navegadores Chromium. |
| **Requisitos / Conexión** | Node.js (npx), autenticación Google Cloud (`GOOGLE_CLOUD_PROJECT`). | Node.js (npx), instalación de navegadores Chromium/Firefox (`npx playwright install`). |
| **Permisos / Credenciales**| Token/Auth de Google Cloud / Google Labs Stitch. | Sin credenciales externas; requiere permisos de ejecución de procesos locales y acceso a red local. |
| **Costos** | Gratuito en fase preview / experimental de Google Labs. | 100% de código abierto y gratuito (sin costos de API). |

### 4.1. Elección Justificada
Se elige **Google Stitch MCP** porque el objetivo en esta etapa del proyecto es la **preparación y diseño visual de un change de frontend** (`C-05`, pantalla pública mobile-first). Playwright MCP es una herramienta pensada para interactuar con aplicaciones ya desplegadas y en ejecución; en este momento no hay un frontend desplegado para testear, por lo que Stitch aporta valor real inmediato al generar los artefactos visuales del `design.md`.

### 4.2. Información y Límites de Datos
* **Datos a consultar/modificar:** Prototipos visuales de interfaz, componentes web y tokens CSS de diseño.
* **Límites de acceso y privacidad:** Stitch MCP opera exclusivamente en la capa de presentación visual. No interactúa con base de datos, credenciales del sistema ni información clínica. Todos los mockups utilizarán información 100% sintética y de fantasía (cumpliendo estrictamente con la Ley 25.326 y la regla R19 del proyecto).

---

## 5. Pasos de Instalación y Configuración del MCP

1. **Requisitos previos:** Node.js (v18+) instalado en el sistema y proyecto activo en Google Cloud.
2. **Configuración del servidor en el cliente MCP:**
   Registrar en el archivo de configuración del cliente MCP (o entorno de ejecución):
   ```json
   {
     "mcpServers": {
       "stitch": {
         "command": "npx",
         "args": ["-y", "@_davideast/stitch-mcp", "proxy"],
         "env": {
           "GOOGLE_CLOUD_PROJECT": "TU_GOOGLE_CLOUD_PROJECT_ID"
         }
       }
     }
   }
   ```
3. **Comprobación de la conexión y ejecución:**
   * Ejecutar la inicialización interactiva si se requiere: `npx @_davideast/stitch-mcp init`.
   * Verificar en el cliente la disponibilidad de las herramientas expuestas (`list_screens`, `get_screen_code`, etc.).
   * Ejecución de prueba: invocar una herramienta de consulta para listar los componentes visuales disponibles.

---

## 6. Archivos de la Fundación que se Prevén Actualizar

1. **`AGENTS.md` / `CLAUDE.md`:** 
   * Agregar `spec-rules-auditor` a la tabla de skills disponibles por rol.
   * Documentar la sección del servidor MCP de Stitch (propósito, herramientas, variables de entorno y límites de acceso).
2. **`.atl/skill-registry.md`:** 
   * Registrar formalmente la skill propia (nombre, propósito, ubicación en `.agents/skills/spec-rules-auditor/` y disparadores).
3. **`README.md`:** 
   * Incluir la sección de configuración reproducible del servidor MCP y los comandos necesarios para ponerlo en funcionamiento en una instalación limpia.
4. **`CHANGES.md`:** 
   * Registrar que el change `C-05` cuenta con sus especificaciones y diseño preparados con el soporte de la nueva skill y el MCP.

---

## 7. Fuentes y Referencias Consultadas

* **Agent Skills Specification:** *Open standard for agent skills*, URL: `https://agentskills.io` (Consultado: 2026-11-02).
* **Anthropic Skills Repository:** *Skill Creator implementation and guidelines*, URL: `https://github.com/anthropics/skills/tree/main/skills/skill-creator` (Consultado: 2026-11-02).
* **Stitch MCP Server Repository:** *CLI and MCP wrapper for Google Stitch by David East*, URL: `https://github.com/davideast/stitch-mcp` (Consultado: 2026-11-02).
* **Google Stitch Platform:** *Google Labs AI UI Design Tool*, URL: `https://stitch.withgoogle.com/` (Consultado: 2026-11-02).
* **Model Context Protocol Specification:** *Anthropic MCP Servers Directory*, URL: `https://github.com/modelcontextprotocol/servers` (Consultado: 2026-11-02).
* **Playwright MCP Server:** *Reference implementation for web automation*, URL: `https://github.com/modelcontextprotocol/servers/tree/main/src/playwright` (Consultado: 2026-11-02).
