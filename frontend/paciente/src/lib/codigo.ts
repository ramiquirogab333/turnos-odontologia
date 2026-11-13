/**
 * El código de gestión llega en el fragmento (`/gestionar#<código>`, `/confirmar#<código>`): el fragmento no viaja al
 * servidor ni queda en sus logs. Se lee una vez y se saca de la URL para que no se copie ni quede en el historial.
 */
export function leerCodigoDelHash(): string | null {
  const crudo = window.location.hash.replace(/^#/, '');
  if (crudo === '') return null;
  try {
    return decodeURIComponent(crudo).trim() || null;
  } catch {
    return crudo.trim() || null;
  }
}

/** Quita el fragmento de la barra de direcciones sin recargar ni agregar una entrada al historial. */
export function sacarCodigoDeLaUrl(): void {
  if (window.location.hash !== '') window.history.replaceState(null, '', window.location.pathname + window.location.search);
}
