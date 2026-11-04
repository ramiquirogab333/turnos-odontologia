import type { Slot } from './tipos';

const E164 = /^\+[1-9]\d{1,14}$/;
const MAX_NOMBRE = 200;

export const EJEMPLO_TELEFONO = '+5491144445555';

/** Quita separadores habituales (espacios, guiones, paréntesis, puntos). No agrega prefijo. */
export function normalizarTelefono(valor: string): string {
  return valor.replace(/[\s\-().]/g, '');
}

/** `null` si es válido; si no, el mensaje que explica cómo corregirlo. */
export function validarTelefono(valor: string): string | null {
  if (E164.test(normalizarTelefono(valor))) return null;
  return `Ingresá el teléfono con + y código de país, por ejemplo ${EJEMPLO_TELEFONO}.`;
}

export function validarNombre(valor: string): string | null {
  const largo = valor.trim().length;
  if (largo === 0) return 'Ingresá tu nombre completo.';
  if (largo > MAX_NOMBRE) return `El nombre admite hasta ${String(MAX_NOMBRE)} caracteres.`;
  return null;
}

export interface EstadoReserva {
  readonly tratamientoId: number | null;
  readonly profesionalId: number | null;
  readonly slot: Slot | null;
  readonly nombre: string;
  readonly telefono: string;
}

export type Paso = 1 | 2 | 3;

export function puedeAvanzar(paso: Paso, estado: EstadoReserva): boolean {
  switch (paso) {
    case 1:
      return estado.tratamientoId !== null && estado.profesionalId !== null;
    case 2:
      return estado.slot !== null;
    case 3:
      return (
        estado.slot !== null && validarNombre(estado.nombre) === null && validarTelefono(estado.telefono) === null
      );
  }
}
