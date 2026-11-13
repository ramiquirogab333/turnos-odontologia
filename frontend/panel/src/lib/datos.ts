/** Lógica pura de la sección «Datos» (C-13): permisos por rol, parámetros de la exportación y textos. Sin I/O. */
import type {
  ConsultaAuditoria,
  EntidadExportable,
  ErrorExportacion,
  ParametrosExportacion,
  Rol,
  UsuarioAuditoria,
} from './tipos';

export interface OpcionExportacion {
  readonly entidad: EntidadExportable;
  readonly etiqueta: string;
}

const TURNOS: OpcionExportacion = { entidad: 'turnos', etiqueta: 'Turnos' };
const PACIENTES: OpcionExportacion = { entidad: 'pacientes', etiqueta: 'Pacientes' };
const CIERRES: OpcionExportacion = { entidad: 'cierres_caja', etiqueta: 'Cierres de caja' };

/** Qué puede exportar cada rol (O7): recepción turnos y cierres; solo el admin, pacientes; la odontóloga, nada. */
export function opcionesSegunRol(roles: readonly Rol[]): readonly OpcionExportacion[] {
  if (roles.includes('admin')) return [TURNOS, PACIENTES, CIERRES];
  if (roles.includes('recepcion')) return [TURNOS, CIERRES];
  return [];
}

export function puedeVerDatos(roles: readonly Rol[]): boolean {
  return roles.includes('admin') || roles.includes('recepcion');
}

/** La auditoría es solo del admin (O6). */
export function puedeVerAuditoria(roles: readonly Rol[]): boolean {
  return roles.includes('admin');
}

/** Query string de `GET /api/panel/export`: el rango es opcional e `incluir_inactivos` solo aplica a pacientes. */
export function parametrosExportacion(p: ParametrosExportacion): string {
  const q = new URLSearchParams({ entidad: p.entidad, formato: 'csv' });
  if (p.desde !== null && p.desde !== '') q.set('desde', p.desde);
  if (p.hasta !== null && p.hasta !== '') q.set('hasta', p.hasta);
  if (p.entidad === 'pacientes' && p.incluirInactivos) q.set('incluir_inactivos', 'true');
  return q.toString();
}

const NOMBRE_SEGURO = /^[A-Za-z0-9_-]+\.csv$/;

/** Nombre del archivo desde `Content-Disposition`; sin cabecera o con un nombre dudoso, `entidad_fecha.csv`. */
export function nombreArchivo(contentDisposition: string | null, entidad: EntidadExportable, hoy: string): string {
  const respaldo = `${entidad}_${hoy}.csv`;
  const nombre = contentDisposition === null ? undefined : /filename="([^"]*)"/.exec(contentDisposition)?.[1];
  return nombre !== undefined && NOMBRE_SEGURO.test(nombre) ? nombre : respaldo;
}

export function etiquetaActor(usuario: UsuarioAuditoria | null): string {
  return usuario === null ? 'Sistema / paciente' : usuario.nombre_completo;
}

export function mensajeDeExportacion(error: ErrorExportacion): string {
  switch (error.tipo) {
    case 'sin_permiso':
      return 'No tenés permiso para exportar esto.';
    case 'limite':
      return `Hiciste muchas exportaciones seguidas. Probá de nuevo en ${String(error.minutos)} ${error.minutos === 1 ? 'minuto' : 'minutos'}.`;
    case 'validacion':
      return 'Revisá el rango de fechas.';
    case 'servidor':
      return 'No pudimos preparar el archivo. Probá de nuevo en un rato.';
    case 'red':
      return 'No pudimos conectarnos. Revisá tu conexión e intentá de nuevo.';
  }
}

/** Query string de `GET /api/panel/auditoria`: solo los filtros con valor. */
export function consultaAuditoriaAQuery(c: ConsultaAuditoria): string {
  const q = new URLSearchParams();
  const texto = (clave: string, valor: string | null): void => {
    const limpio = valor?.trim() ?? '';
    if (limpio !== '') q.set(clave, limpio);
  };
  texto('desde', c.desde);
  texto('hasta', c.hasta);
  if (c.usuarioId !== null) q.set('usuario_id', String(c.usuarioId));
  texto('tipo', c.tipo);
  texto('entidad', c.entidad);
  texto('entidad_id', c.entidadId);
  texto('cursor', c.cursor);
  return q.toString();
}

/** Tipos para filtrar la auditoría (códigos del catálogo del servidor, C-13 D5). */
export const TIPOS_AUDITORIA: readonly { readonly codigo: string; readonly etiqueta: string }[] = [
  { codigo: 'cierre_caja', etiqueta: 'Cierre de caja' },
  { codigo: 'anulacion_cierre_caja', etiqueta: 'Anulación de cierre de caja' },
  { codigo: 'devolucion_sena', etiqueta: 'Devolución de seña' },
  { codigo: 'devolucion_excedente', etiqueta: 'Devolución de excedente' },
  { codigo: 'rechazo_revision_sena', etiqueta: 'Rechazo de revisión de seña' },
  { codigo: 'deshacer_atendido', etiqueta: 'Corrección de atendido' },
  { codigo: 'marcado_ausente', etiqueta: 'Turno marcado ausente' },
  { codigo: 'marcado_atendido', etiqueta: 'Turno marcado atendido' },
  { codigo: 'alta_manual', etiqueta: 'Alta manual de turno' },
  { codigo: 'alta_turno_interna', etiqueta: 'Alta interna de turno' },
  { codigo: 'lectura_listado_pacientes', etiqueta: 'Lectura del listado de pacientes' },
  { codigo: 'busqueda_paciente_dni', etiqueta: 'Búsqueda de paciente por DNI' },
  { codigo: 'lectura_paciente', etiqueta: 'Lectura de datos de un paciente' },
  { codigo: 'exportacion', etiqueta: 'Exportación de datos' },
  { codigo: 'lectura_auditoria', etiqueta: 'Consulta de auditoría' },
  { codigo: 'login_ok', etiqueta: 'Ingreso al panel' },
  { codigo: 'login_failed', etiqueta: 'Ingreso fallido' },
  { codigo: 'otro', etiqueta: 'Otro' },
];
