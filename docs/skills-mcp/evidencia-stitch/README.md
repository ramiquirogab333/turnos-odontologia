# Evidencia de uso de Google Stitch MCP (C-05)

Este directorio guarda lo que Stitch devolvió el **2026-11-03**, la primera vez que el servidor se conectó y se usó de verdad en este proyecto. Todos los datos de las pantallas son ficticios (R19).

No se guardó ningún token ni credencial. Las capturas y los HTML se obtuvieron de los enlaces `screenshot` y `htmlCode` que devuelve `get_screen`, y se cotejaron byte a byte contra una descarga directa de esos enlaces (en un HTML del paso 2 se corrigieron 4 líneas de una transcripción previa). Los HTML están tal como los devolvió Stitch (cargan Tailwind, Google Fonts y Material Symbols desde CDN; el frontend real **no** hace esos pedidos).

## Datos de la sesión

| Dato | Valor |
| :--- | :--- |
| Fecha | 2026-11-03 |
| Herramienta invocada | `generate_screen_from_text` (servidor MCP `stitch`, paquete `@_davideast/stitch-mcp`) |
| Parámetros comunes | `projectId: 7294293124768754545`, `deviceType: MOBILE`, sin `modelId`, `designSystem: assets/6f7af57075fc435f8d9c7205e1bcb0b4` (pantallas 2 y 3) |
| Proyecto de Stitch | `7294293124768754545` |
| Sistema de diseño | `assets/6f7af57075fc435f8d9c7205e1bcb0b4`, "Clinical Clarity Dental System" (Stitch lo generó con la pantalla 1) |
| Recuperación de archivos | `get_screen` y `download_file` |

## Pantallas

| # | Título devuelto por Stitch | ID de pantalla | HTML | Captura |
| :-: | :--- | :--- | :--- | :--- |
| 1 | Reserva de Turno - Paso 1: Tratamiento | `projects/7294293124768754545/screens/a455a665633147aeab88c6faaff3d01f` | [paso-1-tratamiento.html](paso-1-tratamiento.html) | [paso-1-tratamiento.png](paso-1-tratamiento.png) (780x2058) |
| 2 | Paso 2 de 3: Elegí día y horario | `projects/7294293124768754545/screens/ae5226ea5cd54eb596fe79f55f5cc239` | [paso-2-dia-y-horario.html](paso-2-dia-y-horario.html) | [paso-2-dia-y-horario.png](paso-2-dia-y-horario.png) (780x2082) |
| 3 | Paso 3 de 3: Tus datos y Confirmación | `projects/7294293124768754545/screens/2da77be023ad468fb39c53641e7ea26a` | [paso-3-tus-datos.html](paso-3-tus-datos.html) | [paso-3-tus-datos.png](paso-3-tus-datos.png) (780x2568) |

Archivos de Stitch de origen: pantalla 1, HTML `projects/7294293124768754545/files/08629ed2ab12427686eee03f77a75a80` y captura `.../files/bac137c644974ae8b1b17b027dffc734`; pantalla 2, HTML `.../files/8397933788a048a69489390860b4e5c3` y captura `.../files/0cce2fb2395a4fd09395c53c79b265a4`; pantalla 3, HTML `.../files/8a1b5cbfdfda49f38aca79622f4ba0d0` y captura `.../files/3eab5b17e7a2402183ec7d47b309498a`.

## Prompts enviados (textuales)

**Pantalla 1.** El prompt no indicaba colores ni tipografías, así que el tema que devolvió Stitch es una comparación independiente de lo que ya tenía el frontend.

```text
Pantalla móvil de 360px de ancho para que un paciente reserve un turno en una clínica odontológica, sin crear cuenta. Tono clínico, calmo y confiable. Todo el texto en español rioplatense. Es el paso 1 de un wizard de 3 pasos: indicador de progreso "Paso 1 de 3" y título "Elegí el tratamiento". Lista de opciones táctiles, de al menos 48px de alto, con nombre, duración en minutos y precio orientativo. Datos ficticios: "Consulta odontológica", 30 min, $15.000; "Limpieza dental", 45 min, $25.000; "Empaste", 45 min, $30.000. Debajo, un selector de profesional con opciones ficticias "Dra. Ana Ficticia" y "Dr. Bruno Ejemplo". Botón principal fijo al alcance del pulgar: "Continuar". Sin scroll horizontal. No incluir logos, fotos de personas, ni pagos.
```

**Pantalla 2.**

```text
Pantalla móvil de 360px de ancho, paso 2 de 3 del wizard de reserva de turno de una clínica odontológica, sin crear cuenta. Indicador de progreso "Paso 2 de 3" y título "Elegí día y horario". Tono clínico, calmo y confiable. Todo el texto en español rioplatense. Una tira de semana que se desliza horizontalmente con los días (por ejemplo lun 9, mar 10, mié 11, jue 12, vie 13) y un día seleccionado. Debajo, una grilla de horarios táctiles de al menos 48px de alto: horarios libres (09:00, 09:30, 10:00, 10:30, 11:00, 11:30) y uno seleccionado. Incluir además un aviso de estado: "Ese horario ya fue tomado. Elegí otro de los libres." con horarios alternativos libres. Botón principal "Continuar". Sin scroll horizontal de la página (solo la tira de días se desliza). No incluir logos, fotos de personas, ni pagos. Datos ficticios.
```

