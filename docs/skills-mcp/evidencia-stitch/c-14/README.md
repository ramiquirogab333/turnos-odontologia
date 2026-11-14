# Evidencia de uso de Google Stitch MCP (C-14)

Lo que Stitch devolvió el **2026-11-14** para la sección "Catálogo" del panel (tratamientos y horarios de atención). Todos los datos de las pantallas son ficticios (R19). No se guardó ningún token ni credencial.

Las capturas son los bytes que devolvió `download_file`, decodificados desde base64 con un script (se verificó la firma PNG). **El HTML no se guardó en este directorio:** la herramienta lo devuelve en la conversación y copiarlo a mano habría sido una transcripción, no el original. Se puede recuperar con `download_file` y los identificadores de abajo.

## Datos de la sesión

| Dato | Valor |
| :--- | :--- |
| Fecha | 2026-11-14 |
| Herramienta | `generate_screen_from_text` (servidor MCP `stitch`) |
| Parámetros comunes | `projectId: 7294293124768754545`, `deviceType: MOBILE`, sin `modelId`, `designSystem: assets/6f7af57075fc435f8d9c7205e1bcb0b4` |
| Proyecto | `7294293124768754545`, el de C-05 y C-08: se reutilizó para conservar el sistema "Clinical Clarity Dental System" |
| Verificación previa | `get_project` respondió bien (proyecto `PRIVATE`, rol `OWNER`) |
| Recuperación | `get_screen` y `download_file` |

## Pantallas

| # | Título (de Stitch) | `deviceType` | ID de pantalla | Captura | HTML en Stitch |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 1 | Catálogo - Tratamientos | `MOBILE` | `projects/7294293124768754545/screens/a23de3d83bf045a4898af512f50b2701` | [catalogo-tratamientos-360.png](catalogo-tratamientos-360.png) (780x2814; archivo `projects/7294293124768754545/files/e338b77d56024d7d814ddc3b3b89d405`) | `projects/7294293124768754545/files/c4f35239c6d24ee79320ee33dcca3690` |
| 2 | Catálogo - Horarios de atención | `MOBILE` | `projects/7294293124768754545/screens/1f96eb576a644329a4c6e308e9b909fe` | [catalogo-horarios-360.png](catalogo-horarios-360.png) (780x3468; archivo `projects/7294293124768754545/files/92e8722a083144368840f30defefebc5`) | `projects/7294293124768754545/files/c6b8dd745a42433788ef13c07f5cd22b` |

No se generó variante de escritorio: a 1280 px la sección reutiliza el diseño de lista de las demás secciones del panel (ver `design.md` §D9).

## Prompts enviados (textuales)

**Pantalla 1.**

```text
Pantalla móvil de 360px de ancho del panel interno de una clínica odontológica: sección "Catálogo", pestaña "Tratamientos", para recepción. Tono clínico, calmo y confiable. Todo el texto en español rioplatense, en sentence case, sin mayúsculas sostenidas. Arriba, un selector de pestañas: "Tratamientos" (activa), "Profesionales", "Sillones" y "Horarios". Debajo, el botón principal "Agregar tratamiento". Una lista de tratamientos, cada fila de al menos 48px de alto con nombre, duración en minutos, precio base en pesos y un estado con texto ("Activo" o "Inactivo"), sin depender solo del color, y un botón "Editar". Datos ficticios: "Consulta odontológica", 30 min, $ 12.000, Activo; "Limpieza dental", 45 min, $ 18.500, Activo; "Empaste", 60 min, $ 25.000, Activo; "Blanqueamiento de prueba", 90 min, $ 0, Activo, con la nota "Sin seña"; "Ortodoncia demo", 30 min, $ 15.000, Inactivo, con estilo atenuado y la nota "No se ofrece para reservar". Debajo de la lista, un formulario de edición abierto para "Limpieza dental" con los campos "Nombre", "Duración (minutos)" y "Precio base", el aviso "El cambio de duración solo vale para turnos nuevos: los turnos ya tomados conservan su horario", y los botones "Guardar cambios", "Desactivar" y "Cancelar". Sin scroll horizontal. No incluir logos, fotos de personas, gráficos, caja ni pagos en línea. Datos 100% ficticios.
```

**Pantalla 2.**

