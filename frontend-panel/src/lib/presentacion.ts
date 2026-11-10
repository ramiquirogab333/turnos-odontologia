import { montoExacto } from './formato';
import type { EstadoTurno, TurnoAgenda } from './tipos';

/** El estado se lee siempre como texto: el color es solo un refuerzo. */
export const ETIQUETA_ESTADO: Readonly<Record<EstadoTurno, string>> = {
  en_espera: 'Esperando seña',
  reservado: 'Reservado',
  confirmado: 'Confirmado',
  cancelado: 'Cancelado',
  ausente: 'Ausente',
  atendido: 'Atendido',
};

/** Qué pasa con la seña del turno, en una frase que recepción puede leer de un vistazo. */
export function textoSena(turno: Pick<TurnoAgenda, 'sena' | 'origen' | 'estado'>): string | null {
  const { sena } = turno;
  if (sena === null) {
    if (turno.origen === 'manual') return 'Alta manual, sin seña';
    return turno.estado === 'en_espera' ? null : 'Sin seña';
  }
  const monto = montoExacto(sena.monto);
  switch (sena.estado) {
    case 'acreditado':
      return `Seña acreditada: ${monto}`;
    case 'no_reembolsado':
      return `Seña retenida: ${monto}`;
    case 'a_reembolsar':
      return `Seña a devolver: ${monto}`;
    case 'pendiente':
      return `Seña pendiente: ${monto}`;
    case 'en_revision':
      return `Seña en revisión: ${monto}`;
    case 'vencido':
      return 'Seña vencida';
    default:
      return `Seña ${sena.estado}: ${monto}`;
  }
}
