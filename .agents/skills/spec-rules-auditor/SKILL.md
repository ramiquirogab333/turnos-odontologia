---
name: spec-rules-auditor
description: Audit specifications, proposals, and design documents against business rules and domain invariants. Formulates and verifies the mandatory three-scenario test matrix (Happy Path, Business Error, and Edge Case) in Spec-Driven Development (SDD) and OpenSpec workflows.
---

# Spec & Business Rules Auditor (`spec-rules-auditor`)

A reusable, domain-agnostic skill designed to audit technical specifications, RFCs, change proposals, and designs against a project's authoritative business rules and invariants.

## When to Use

- When preparing, exploring, or reviewing a change in **Spec-Driven Development (SDD)** or **OpenSpec** (`openspec-propose`, `openspec-explore`, `proposal.md`, `design.md`, `spec.md`).
- When defining acceptance criteria, user stories, or test scenarios to ensure domain compliance.
- When verifying that no implicit assumptions or unauthorized rule changes slip into feature designs.
- When generating the canonical **Three-Scenario Verification Matrix** (Expected Behavior, Business Rule Error, Edge Case) required for rigorous specification and test-driven implementation.

---

## Inputs Required

1. **Source of Truth (Domain Rules):**
   * *In this project:* `knowledge-base/05_reglas_de_negocio.md` and hard constraints in `AGENTS.md` (e.g. `RN-TU-*`, `RN-PG-*`, `R1-R20`).
   * *In other projects:* Any markdown/text file containing coded business rules, domain invariants, or PRD requirements.
2. **Target Artifact to Audit:**
   * The delta specification (`spec.md`), proposal (`proposal.md`), or architecture design (`design.md`) under review.

---

## Audit Protocol (Step-by-Step)

Follow this 5-step procedure on every audit:

### Step 1: Entity & Flow Extraction
Identify all domain entities, operations, state transitions, and API endpoints introduced or modified by the target artifact.
* Example: `Turno`, `Paciente`, `POST /api/turnos/reservar`, estado `en_espera` -> `confirmado`.

### Step 2: Rules Matrix Mapping
Scan the Source of Truth and cross-reference every rule that intersects with the extracted entities.
* Create a mental or written traceability table:
  * Which rules are explicitly addressed?
  * Which rules apply to these entities but were **omitted** from the spec?
  * Are there rules partially satisfied or contradicted?

### Step 3: Conflict, Leakage & Assumption Detection
Check for common AI agent anti-patterns:
- **Invented rules:** Agent assumed a default (e.g., "defaults to 30 minutes") without verifying `RN-TU-04` or the treatments table.
- **Leaked state transitions:** Transitions bypassing required intermediate states (e.g., confirming a booking without checking deposit clearance `R8`).
- **Missing negative paths:** Spec describes only the success path and omits HTTP 400/409/422 responses and business error codes.

### Step 4: Verification of the Mandatory Three Scenarios
The skill MUST ensure that the specification defines at least three verifiable scenarios in BDD/Gherkin format:

1. **Scenario 1 — Happy Path (Comportamiento Esperado):**
   * Normal operation under valid preconditions.
   * All rules respected; postconditions and side effects verified.
2. **Scenario 2 — Business Error (Error de Negocio / Invariante Violada):**
   * Deliberate attempt to violate an explicit business rule (e.g., double booking over an occupied chair, cancelling with less than 24h notice).
   * Verifies immediate rejection, informative error code/message, and guarantee that no corrupted state is persisted.
3. **Scenario 3 — Edge Case (Caso de Borde / Límites Operativos):**
   * Boundary condition testing: minimum/maximum thresholds, exact time boundaries (e.g., 23h 59m before appointment), concurrent simultaneous requests, formatting edges (international phone codes, non-working hours).

### Step 5: Audit Report & Recommendation
Emit a formal audit report structured as follows:

```markdown
## Business Rules Audit Report: [Change Name / Artifact]

### 1. Verdict
[APROBADO | OBSERVACIONES | RECHAZADO]

### 2. Traceability Matrix
| Regla ID | Descripción Breve | Estado en Spec | Observación / Gap |
| :--- | :--- | :--- | :--- |
| RN-XX-01 | ... | CUBIERTA | Validado en Escenario 1 |
| RN-XX-02 | ... | OMITIDA | Requiere agregar validación de error |

### 3. Detected Gaps & Critical Risks
- [Riesgo/Omisión detectada y recomendación correctiva]

### 4. Canonical Verification Scenarios (to append to `spec.md`)

#### Scenario 1: [Nombre descriptivo - Happy Path]
- **Given** [Precondiciones válidas y estado del sistema]
- **When** [Acción ejecutada por el actor]
- **Then** [Resultado esperado, estado final y código de respuesta]

#### Scenario 2: [Nombre descriptivo - Violación de Regla de Negocio]
- **Given** [Precondiciones con conflicto o restricción activa]
- **When** [Acción infractora]
- **Then** [Rechazo con motivo explícito, código de error y preservación de estado]

#### Scenario 3: [Nombre descriptivo - Caso de Borde]
- **Given** [Condición en el límite operativo exacto]
- **When** [Acción en la frontera]
- **Then** [Comportamiento determinístico y seguro]
```

---

## Review Criteria & Quality Gates

An audit generated by this skill is considered complete ONLY IF:
- [x] Every affected rule from the Source of Truth is accounted for in the Traceability Matrix.
- [x] No hypothetical business rules are invented without flagging them as `[SUPUESTO / ABIERTO]`.
- [x] The Three Scenarios are complete, deterministic, and directly translatable into automated tests (Playwright, Pytest, etc.).
- [x] Privacy rules (e.g. synthetic data only, no real patient info) are strictly respected in all scenario examples.
