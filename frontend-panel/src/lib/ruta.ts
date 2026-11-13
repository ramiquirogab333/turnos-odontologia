/** Secciones del panel. La sección activa vive en el hash de la URL (`#/caja`): sin dependencias y sin recargar. */
export const SECCIONES = ['agenda', 'pacientes', 'indicadores', 'caja', 'recordatorios', 'google-calendar'] as const;
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
};

function esSeccion(valor: string): valor is Seccion {
  return (SECCIONES as readonly string[]).includes(valor);
}

/** Sección del hash (sin su query); todo lo que no sea una sección exacta cae en la agenda. */
export function leerSeccion(hash: string): Seccion {
  const candidata = hash.startsWith('#/') ? (hash.slice(2).split('?')[0] ?? '') : '';
  return esSeccion(candidata) ? candidata : 'agenda';
}

export type ResultadoGoogle = 'conectado' | 'error_autorizacion' | 'permiso_denegado';

/** Resultado de la vuelta de Google (`#/google-calendar?resultado=conectado`), o `null` si no hay uno válido. */
export function resultadoDeGoogle(hash: string): ResultadoGoogle | null {
  const query = hash.split('?')[1];
  if (query === undefined || leerSeccion(hash) !== 'google-calendar') return null;
  const valor = new URLSearchParams(query).get('resultado');
  return valor === 'conectado' || valor === 'error_autorizacion' || valor === 'permiso_denegado' ? valor : null;
}

export function irA(seccion: Seccion): void {
  window.location.hash = `#/${seccion}`;
}