**Pantalla 3.**

```text
Pantalla móvil de 360px de ancho, paso 3 de 3 del wizard de reserva de turno de una clínica odontológica, sin crear cuenta. Indicador "Paso 3 de 3" y título "Tus datos". Tono clínico, calmo y confiable. Todo el texto en español rioplatense. Campos de nombre ("Carlos Sintético") y teléfono ("+5491144445555"), un resumen del turno (tratamiento, profesional, día y horario ficticios), y un estado de error de validación del teléfono que explique qué pasó y cómo corregirlo. Botón principal "Reservar turno". Mostrar además el estado de confirmación posterior: "Turno reservado" con un código de gestión ficticio "TUR-EJEMPLO", sin ningún enlace ni botón de gestión. Sin scroll horizontal. No incluir logos, fotos de personas, ni pagos. Datos 100% ficticios.
```

Stitch reescribió y amplió los prompts de las pantallas 2 y 3 antes de generarlas (campo `prompt` de la respuesta). Esa versión ampliada agregó cosas que **no** pedimos: "Marzo 2025" y "Zona horaria: ART", sede y consultorio, "Dra. Valeria Ramos", "Confirmación inmediata", recordatorios por WhatsApp y SMS, un tratamiento llamado "Limpieza y profilaxis profunda", un mensaje de error de teléfono que pide "sin el 9 inicial" (contradice el propio valor de ejemplo `+5491144445555`) y una "previsualización del estado confirmado". Por eso el frontend no copia los textos de Stitch; ver [`design.md`](../../../openspec/changes/c-05-reserva-publica-horarios/design.md), Decisión 1.

## Tema devuelto por Stitch

Nombre: "Clinical Clarity Dental System". `colorMode: LIGHT`, `colorVariant: FIDELITY`, `roundness: ROUND_EIGHT`, `spacingScale: 2`. Fuente de títulos, cuerpo y etiquetas: Plus Jakarta Sans.

| Rol | Valor |
| :--- | :--- |
| Primario | `#0D5C75` (hover `#0A4659`) |
| Secundario | `#2BB69F` |
| Terciario / texto | `#1B3B48` |
| Lienzo | `#F4F7F6` |
| Superficie | `#FFFFFF` |
| Bordes | `#D8E2E1` y `#B8CBC8` |
| Éxito | `#16806B` |
| Advertencia | `#B76E00` |
| Error | `#B3261E` |
| Botones y campos | 48px de alto |
| Radios | base 8px, tarjeta 16px, modal 24px |
| Tarjeta seleccionada | borde de 2px `#0D5C75`, tinte `rgba(43,182,159,0.05)` |
| Anillo de foco | 3px `#2BB69F`, desfase de 2px |
| Chips de horario | mínimo 40px de alto; seleccionado `#0D5C75` con texto blanco |
| Espaciado | múltiplos de 4px y 8px |

Además el tema trae una paleta Material generada (`primary: #004357`, `primary-container: #0d5c75`, `secondary: #006b5c`, `tertiary: #22424f`, `surface: #f7faf9`, `on-surface: #181c1c`, `error: #ba1a1a`, entre otros). Los HTML generados usan esa paleta Material: en las pantallas 1 y 2 el botón principal es `#004357` (el `primary` Material), y en la pantalla 3 es `#0d5c75` (`primary-container`). Las dos cosas conviven en lo que devolvió Stitch; el frontend adopta `#0D5C75`, que es el valor que el sistema de diseño declara como primario.

El texto completo del tema (`designMd`) viene en la respuesta de `generate_screen_from_text`; no se copia entero acá. También incluye una sección de odontograma, que no se usó.

## Qué no se adoptó y por qué

- "Cualquier profesional disponible": la API de disponibilidad se consulta por un profesional concreto.
- Subtítulos de especialidad por tratamiento ("Revisión clínica", "Profilaxis", "Restauración"), sede y consultorio: el backend no tiene esos datos.
- Textos tranquilizadores sin respaldo (bioseguridad, "Confirmación inmediata", recordatorios por SMS, "Podés cancelar o reprogramar sin cargo hasta 24 h antes").
- Barra de pasos fija en la parte inferior y botón fijo: ocultan contenido a 360x800 (R3).
- Chips de horario de 40px: el proyecto exige 48px (R3).
- Anillo de foco menta `#2BB69F`: da 2,35:1 sobre el lienzo `#F4F7F6`, menos de 3:1; se usa `#0D5C75` con el mismo trazo.
- Código "TUR-EJEMPLO": es ficticio; el backend devuelve un identificador distinto y el frontend muestra el real, sin enlace (el enlace de gestión queda para C-07).