```text
Pantalla móvil de 360px de ancho del panel interno de una clínica odontológica: sección "Catálogo", pestaña "Horarios", editor de la disponibilidad semanal de una profesional, para recepción. Tono clínico, calmo y confiable. Todo el texto en español rioplatense, en sentence case, sin mayúsculas sostenidas. Arriba, un selector de pestañas: "Tratamientos", "Profesionales", "Sillones" y "Horarios" (activa). Debajo, un selector de profesional con "Dra. Ana Ficticia". Luego una lista vertical por día de la semana, de lunes a domingo; cada día muestra sus franjas horarias como filas de al menos 48px con hora de inicio y fin, el sillón preferido y un estado con texto, más un botón "Agregar franja" por día. Datos ficticios: lunes 09:00 a 13:00, Sillón 1, Activa; lunes 14:00 a 18:00, Sillón 2, Activa; martes sin franjas, con el texto "Sin atención este día"; miércoles 09:00 a 13:00, Sillón 1, Activa; jueves 15:00 a 19:00, sin sillón preferido, "Pausada", con estilo atenuado y la nota "No se ofrecen turnos"; viernes 09:00 a 12:00, Sillón 1, Activa; sábado y domingo "Sin atención este día". Un diálogo de confirmación abierto sobre la franja del lunes 14:00 a 18:00 con el título "Quitar franja", el texto "Hay 3 turnos tomados en esta franja en las próximas semanas. No se cancelan: siguen en la agenda. Los pacientes nuevos ya no van a poder reservar en este horario." y los botones "Quitar franja" y "Volver". Sin scroll horizontal. No incluir logos, fotos de personas, gráficos, caja ni pagos en línea. Datos 100% ficticios.
```

Stitch reescribió y amplió los dos prompts antes de generar (campo `prompt` de la respuesta): en la pantalla 2 agregó por su cuenta una barra inferior "Agenda / Pacientes / Catálogo / Ajustes" y el título "Catálogo DentalCare".

## Qué se adopta y qué no

**Se adopta:** pestañas Tratamientos / Profesionales / Sillones / Horarios; botón principal arriba de la lista; estado como texto con insignia ("Activo", "Inactivo", "Pausada") además del color; fila inactiva atenuada con la nota "No se ofrece para reservar"; la nota "Sin seña" para precio 0 (RN-SN-06); aviso de que la duración nueva solo vale para turnos nuevos; editor de horarios con selector de profesional y un bloque por día con "Sin atención este día" y "Agregar franja"; diálogo de confirmación que dice cuántos turnos tomados hay y que no se cancelan.

**No se adopta, porque Stitch lo agregó sin pedirlo o contradice el proyecto:**
- Marca "Catálogo DentalCare", ícono de diente, buscador, "Filtrar" y la barra inferior "Agenda / Pacientes / Catálogo / Ajustes": el panel ya tiene su cabecera y su navegación por secciones (hash), y no existe una sección "Ajustes". Una barra fija oculta contenido a 360x800 (R3, igual que en C-05 y C-08).
- Etiquetas en mayúsculas "RECEPCIÓN CLÍNICA" y "EN EDICIÓN" y el texto de contexto "Gestión de prestaciones...": la guía de diseño prohíbe mayúsculas sostenidas y etiquetas decorativas.
- Insignia "ID: #042": el id interno no le sirve a recepción.
- Botón "Abierto" en la fila en edición y "$ 0 (Sin costo)": se usa "Editar" siempre y "Sin seña", que es lo que cambia para la reserva.
- "¿Buscás una prestación fuera de catálogo? Crear prestación manual": no existe; todo turno usa un tratamiento del catálogo (RN-TU-04).
- El nombre de la prestación como etiqueta ("Nombre de la prestación"): se usa "Nombre", igual que en el resto del panel.
- En horarios: avatar de la profesional, "Odontología General", "Cambiar" y "Configuración de agenda": se usa un `select` nativo de profesional sin foto; la especialidad no hace falta para editar horarios.
- Botones "Editar" y "Quitar" de unos 32 px dentro de cada franja: el proyecto exige 48 px; las acciones pasan a una fila propia o a un menú de la franja.
- Pestañas que no entran a 360 px ("Horarios" quedó cortada, scroll horizontal): las cuatro pestañas se distribuyen en dos filas o con texto que entra, sin desborde.
- Contadores "2 franjas activas" por día: no se agregan en v1 (información redundante con la lista).
- Fondo desenfocado detrás del diálogo: se usa el `Dialogo` existente del panel.

El frontend **no copia los textos de Stitch tal cual**: la pantalla real usa los tokens y componentes existentes de `frontend/panel` (`estilos.css`, `Dialogo`, `selector`) y los textos definidos en los specs de C-14.
