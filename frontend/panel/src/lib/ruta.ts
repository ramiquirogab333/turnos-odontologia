/** Secciones del panel. La sección activa vive en el hash de la URL (`#/caja`): sin dependencias y sin recargar. */
export const SECCIONES = ['agenda', 'pacientes', 'indicadores', 'caja', 'recordatorios', 'google-calendar', 'datos', 'catalogo'] as const;
export type Seccion = (typeof SECCIONES)[number];

/** La odontóloga ve su agenda y la conexión con su Google Calendar; el resto es de recepción y admin. */
export const SECCIONES_ODONTOLOGA: readonly Seccion[] = ['agenda', 'google-calendar'];

export const TITULO_SECCION: Readonly<Record<Seccion, string>> = {
  agenda: 'Agenda',
  pacientes: 'Pacientes',
  indicadores: 'Indicadores',
  caja: 'Caja',
  recordatorios: 'Recordatorios',
  'google-calendar': 'Google Calendar',
  datos: 'Datos',
  catalogo: 'Catálogo',
};

function esSeccion(valor: string): valor is Seccion {
  return (SECCIONES as readonly string[]).includes(valor);
}

/** Sección del hash (sin su query); todo lo que no sea una sección exacta cae en la agenda. */
export function leerSeccion(hash: string): Seccion {
  if (leerDetallePaciente(hash) !== null) return 'pacientes';
  const candidata = hash.startsWith('#/') ? (hash.slice(2).split('?')[0] ?? '') : '';
  return esSeccion(candidata) ? candidata : 'agenda';
}

export type PestanaPaciente = 'ficha' | 'odontograma' | 'presupuestos' | 'datos';
export const PESTANAS_PACIENTE: readonly PestanaPaciente[] = ['ficha', 'odontograma', 'presupuestos', 'datos'];

export interface DetallePaciente {
  readonly pacienteId: number;
  readonly pestana: PestanaPaciente;
}

const RUTA_DETALLE = /^#\/pacientes\/([1-9][0-9]*)$/;

/** Detalle de un paciente (`#/pacientes/7?pestana=odontograma`); una pestaña inválida abre la ficha. `null` si no es esa ruta. */
export function leerDetallePaciente(hash: string): DetallePaciente | null {
  const [ruta = '', query] = hash.split('?');
  const coincide = RUTA_DETALLE.exec(ruta);
  if (coincide?.[1] === undefined) return null;
  const pedida = query === undefined ? null : new URLSearchParams(query).get('pestana');
  return { pacienteId: Number(coincide[1]), pestana: PESTANAS_PACIENTE.find((p) => p === pedida) ?? 'ficha' };
}

export function hashDePaciente(pacienteId: number, pestana: PestanaPaciente = 'ficha'): string {
  return pestana === 'ficha' ? `#/pacientes/${String(pacienteId)}` : `#/pacientes/${String(pacienteId)}?pestana=${pestana}`;
}

export type ResultadoGoogle = 'conectado' | 'error_autorizacion' | 'permiso_denegado';

/** Resultado de la vuelta de Google (`#/google-calendar?resultado=conectado`), o `null` si no hay uno válido. */
export function resultadoDeGoogle(hash: string): ResultadoGoogle | null {
  const query = hash.split('?')[1];
  if (query === undefined || leerSeccion(hash) !== 'google-calendar') return null;
  const valor = new URLSearchParams(query).get('resultado');
  return valor === 'conectado' || valor === 'error_autorizacion' || valor === 'permiso_denegado' ? valor : null;
}

/** Pestaña de «Datos» del hash (`#/datos?pestana=auditoria`); cualquier otro valor abre la exportación. */
export function pestanaDeDatos(hash: string): 'exportar' | 'auditoria' {
  const query = hash.split('?')[1];
  if (query === undefined || leerSeccion(hash) !== 'datos') return 'exportar';
  return new URLSearchParams(query).get('pestana') === 'auditoria' ? 'auditoria' : 'exportar';
}

export type PestanaCatalogo = 'tratamientos' | 'profesionales' | 'sillones' | 'horarios';
export const PESTANAS_CATALOGO: readonly PestanaCatalogo[] = ['tratamientos', 'profesionales', 'sillones', 'horarios'];

/** Pestaña de «Catálogo» del hash (`#/catalogo?pestana=horarios`); cualquier otro valor abre Tratamientos. */
export function pestanaDeCatalogo(hash: string): PestanaCatalogo {
  const query = hash.split('?')[1];
  if (query === undefined || leerSeccion(hash) !== 'catalogo') return 'tratamientos';
  const valor = new URLSearchParams(query).get('pestana');
  return PESTANAS_CATALOGO.find((p) => p === valor) ?? 'tratamientos';
}

export function irA(seccion: Seccion): void {
  window.location.hash = `#/${seccion}`;
}
