import { combinacionValida } from './odontograma';
import { ZONA_CLINICA } from './tiempo';
import type { CobroRegistrado, ErrorClinico, EstadoPresupuesto, LineaNueva, Presupuesto } from './tipos';

export const ETIQUETA_PRESUPUESTO: Readonly<Record<EstadoPresupuesto, string>> = {
  borrador: 'Borrador',
  presentado: 'Presentado',
  aceptado: 'Aceptado',
  rechazado: 'Rechazado',
  anulado: 'Anulado',
};

export type AccionDisponible = 'editar' | 'presentar' | 'aceptar' | 'rechazar' | 'anular' | 'registrar_cobro';

/** Qué se puede hacer con un presupuesto según su estado (RN-PG-05); los estados finales no ofrecen nada. */
export function accionesDe(estado: EstadoPresupuesto): readonly AccionDisponible[] {
  switch (estado) {
    case 'borrador':
      return ['editar', 'presentar', 'anular'];
    case 'presentado':
      return ['aceptar', 'rechazar', 'anular'];
    case 'aceptado':
      return ['registrar_cobro', 'anular'];
    case 'rechazado':
    case 'anulado':
      return [];
  }
}

export const MAX_LINEAS = 50;

export interface ErroresDeLineas {
  readonly general: string | null;
  readonly porLinea: readonly (string | null)[];
}

/** Igual que `PresupuestoCreate` del servidor (1–50 líneas, cantidad 1–99, la cara exige la pieza); el servidor sigue siendo la barrera. */
export function validarLineas(lineas: readonly LineaNueva[]): ErroresDeLineas {
  const general = lineas.length === 0 ? 'Agregá al menos una línea' : lineas.length > MAX_LINEAS ? 'Un presupuesto admite hasta 50 líneas' : null;
  const porLinea = lineas.map((l): string | null => {
    if (!Number.isInteger(l.cantidad) || l.cantidad < 1 || l.cantidad > 99) return 'La cantidad va de 1 a 99';
    if (l.cara !== null && l.pieza === null) return 'La cara exige indicar la pieza';
    if (l.pieza !== null && !combinacionValida(l.pieza, null, 'sano')) return 'La pieza no es válida (11 a 48 o 51 a 85)';
    return null;
  });
  return { general, porLinea };
}

// --- importes: siempre texto decimal, operados en centavos enteros (nunca `number`) ----------------------------

const CENTAVOS = /^(\d+)(?:\.(\d{1,2}))?$/;

function aCentavos(monto: string): bigint | null {
  const m = CENTAVOS.exec(monto);
  if (m?.[1] === undefined) return null;
  return BigInt(m[1]) * 100n + BigInt((m[2] ?? '').padEnd(2, '0'));
}

function deCentavos(c: bigint): string {
  const negativo = c < 0n;
  const abs = negativo ? -c : c;
  return `${negativo ? '-' : ''}${(abs / 100n).toString()}.${(abs % 100n).toString().padStart(2, '0')}`;
}

/** «1000», «1000,5» o «2500.25» a «1000.00», «1000.50», «2500.25»; `null` si no es un importe de a lo sumo dos decimales. */
export function normalizarMonto(texto: string): string | null {
  const limpio = texto.trim().replace(',', '.');
  const c = aCentavos(limpio);
  return c === null ? null : deCentavos(c);
}

export function restarMontos(a: string, b: string): string {
  return deCentavos((aCentavos(a) ?? 0n) - (aCentavos(b) ?? 0n));
}

const conMiles = (enteros: string): string => enteros.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

/** «$ 2.500» sin decimales cuando son cero, «$ 1.500,50» con ellos (R4: se arma desde el texto, no desde `number`). */
export function pesosCompactos(monto: string): string {
  const c = aCentavos(monto);
  if (c === null) return '—';
  const enteros = conMiles((c / 100n).toString());
  const centavos = c % 100n;
  return centavos === 0n ? `$ ${enteros}` : `$ ${enteros},${centavos.toString().padStart(2, '0')}`;
}

export interface CamposCobro {
  readonly monto: string;
  readonly saldo: string;
  readonly referencia: string;
}

