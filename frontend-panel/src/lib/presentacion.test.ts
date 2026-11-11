import { describe, expect, it } from 'vitest';
import { ETIQUETA_ESTADO_SENA, textoSena as textoSenaCrudo } from './presentacion';

/** El formato de moneda del navegador usa un espacio duro: se compara con espacios comunes. */
const textoSena = (...args: Parameters<typeof textoSenaCrudo>): string | null =>
  textoSenaCrudo(...args)?.replace(/\s/g, ' ') ?? null;

describe('textoSena: seña devuelta', () => {
  it('una seña reembolsada se lee "Seña devuelta" con su monto', () => {
    expect(textoSena({ sena: { estado: 'reembolsado', monto: '3000.00' }, origen: 'web', estado: 'cancelado' })).toBe(
      'Seña devuelta: $ 3.000,00',
    );
  });

  it('las demás etiquetas siguen igual', () => {
    expect(textoSena({ sena: { estado: 'no_reembolsado', monto: '3000.00' }, origen: 'web', estado: 'ausente' })).toBe(
      'Seña retenida: $ 3.000,00',
    );
    expect(textoSena({ sena: { estado: 'a_reembolsar', monto: '4500.00' }, origen: 'web', estado: 'cancelado' })).toBe(
      'Seña a devolver: $ 4.500,00',
    );
  });

  it('la etiqueta corta del estado de la seña también dice "Seña devuelta"', () => {
    expect(ETIQUETA_ESTADO_SENA['reembolsado']).toBe('Seña devuelta');
  });
});
