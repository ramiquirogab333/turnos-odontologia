/**
 * Minutos de espera que informa un 429 (C-15, D10): `Retry-After` viene en segundos.
 * Ausente, no numérico, cero, negativo o hasta 60 s → 1 minuto; si no, redondeo hacia arriba.
 */
export function minutosDesdeRetryAfter(cabecera: string | null): number {
  if (cabecera === null || !/^\d+$/.test(cabecera.trim())) return 1;
  const segundos = Number(cabecera.trim());
  return segundos <= 60 ? 1 : Math.ceil(segundos / 60);
}

/** Mensaje al paciente cuando la API limita los pedidos (reserva, seña, horarios y gestión). */
export function mensajeLimite(cabecera: string | null): string {
  const minutos = minutosDesdeRetryAfter(cabecera);
  return `Hiciste muchos pedidos seguidos. Probá de nuevo en ${String(minutos)} ${minutos === 1 ? 'minuto' : 'minutos'}.`;
}
