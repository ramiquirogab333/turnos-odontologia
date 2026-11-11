/** Secciones del panel. La sección activa vive en el hash de la URL (`#/caja`): sin dependencias y sin recargar. */
export const SECCIONES = ['agenda', 'pacientes', 'indicadores', 'caja'] as const;
export type Seccion = (typeof SECCIONES)[number];

export const TITULO_SECCION: Readonly<Record<Seccion, string>> = {
  agenda: 'Agenda',
  pacientes: 'Pacientes',
  indicadores: 'Indicadores',
  caja: 'Caja',
};

function esSeccion(valor: string): valor is Seccion {
  return (SECCIONES as readonly string[]).includes(valor);
}

/** Sección del hash; todo lo que no sea una sección exacta cae en la agenda. */
export function leerSeccion(hash: string): Seccion {
  const candidata = hash.startsWith('#/') ? hash.slice(2) : '';
  return esSeccion(candidata) ? candidata : 'agenda';
}

export function irA(seccion: Seccion): void {
  window.location.hash = `#/${seccion}`;
}
