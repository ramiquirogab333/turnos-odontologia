import { describe, expect, it } from 'vitest';
import { minutosDesdeRetryAfter } from './limite';

describe('minutosDesdeRetryAfter', () => {
  it.each([
    ['600', 10],
    ['900', 15],
    ['61', 2],
    ['120', 2],
    ['121', 3],
  ])('%s segundos son %i minutos (redondeo hacia arriba)', (cabecera, minutos) => {
    expect(minutosDesdeRetryAfter(cabecera)).toBe(minutos);
  });

  it.each([['20'], ['60'], ['1'], ['0'], ['-5'], ['abc'], [''], ['1.5e3x'], [null]])(
    'valor %s (corto, cero, negativo, ausente o no numérico) cae en 1 minuto',
    (cabecera) => {
      expect(minutosDesdeRetryAfter(cabecera)).toBe(1);
    },
  );
});
