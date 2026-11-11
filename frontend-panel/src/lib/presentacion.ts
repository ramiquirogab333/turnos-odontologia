import { montoExacto } from './formato';
import { etiquetaDiaLarga, horaClinica } from './tiempo';
import type { ConceptoCaja, ErrorCaja, EstadoTurno, MedioCaja, TurnoAgenda } from './tipos';

/** El estado se lee siempre como texto: el color es solo un refuerzo. */
export const ETIQUETA_ESTADO: Readonly<Record<EstadoTurno, string>> = {
  en_espera: 'Esperando seña',
  reservado: 'Reservado',
  confirmado: 'Confirmado',
  cancelado: 'Cancelado',
  ausente: 'Ausente',
  atendido: 'Atendido',
};

/** Estado de la seña como etiqueta corta (la seña devuelta es el estado final de RN-SN-11). */
export const ETIQUETA_ESTADO_SENA: Readonly<Record<string, string>> = {
  pendiente: 'Seña pendiente',
  acreditado: 'Seña acreditada',
  no_reembolsado: 'Seña retenida',
  a_reembolsar: 'Seña a devolver',
  en_revision: 'Seña en revisión',
  vencido: 'Seña vencida',
  reembolsado: 'Seña devuelta',
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
    case 'reembolsado':
      return `Seña devuelta: ${monto}`;
    case 'vencido':
      return 'Seña vencida';
    default:
      return `Seña ${sena.estado}: ${monto}`;
  }
}

// --- Caja (C-12) ------------------------------------------------------------------------------------------------

const MEDIO: Readonly<Record<MedioCaja, string>> = { mercadopago: 'Mercado Pago', transferencia: 'transferencia' };

export function textoMedio(medio: MedioCaja): string {
  return MEDIO[medio];
}

/** "Señas por Mercado Pago", "Devoluciones de señas por transferencia". */
export function etiquetaLinea(concepto: ConceptoCaja, medio: MedioCaja): string {
  switch (concepto) {
    case 'sena':
      return `Señas por ${MEDIO[medio]}`;
    case 'pago_presupuesto':
      return `Cobros de presupuestos por ${MEDIO[medio]}`;
    case 'devolucion_sena':
      return `Devoluciones de señas por ${MEDIO[medio]}`;
  }
}

/** Un movimiento suelto, en singular: "Devolución de seña por transferencia". */
export function etiquetaMovimiento(concepto: ConceptoCaja, medio: MedioCaja): string {
  switch (concepto) {
    case 'sena':
      return `Seña por ${MEDIO[medio]}`;
    case 'pago_presupuesto':
      return `Cobro de presupuesto por ${MEDIO[medio]}`;
    case 'devolucion_sena':
      return `Devolución de seña por ${MEDIO[medio]}`;
  }
}

export type ObjetoDeCaja = 'pago' | 'cierre';

/** Rechazos tras los cuales los datos en pantalla quedaron viejos. */
export const RECARGAN_CAJA: readonly ErrorCaja['tipo'][] = ['estado_cambiado', 'no_encontrado', 'dia_ya_cerrado'];

/** Qué le decimos a recepción cuando la caja, un cierre o un pendiente rechazan el cambio. */
export function mensajeDeCaja(error: ErrorCaja, objeto: ObjetoDeCaja): string {
  switch (error.tipo) {
    case 'caja_cerrada':
      return `La caja ${error.dia !== null ? `del ${etiquetaDiaLarga(error.dia)}` : 'de ese día'} está cerrada. Pedile a un administrador que anule el cierre para poder registrarlo.`;
    case 'dia_no_terminado':
      return error.cerrableDesde !== null
        ? `Todavía no se puede cerrar este día. Probá desde las ${horaClinica(error.cerrableDesde)}.`
        : 'Todavía no se puede cerrar este día.';
    case 'dia_ya_cerrado':
      return 'Este día ya tiene un cierre. Actualizamos la pantalla.';
    case 'estado_cambiado':
      return 'Este pago ya cambió de estado. Actualizamos la lista.';
    case 'no_encontrado':
      return objeto === 'pago' ? 'Ese pago ya no existe. Actualizamos la lista.' : 'Ese cierre ya no existe. Actualizamos la pantalla.';
    case 'validacion':
      return error.mensaje;
    case 'sin_permiso':
      return 'Tu usuario no puede hacer este cambio.';
    case 'reintentar':
      return 'El servidor está ocupado. Probá de nuevo en unos segundos.';
    case 'desconocido':
      return 'No pudimos guardar el cambio. Probá de nuevo; si sigue igual, avisá a la clínica.';
  }
}
