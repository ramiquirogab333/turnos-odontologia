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
