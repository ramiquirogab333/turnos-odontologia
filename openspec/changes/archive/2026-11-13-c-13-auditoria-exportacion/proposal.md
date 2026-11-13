# Proposal: c-13-auditoria-exportacion

## Why
RN-GL-01 ("toda acción de gestión interna queda registrada: quién, qué, cuándo") y RN-GL-02 ("los datos deben poder exportarse masivamente") son las dos reglas globales que siguen sin cerrar (US-011, US-012; C-11 y C-12 las dejaron explícitamente para C-13). Relevado en el código (HEAD `6dc9e58`, migración `012_sesion_panel`), **la auditoría ya existe pero es parcial y heterogénea**:
- La tabla `registro_auditoria` existe desde la `002` (`usuario_id` FK `ON DELETE SET NULL` indexada, `accion`/`entidad` `TEXT` con `CHECK` 2–50, `entidad_id`, `datos_antes`/`datos_despues` JSONB, `ip`, `created_at timestamptz` indexado). **No es inmutable** (se puede hacer `UPDATE`/`DELETE`) y no tiene índice para filtrar por entidad.
- Se escribe con **~45 llamadas explícitas en la misma transacción del caso de uso**, a través de **siete helpers distintos** (`pacientes.auditoria.auditar` con lista de claves prohibidas, `pagos.service._auditar`, `auth.router._audit`, `catalogo.service._audit`, dos `_auditar` de Google Calendar, `notificaciones.panel._auditar`) y `session.add(...)` sueltos en `panel`, `public`, `gestion`, `barrido` y `usuarios`. Solo el de pacientes impide guardar datos personales.
- Conviven **tres convenciones de `accion`**: verbos CRUD (`CREATE`/`UPDATE`/`DELETE` con el detalle en `datos_despues.origen`, p. ej. `deshacer_atendido_panel`), eventos de auth en mayúsculas (`LOGIN_OK`, `LOGIN_BLOQUEADO`, `SESIONES_REVOCADAS`) y nombres semánticos (`cierre_caja`, `devolucion_sena_registrada`, `lectura_ficha`).
- La `ip` solo la llenan auth y catálogo; el resto guarda `NULL`.
- Quedan **acciones del panel sin rastro**: `POST /api/turnos` (alta interna de C-01) y `POST /api/panel/google-calendar/conexion/iniciar`; y **lecturas de datos personales sin auditar**: `GET /api/panel/pacientes/listado` (pedido explícito de C-12), `GET /api/panel/pacientes?dni=` y `GET /api/panel/pacientes/{id}`.
- **No hay forma de leer la auditoría** ni de exportar nada.

## What Changes
- **Auditoría transversal por llamadas explícitas + contrato de cobertura (O1):** se mantiene el registro explícito en la misma transacción (lo que ya existe) y se agrega un **catálogo de política por ruta** (`semantica` / `lectura` / `exenta` con motivo) verificado por un test de contrato que recorre todas las rutas autenticadas de `/api/panel/*`, `/api/admin/*`, `/api/turnos` y `/api/auth/*`: una ruta nueva sin política hace fallar la suite. Se descarta el middleware HTTP (no conoce la transacción, la entidad ni el antes/después, y rompe el streaming de la exportación).
- **Helper único de auditoría (D2):** `app/plataforma/auditoria.registrar(...)` con la guarda de datos personales de C-11 para todos; los siete helpers pasan a delegar en él **sin cambiar los valores que ya graban** (no se reescribe historia).
- **IP real en todo registro originado en un pedido autenticado (O9)**, tomada una sola vez con `ip_cliente` (C-15).
- **Cierre de brechas (O2, O10):** se auditan el alta interna `POST /api/turnos`, el inicio de conexión con Google Calendar y las lecturas de datos de pacientes (listado, búsqueda por DNI, datos administrativos), **sin guardar el texto buscado**.
- **Registro inmutable (O4):** la migración **`013_auditoria_exportacion`** (reversible, R14) agrega un trigger que rechaza `UPDATE`/`DELETE` sobre `registro_auditoria`, cambia la FK de usuario a `ON DELETE RESTRICT` (los usuarios se desactivan desde C-15, no se borran), un `CHECK` de longitud de `ip` y el índice `(entidad, entidad_id, created_at)`.
- **Consulta de la auditoría (O5, O6, O7):** `GET /api/panel/auditoria` con filtros por entidad, id de entidad, usuario, tipo de acción y rango de fechas; paginación por cursor; cada fila trae un **tipo legible** derivado de `accion` + `origen` que cubre las acciones de C-12 (cierre y anulación de caja, devolución de seña y de excedente, rechazo de una revisión, `deshacer_atendido`, lectura del listado de pacientes).
- **Exportación masiva (O8, O11–O15):** `GET /api/panel/export?entidad=turnos|pacientes|cierres_caja&formato=csv` en **streaming** (cursor del servidor, sin cargar todo en memoria ni bloquear el loop, R16), instantáneas consistentes, columnas mínimas sin datos clínicos ni secretos (nunca `codigo_gestion`), **neutralización de fórmulas CSV** en texto libre, y **cada exportación queda auditada antes del primer byte**. Límite de exportaciones por usuario con el limitador de C-15 (429).
- **Panel (O3), 360 px (R3):** sección **"Datos"** con exportación (turnos, pacientes, cierres de caja con rango de fechas) y la vista de auditoría con filtros, según rol.
- **Decisiones abiertas O1–O16** en `design.md`, cada una con opciones y una recomendada. **Todas PENDIENTES** de aprobación del usuario (governance CRÍTICO: no se escribe código hasta aprobarlas).

