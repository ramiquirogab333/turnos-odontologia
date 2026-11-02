# Proposal: c-05-reserva-publica-horarios

## Why
Actualmente, el paciente debe coordinar turnos mediante llamadas telefónicas o mensajes de WhatsApp dispersos, lo que genera demoras, desatención fuera de horario comercial y sobrecarga en la recepción. Esta propuesta implementa el portal público de reserva de turnos mobile-first, permitiendo a los pacientes consultar en tiempo real las franjas horarias libres y reservar su turno en menos de 2 minutos sin registro ni contraseña obligatoria (sólo nombre y WhatsApp), garantizando la regla de anti-solape dual por profesional y sillón.

## What Changes
- **Frontend Paciente (`frontend-paciente/`):** Scaffolding y desarrollo del flujo de reserva online responsive mobile-first optimizado para pantallas de 360px (R3), con tipografía clínica clara y navegación sin cascadas de fetch (`Promise.all` y `Suspense`, R1/R2).
- **Consulta de Disponibilidad (`GET /api/public/disponibilidad`):** Endpoint público de cálculo dinámico de franjas horarias libres basado en la agenda de profesionales, sillones odontológicos y duración del tratamiento solicitado (`fin = inicio + duracion_minutos`).
- **Reserva Pública de Turnos (`POST /api/public/turnos`):** Creación de turno con datos de contacto básicos (nombre + teléfono/WhatsApp verificado), asignando automáticamente sillón disponible y profesional, reutilizando la exclusión GiST de Postgres (`EXCLUDE USING gist`) para evitar dobles reservas.
- **Enlace de Gestión Pública:** Generación de un token o código único para que el paciente pueda consultar o solicitar cancelación/reprogramación con anticipación mínima de 24 hs.

## Capabilities

### New Capabilities
- `turnos/reserva-publica`: Consulta pública de disponibilidad y creación de reservas de turnos sin autenticación previa por parte del paciente, respetando duraciones de tratamiento, disponibilidad de sillón y reglas anti-solape.

### Modified Capabilities
- Ninguna (la capacidad existente `turnos/creacion-sin-solape` de C-01 se mantiene intacta como motor backend de integridad).

## Impact
- **Backend:** Nuevos endpoints públicos bajo `/api/public/` en FastAPI con esquemas Pydantic de entrada/salida (R15).
- **Frontend:** Creación de la aplicación React + TypeScript + Vite en `frontend-paciente/`.
- **Integraciones / MCP:** Mockups y layout visual mobile-first derivados y asistidos mediante Google Stitch MCP (`design.md`).
- **Validación de Dominio:** Especificación auditada y estructurada mediante la skill `spec-rules-auditor` con cobertura de los tres escenarios verificables obligatorios.
