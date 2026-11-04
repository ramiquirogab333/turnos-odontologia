const formatoPesos = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 0,
});

/** Precio orientativo para mostrar. Solo presentación: nunca se opera con este número. */
export function precioOrientativo(precioBase: string): string {
  return formatoPesos.format(Number(precioBase));
}