## Capabilities

### New Capabilities
- `plataforma/auditoria`: registro transversal de las acciones del panel (quién, qué, cuándo, desde dónde), política de auditoría por ruta con contrato de cobertura, inmutabilidad, catálogo de tipos legibles y consulta filtrada con permisos; pantalla de auditoría.
- `plataforma/exportacion-datos`: exportación tabular masiva (turnos, pacientes, cierres de caja) en CSV por streaming, con minimización de columnas, neutralización de fórmulas, auditoría de cada exportación, permisos y límite de uso; pantalla de exportación.

### Modified Capabilities
- `pacientes/registro-paciente`: el listado, la búsqueda por DNI y la consulta de datos administrativos de un paciente pasan a quedar auditados (sin el texto buscado ni datos personales en el registro).
- `turnos/creacion-sin-solape`: el alta interna `POST /api/turnos` deja registro de auditoría en la misma transacción.
- `integraciones/google-calendar`: iniciar la conexión con Google deja registro de auditoría.
- `dominio/modelos-core`: `RegistroAuditoria` pasa a ser de solo agregado, con FK de usuario `RESTRICT`, IP acotada e índice por entidad.

## Impact
- **Backend:** nuevo `app/plataforma/` (`auditoria.py` helper + catálogo de tipos + política por ruta; `router_auditoria.py`; `exportacion.py` + `router_exportacion.py`; esquemas Pydantic), `app/auth/rbac.py` (la IP del pedido queda disponible para la auditoría), los siete helpers existentes delegan en el central, `app/turnos/` (auditoría del alta), `app/integraciones/gcal/oauth.py`, `app/pacientes/` (lecturas auditadas), `app/main.py` (routers nuevos), `app/shared/settings.py` (límites de exportación).
- **API:** nuevos `GET /api/panel/auditoria`, `GET /api/panel/export` y `GET /api/panel/usuarios` (directorio mínimo para el filtro, solo admin, sujeto a O3). Sin cambios de forma en respuestas existentes; las lecturas de pacientes ahora escriben auditoría (si la escritura falla, la lectura responde 500 sin datos).
- **Base de datos:** migración `013_auditoria_exportacion` (verificar el número antes del apply: C-14 puede ir en paralelo). **BREAKING (operativo):** borrar un usuario con auditoría pasa a ser imposible (se desactiva); `UPDATE`/`DELETE` sobre la auditoría falla. Los tests limpian la tabla con `TRUNCATE`.
- **Frontend:** `frontend/panel` (sección "Datos": exportación y auditoría; descarga con `fetch` autenticado + `Blob`).
- **Docs/KB:** `04_modelo_de_datos.md` (RegistroAuditoria real), `03_actores_y_roles.md` (quién lee auditoría y quién exporta qué, según O6/O7), `08_arquitectura_propuesta.md` (variables `EXPORT_*`), `05_reglas_de_negocio.md` (precisiones de RN-GL-01/02), README (cómo abrir el CSV).
- **Fuera de alcance:** exportación de datos clínicos (ficha, odontograma, presupuestos), exportación en XLSX/JSON, exportaciones asíncronas con archivo guardado, retención/purga de la auditoría (supuesto abierto, O16), firma o encadenamiento criptográfico de registros, auditoría de lecturas de la agenda y de agregados sin personas (indicadores, caja, catálogo), reescritura de los registros históricos.
