import { describe, expect, it } from 'vitest';
import { pesos, porcentaje } from './formato';

describe('pesos', () => {
  it('formatea el texto decimal con separador de miles y coma', () => {
    expect(pesos('3000.00')).toBe('$ 3.000,00');
    expect(pesos('0.00')).toBe('$ 0,00');
    expect(pesos('1234567.5')).toBe('$ 1.234.567,50');
    expect(pesos('12.34')).toBe('$ 12,34');
  });

  it('conserva los centavos exactos sin pasar por number', () => {
    expect(pesos('9007199254740993.01')).toBe('$ 9.007.199.254.740.993,01');
    expect(pesos('0.10')).toBe('$ 0,10');
  });

  it('muestra los negativos con el signo adelante', () => {
    expect(pesos('-1500.00')).toBe('-$ 1.500,00');
  });

  it('un valor vacío o inválido es un guion, no un importe inventado', () => {
    expect(pesos(null)).toBe('—');
    expect(pesos('')).toBe('—');
    expect(pesos('abc')).toBe('—');
  });
});

describe('porcentaje', () => {
  it('muestra hasta un decimal y coma', () => {
    expect(porcentaje('37.50')).toBe('37,5 %');
    expect(porcentaje('0.00')).toBe('0 %');
    expect(porcentaje('100.00')).toBe('100 %');
    expect(porcentaje('2.08')).toBe('2,1 %');
  });

  it('un valor vacío es un guion', () => {
    expect(porcentaje(null)).toBe('—');
    expect(porcentaje('')).toBe('—');
  });
});
