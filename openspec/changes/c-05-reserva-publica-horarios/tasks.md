# Tasks: c-05-reserva-publica-horarios

## 1. Backend: Endpoints Públicos de Disponibilidad y Reserva

- [ ] 1.1 Definir esquemas Pydantic `DisponibilidadPublicaQuery`, `DisponibilidadPublicaResponse`, `ReservaPublicaRequest` y `ReservaPublicaResponse` con validación de teléfono E.164 (R15) y verificar validaciones con tests unitarios.
- [ ] 1.2 Implementar servicio y endpoint `GET /api/public/disponibilidad` que calcula franjas libres según duración del tratamiento y estado de sillones/profesionales, verificando cálculo correcto mediante pytest.
- [ ] 1.3 Implementar endpoint `POST /api/public/turnos` con asignación atómica de sillón y manejo de excepciones de solape relacional (`EXCLUDE USING gist`), verificando respuestas 201 y 409 con pytest.

## 2. Frontend Paciente: Flujo Mobile-First (360px) asistido por Stitch

- [ ] 2.1 Configurar scaffolding `frontend-paciente/` en React + TypeScript + Vite (`strict: true`, sin `any` - R1) e integrar tokens de diseño clínico extraídos con Google Stitch MCP.
- [ ] 2.2 Construir wizard de 3 pasos (Tratamiento → Calendario/Slots → Contacto) garantizando botones de 48px y usabilidad completa en viewport de 360px (R3).
- [ ] 2.3 Implementar consumo de API sin fetches en cascada mediante carga paralela con `Promise.all` y límites `Suspense` (R2), verificando renderizado sin waterfalls de red.

## 3. Verificación de la Terna de Escenarios (Auditoría `spec-rules-auditor`)

- [ ] 3.1 Verificar **Escenario 1 (Happy Path)**: Ejecutar prueba de reserva exitosa con nombre "Carlos Sintético", teléfono "+5491144445555" y tratamiento de 30 min, comprobando código HTTP 201, cálculo de fin exacto y generación de código de gestión.
- [ ] 3.2 Verificar **Escenario 2 (Error de Negocio)**: Ejecutar prueba de carrera concurrente con dos peticiones simultáneas sobre el mismo slot, comprobando que una obtiene 201 y la otra 409 Conflict con detalle del solape y lista de alternativas libres.
- [ ] 3.3 Verificar **Escenario 3 (Caso de Borde)**: Ejecutar prueba con teléfono inválido en el límite del horario de atención clínica, comprobando rechazo HTTP 422 Unprocessable Entity, ausencia de bloqueo de agenda y cero registros huérfanos.

## Workflow follow-up
- Una vez implementado y verificado en la etapa correspondiente del roadmap, archivar con `openspec archive c-05-reserva-publica-horarios`.
