# Evidencia de uso de Google Stitch MCP (C-08)

Lo que Stitch devolvió el **2026-11-09** para la agenda del panel. Todos los datos de las pantallas son ficticios (R19). No se guardó ningún token ni credencial.

Las capturas son los bytes que devolvió `download_file`, decodificados desde base64. **El HTML no se guardó en este directorio:** la herramienta lo devolvió en la conversación y copiarlo a mano habría sido una transcripción, no el original. Se puede recuperar con `download_file` y los identificadores de abajo.

## Datos de la sesión

| Dato | Valor |
| :--- | :--- |
| Fecha | 2026-11-09 |
| Herramienta | `generate_screen_from_text` (servidor MCP `stitch`) |
| Parámetros comunes | `projectId: 7294293124768754545`, sin `modelId`, `designSystem: assets/6f7af57075fc435f8d9c7205e1bcb0b4` |
| Proyecto | `7294293124768754545`, el de C-05: se reutilizó para conservar el sistema "Clinical Clarity Dental System" |
| Recuperación | `get_screen` y `download_file` |

`list_screens` devolvió una respuesta vacía antes de generar, aunque el proyecto ya tenía las pantallas de C-05 y `get_project` respondió bien. No impidió generar.

## Pantallas

| # | Título | `deviceType` | ID de pantalla | Captura | HTML en Stitch |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 1 | Agenda del día - Recepción | `MOBILE` | `projects/7294293124768754545/screens/8b183471d9ca4f17b615ab28714d94d4` | [agenda-dia-360.png](agenda-dia-360.png) (780x2362) | `projects/7294293124768754545/files/173132b2d2c54bb8be93be394035612b` |
| 2 | Agenda semanal - Recepción clínica | `DESKTOP` | `projects/7294293124768754545/screens/4adf8afd774e41e4bf9b9ac472b1f32d` | [agenda-semana-escritorio.png](agenda-semana-escritorio.png) (2560x2048) | `projects/7294293124768754545/files/fa33e00c1b8b41a6b7f7cdcf085ac5bd` |

## Prompts enviados (textuales)

**Pantalla 1.**

```text
Pantalla móvil de 360px de ancho del panel interno de una clínica odontológica: agenda del día para recepción. Tono clínico, calmo y confiable. Todo el texto en español rioplatense, en sentence case, sin mayúsculas sostenidas. Encabezado con "Agenda", selector de vista "Día" (activo) y "Semana", y navegación de fecha con "Hoy", anterior y siguiente, mostrando "Martes 17 de noviembre". Dos filtros: profesional ("Dra. Ana Ficticia") y sillón ("Todos los sillones"). Debajo, una lista cronológica de turnos, cada fila de al menos 48px de alto con hora de inicio y fin, nombre del paciente, tratamiento, sillón y un estado con texto, sin depender solo del color. Datos ficticios: 09:00 a 09:30 "Carlos Sintético", Consulta odontológica, Sillón 1, estado "Reservado", seña acreditada; 09:30 a 10:15 "Lucía Ejemplo", Limpieza dental, Sillón 1, estado "Confirmado"; 10:30 a 11:15 "Marcos Ficticio", Empaste, Sillón 2, estado "Atendido"; 11:30 a 12:00 "Paula Demo", Consulta odontológica, Sillón 1, estado "Ausente", seña retenida; 12:00 a 12:30 "Tomás Prueba", Consulta odontológica, estado "Reservado", etiqueta "Alta manual, sin seña". Una pre-reserva sin pagar, con estilo claramente atenuado y borde punteado, sin ocupar la agenda: 10:00 a 10:30 "Sofía Muestra", estado "Esperando seña", con el aviso "No ocupa el horario". Botón principal "Nuevo turno". Sin scroll horizontal. No incluir logos, fotos de personas, gráficos, caja ni pagos en línea. Datos 100% ficticios.
```

**Pantalla 2.**

```text
Pantalla de escritorio del panel interno de una clínica odontológica: agenda semanal para recepción. Tono clínico, calmo y confiable. Todo el texto en español rioplatense, en sentence case, sin mayúsculas sostenidas. Encabezado con "Agenda", selector de vista "Día" y "Semana" (activo), navegación de semana con "Hoy", anterior y siguiente, y el rango "Lunes 16 al domingo 22 de noviembre". Filtros: profesional ("Dra. Ana Ficticia") y sillón ("Todos los sillones"). Una grilla con una columna por día de lunes a viernes y filas por hora de 09:00 a 13:00, sin turnos superpuestos entre sí. Cada bloque muestra hora, nombre del paciente, tratamiento y un estado con texto, sin depender solo del color. Datos ficticios: lunes 09:00 "Carlos Sintético", Consulta odontológica, "Reservado"; lunes 09:30 "Lucía Ejemplo", Limpieza dental, "Confirmado"; martes 10:30 "Marcos Ficticio", Empaste, "Atendido"; martes 11:30 "Paula Demo", Consulta odontológica, "Ausente"; miércoles 09:00 "Tomás Prueba", Consulta odontológica, "Reservado", etiqueta "Alta manual"; jueves 11:00 "Julia Ejemplar", Limpieza dental, "Confirmado". Debajo de la grilla, una banda separada titulada "Pre-reservas sin pagar, no ocupan horario", con estilo atenuado y borde punteado, que lista "Sofía Muestra, martes 10:00, Esperando seña". Botón principal "Nuevo turno". No incluir logos, fotos de personas, gráficos, caja ni pagos en línea. Datos 100% ficticios.
```

Stitch reescribió y amplió los dos prompts antes de generar (campo `prompt` de la respuesta).

## Qué se adopta y qué no

**Se adopta:** selector día/semana, navegación con "Hoy", filtros, estado como texto con insignia, lista cronológica a 360 px, grilla por día en escritorio, y la banda separada de pre-reservas con borde punteado.

**Cambio respecto de lo generado:** la pantalla móvil intercaló la pre-reserva de las 10:00 entre un turno de 09:30 a 10:15 y el siguiente, justo el solape visible que US-005 prohíbe. La banda separada de la pantalla de escritorio resuelve eso y se usa en las dos vistas.

**No se adopta, porque Stitch lo agregó sin pedirlo o contradice el proyecto:**
- Marca "DentalCare Admin", buscador, notificaciones, ayuda y navegación a Pacientes, Tratamientos, Facturación, Ajustes y Configuración: esas pantallas no existen en C-08.
- Celdas "Disponible" en la grilla: una celda sin turno no significa que la profesional tenga franja a esa hora.
- "Descartar" y "Asignar sillón" en la pre-reserva, y el texto "Se confirmará automáticamente al registrarse el adelanto": esas acciones no existen y `en_espera → reservado` solo ocurre al acreditar la seña.
- Sillón "Por asignar": todo turno tiene sillón. Nombres "Sillón 1 (Clínica)" y "Tratamiento tentativo": el backend no tiene esos datos.
- Controles de 32 a 40 px y botón fijo sobre una barra inferior: el proyecto exige 48 px y una barra fija oculta contenido a 360x800 (R3, igual que en C-05).