/** Error por campo del cobro (monto mayor que 0 y hasta el saldo, referencia de hasta 64). */
export function validarCobro({ monto, saldo, referencia }: CamposCobro): { readonly monto: string | null; readonly referencia: string | null } {
  const normal = normalizarMonto(monto);
  const c = normal === null ? null : aCentavos(normal);
  const tope = aCentavos(saldo);
  let errorMonto: string | null = null;
  if (c === null) errorMonto = 'Escribí el monto con números, por ejemplo 1500 o 1500,50';
  else if (c <= 0n) errorMonto = 'El monto tiene que ser mayor que 0';
  else if (tope !== null && c > tope) errorMonto = `El monto supera el saldo. El saldo actual es ${pesosCompactos(saldo)}`;
  return { monto: errorMonto, referencia: referencia.trim().length > 64 ? 'La referencia admite hasta 64 caracteres' : null };
}

/** Motivo de una anulación: de 3 a 300 caracteres. */
export function validarMotivo(texto: string): string | null {
  const n = texto.trim().length;
  if (n < 3) return 'Escribí al menos 3 caracteres';
  if (n > 300) return 'El motivo admite hasta 300 caracteres';
  return null;
}

export function mensajeDeErrorPresupuesto(error: ErrorClinico): string {
  switch (error.tipo) {
    case 'obra_social_inactiva':
      return 'Esa obra social ya no está activa. Elegí otra o «Sin obra social»';
    case 'presupuesto_no_editable':
      return 'Este presupuesto ya fue presentado y no se puede editar';
    case 'transicion_invalida':
      return 'El presupuesto cambió de estado mientras lo mirabas';
    case 'presupuesto_con_pagos':
      return 'No se puede anular un presupuesto con cobros registrados. Anulá antes los cobros';
    case 'presupuesto_no_aceptado':
      return 'Solo se pueden registrar cobros en un presupuesto aceptado';
    case 'monto_excede_saldo':
      return error.saldo === null ? 'El monto supera el saldo.' : `El monto supera el saldo. El saldo actual es ${pesosCompactos(error.saldo)}`;
    case 'referencia_duplicada':
      return 'Ya hay un cobro registrado con esa referencia';
    case 'caja_cerrada':
      return 'La caja de ese día está cerrada. Un admin tiene que anular el cierre para registrar este cobro';
    case 'sin_permiso':
      return 'Tu usuario no puede hacer este cambio.';
    case 'no_encontrado':
      return 'Ese presupuesto ya no existe. Actualizamos la lista.';
    case 'validacion':
      return error.mensaje;
    default:
      return 'No pudimos completar la acción. Revisá tu conexión e intentá de nuevo.';
  }
}

const formatoOffset = new Intl.DateTimeFormat('en-US', { timeZone: ZONA_CLINICA, timeZoneName: 'longOffset' });

/** Offset de la clínica en un instante, como «-03:00» (de `GMT-03:00`). */
function offsetClinica(instante: Date): string {
  const nombre = formatoOffset.formatToParts(instante).find((p) => p.type === 'timeZoneName')?.value ?? 'GMT';
  const m = /GMT([+-]\d{2}:\d{2})/.exec(nombre);
  return m?.[1] ?? '+00:00';
}

/**
 * Fecha de cobro a enviar: hoy se omite (el servidor usa su reloj); un día pasado va como las 12:00 de ese día en la
 * clínica con offset explícito, para que caiga en el día de caja elegido (O14).
 *
 * @throws RangeError si el día es posterior a hoy (el formulario no lo deja elegir).
 */
export function fechaCobroParaEnviar(hoy: string, elegida: string): string | undefined {
  if (elegida === hoy) return undefined;
  if (elegida > hoy) throw new RangeError('La fecha de cobro no puede ser futura');
  const mediodia = new Date(`${elegida}T12:00:00Z`);
  return `${elegida}T12:00:00${offsetClinica(mediodia)}`;
}

/** El presupuesto con el cobro registrado o anulado aplicado (el servidor devuelve el pago y los totales nuevos). */
export function aplicarCobro(presupuesto: Presupuesto, cobro: CobroRegistrado): Presupuesto {
  const existe = presupuesto.pagos.some((p) => p.id === cobro.pago.id);
  const pagos = existe ? presupuesto.pagos.map((p) => (p.id === cobro.pago.id ? cobro.pago : p)) : [...presupuesto.pagos, cobro.pago];
  return { ...presupuesto, pagos, total_pagado: cobro.total_pagado, saldo: cobro.saldo };
}
