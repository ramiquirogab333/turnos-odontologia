import { describe, expect, it } from 'vitest';
import { mensajeLimite, minutosDesdeRetryAfter } from './limite';

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

describe('mensajeLimite', () => {
  it.each([
    ['300', 'Hiciste muchos pedidos seguidos. Probá de nuevo en 5 minutos.'],
    ['120', 'Hiciste muchos pedidos seguidos. Probá de nuevo en 2 minutos.'],
    ['20', 'Hiciste muchos pedidos seguidos. Probá de nuevo en 1 minuto.'],
    [null, 'Hiciste muchos pedidos seguidos. Probá de nuevo en 1 minuto.'],
  ])('Retry-After %s da "%s"', (cabecera, texto) => {
    expect(mensajeLimite(cabecera)).toBe(texto);
  });
});
