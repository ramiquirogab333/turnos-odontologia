# Tasks: c-05-reserva-publica-horarios

## 1. Backend: Endpoints Públicos de Disponibilidad y Reserva

- [x] 1.1 Definir esquemas Pydantic `DisponibilidadPublicaQuery`, `DisponibilidadPublicaResponse`, `ReservaPublicaRequest` y `ReservaPublicaResponse` con validación de teléfono E.164 (R15) y verificar validaciones con tests unitarios.
- [x] 1.2 Implementar servicio y endpoint `GET /api/public/disponibilidad` que calcula franjas libres según duración del tratamiento y estado de sillones/profesionales, verificando cálculo correcto mediante pytest.
- [x] 1.3 Implementar endpoint `POST /api/public/turnos` con asignación atómica de sillón y manejo de excepciones de solape relacional (`EXCLUDE USING gist`), verificando respuestas 201 y 409 con pytest.

## 2. Frontend Paciente: Flujo Mobile-First (360px) asistido por Stitch

- [x] 2.1 Configurar scaffolding `frontend-paciente/` en React + TypeScript + Vite (`strict: true`, sin `any` - R1) e integrar tokens de diseño clínico extraídos con Google Stitch MCP.
- [x] 2.2 Construir wizard de 3 pasos (Tratamiento → Calendario/Slots → Contacto) garantizando botones de 48px y usabilidad completa en viewport de 360px (R3).
- [x] 2.3 Implementar consumo de API sin fetches en cascada mediante carga paralela con `Promise.all` y límites `Suspense` (R2), verificando renderizado sin waterfalls de red.
- [x] 2.4 Implementar E2E Playwright del flujo completo de reserva a viewport 360px contra el backend real en Docker Compose, incluyendo slot ocupado con alternativas y teléfono inválido, sin scroll horizontal (R3, R7; done-criteria de C-05 en `CHANGES.md`).
- [x] 2.5 Configurar CI en GitHub Actions con jobs paralelos backend y frontend (alcance de C-05 en `CHANGES.md`).

## 3. Verificación de la Terna de Escenarios (Auditoría `spec-rules-auditor`)

- [x] 3.1 Verificar **Escenario 1 (Happy Path)**: Ejecutar prueba de reserva exitosa con nombre "Carlos Sintético", teléfono "+5491144445555" y tratamiento de 30 min, comprobando código HTTP 201, cálculo de fin exacto y generación de código de gestión.
- [x] 3.2 Verificar **Escenario 2 (Error de Negocio)**: Ejecutar prueba de carrera concurrente con dos peticiones simultáneas sobre el mismo slot, comprobando que una obtiene 201 y la otra 409 Conflict con detalle del solape y lista de alternativas libres.
- [x] 3.3 Verificar **Escenario 3 (Caso de Borde)**: Ejecutar prueba con teléfono inválido en el límite del horario de atención clínica, comprobando rechazo HTTP 422 Unprocessable Entity, ausencia de bloqueo de agenda y cero registros huérfanos.

> Nota de verificación (apply frontend): 3.1, 3.2 y 3.3 quedan verificados **por la UI a 360px contra el backend real**
> (`frontend-paciente/e2e/reserva.spec.ts`, Playwright + Docker Compose + PostgreSQL; 7 tests en verde, repetidos x3. El test R2 fallaba de forma intermitente por pedidos en vuelo de la carga del `beforeEach`: se aisló y se reescribió sin depender del orden de eventos, 120/120 en verde) y, además,
> a nivel API (`backend/tests/test_public_endpoints_integration.py`). 2.1: el frontend se armó primero con tokens de origen no verificado (sin Stitch) y el 2026-11-03 se
> ajustó con los tokens reales de Stitch (tres pantallas generadas con `generate_screen_from_text`; evidencia en
> `docs/skills-mcp/evidencia-stitch/`; desvíos por R3 y contraste documentados en `design.md` Decisión 1 y en `estilos.css`). 2.5: `.github/workflows/ci.yml` corrió en verde en GitHub Actions (run 41762187593, commit 7a31f34; jobs backend, frontend y e2e). Para 2.3 se agregaron `GET /api/public/tratamientos` y
> `GET /api/public/profesionales` (el wizard no tenía catálogo público).

## Workflow follow-up
- Una vez implementado y verificado en la etapa correspondiente del roadmap, archivar con `openspec archive c-05-reserva-publica-horarios`.
