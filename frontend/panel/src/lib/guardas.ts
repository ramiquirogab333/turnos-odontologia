/** Guardas de tipo para respuestas JSON desconocidas (R1: sin `any` ni aserciones ciegas). */

export type Registro = Readonly<Record<string, unknown>>;

export function esRegistro(valor: unknown): valor is Registro {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

export function esTexto(valor: unknown): valor is string {
  return typeof valor === 'string';
}

export function esNumero(valor: unknown): valor is number {
  return typeof valor === 'number' && Number.isFinite(valor);
}
