# Spec Delta: turnos/gestion-paciente

## ADDED Requirements

### Requirement: La gestión informa el límite de solicitudes sin cambiar el turno
Si consultar, cancelar, reprogramar o confirmar un turno con el código de gestión responde 429, el sitio del paciente SHALL mostrar "Hiciste muchos pedidos seguidos. Probá de nuevo en N minutos", con N desde `Retry-After` redondeado hacia arriba (mínimo 1), y no SHALL mostrar la operación como hecha. El turno no SHALL cambiar de estado (RN-TU-08 y la ventana de RN-TU-11 siguen aplicando al reintentar).

#### Scenario: Cancelación limitada (Happy Path del mensaje)
- **GIVEN** un turno `reservado` dentro de la ventana de cancelación y la pantalla de gestión abierta
- **WHEN** el paciente toca "Cancelar turno" y la API responde 429 con `Retry-After: 120`
- **THEN** ve "Hiciste muchos pedidos seguidos. Probá de nuevo en 2 minutos" y el turno sigue `reservado`

#### Scenario: Cancelación fuera de la ventana de 24 h (Error de Negocio)
- **GIVEN** un turno que empieza en 20 horas
- **WHEN** el paciente intenta cancelarlo y la API responde con el rechazo de la ventana de 24 h
- **THEN** ve el mensaje de la ventana de 24 h de siempre, no el de límite

#### Scenario: Reintento después de la espera (Caso de Borde)
- **GIVEN** el mensaje de límite por una confirmación
- **WHEN** pasados los minutos indicados el paciente vuelve a tocar "Confirmar asistencia"
- **THEN** la confirmación se procesa con las reglas de siempre
