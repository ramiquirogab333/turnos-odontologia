const formatoPesos = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 0,
});

const formatoMontoExacto = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Monto de la seña con centavos. El monto llega como texto decimal; solo se formatea, nunca se opera. */
export function montoExacto(monto: string): string {
  return formatoMontoExacto.format(Number(monto));
}

/** Precio orientativo para mostrar. Solo presentación: nunca se opera con este número. */
export function precioOrientativo(precioBase: string): string {
  return formatoPesos.format(Number(precioBase));
}

const SIN_DATO = '—';
const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

function conMiles(enteros: string): string {
  return enteros.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

/**
 * Importe a texto "$ 3.000,00". Se arma con el texto decimal del servidor (sin pasar por `number`, que perdería
 * centavos en cifras grandes) y los centavos se completan a dos cifras.
 */
export function pesos(monto: string | null): string {
  const partes = monto === null ? null : DECIMAL.exec(monto);
  if (partes === null) return SIN_DATO;
  const [, signo = '', enteros = '0', decimales = ''] = partes;
  return `${signo}$ ${conMiles(enteros)},${decimales.padEnd(2, '0').slice(0, 2)}`;
}

/** Porcentaje a texto "37,5 %": un decimal como máximo y sin ceros de relleno. */
export function porcentaje(valor: string | null): string {
  const partes = valor === null ? null : DECIMAL.exec(valor);
  if (partes === null) return SIN_DATO;
  const [, signo = '', enteros = '0', decimales = ''] = partes;
  const redondeado = Math.round(Number(`0.${decimales || '0'}`) * 10);
  const entero = redondeado === 10 ? String(BigInt(enteros) + 1n) : enteros;
  const decimal = redondeado === 10 ? 0 : redondeado;
  return `${signo}${entero}${decimal === 0 ? '' : `,${String(decimal)}`} %`;
}
