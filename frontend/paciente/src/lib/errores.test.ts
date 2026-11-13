import { describe, expect, it } from 'vitest';
import { interpretarRespuestaError } from './errores';

describe('interpretarRespuestaError', () => {
  it('422 con lista de Pydantic: asigna el mensaje al campo y lo explica en español', () => {
    const cuerpo = {
      detail: [
        {
          type: 'value_error',
          loc: ['body', 'telefono'],
          msg: 'Value error, telefono debe tener formato E.164 (ej. +5491144445555)',
          input: '1234',
        },
      ],
    };
    const e = interpretarRespuestaError(422, cuerpo);
    expect(e.tipo).toBe('validacion');
    if (e.tipo !== 'validacion') return;
    expect(e.campos.telefono).toMatch(/código de país/);
    expect(e.campos.telefono).toMatch(/\+5491144445555/);
    expect(e.campos.nombre).toBeUndefined();
    expect(e.generales).toEqual([]);
  });

  it('422 con lista: varios campos a la vez', () => {
    const e = interpretarRespuestaError(422, {
      detail: [
        { type: 'value_error', loc: ['body', 'nombre'], msg: 'Value error, nombre debe tener entre 1 y 200 caracteres' },
        { type: 'value_error', loc: ['body', 'telefono'], msg: 'Value error, x' },
      ],
    });
    expect(e.tipo).toBe('validacion');
    if (e.tipo !== 'validacion') return;
    expect(e.campos.nombre).toMatch(/nombre/i);
    expect(e.campos.telefono).toBeDefined();
  });

  it('422 con lista sobre un campo desconocido: queda como mensaje general sin el prefijo técnico', () => {
    const e = interpretarRespuestaError(422, {
      detail: [{ type: 'value_error', loc: ['body', 'inicio'], msg: 'Value error, inicio debe ser futuro' }],
    });
    expect(e.tipo).toBe('validacion');
    if (e.tipo !== 'validacion') return;
    expect(e.generales).toEqual(['inicio debe ser futuro']);
  });

  it('422 con texto plano (horario fuera de atención) es un tipo propio', () => {
    const e = interpretarRespuestaError(422, {
      detail: 'El horario solicitado está fuera de la disponibilidad del profesional',
    });
    expect(e.tipo).toBe('fuera_de_horario');
    if (e.tipo !== 'fuera_de_horario') return;
    expect(e.mensaje).toMatch(/otro horario/i);
  });

  it('422 con detalle de referencia inexistente (texto plano) también se tolera', () => {
    const e = interpretarRespuestaError(422, { detail: 'Referencia inexistente: profesional_id' });
    expect(e.tipo).toBe('fuera_de_horario');
  });

  it('409 trae el motivo y las alternativas libres', () => {
    const alternativa = { inicio: '2026-11-16T13:30:00-03:00', fin: '2026-11-16T14:00:00-03:00', sillon_id: 3 };
    const e = interpretarRespuestaError(409, {
      detail: 'Solape por profesional',
      motivo: 'profesional',
      alternativas: [alternativa],
    });
    expect(e).toEqual({ tipo: 'conflicto', motivo: 'profesional', alternativas: [alternativa] });
  });

  it('409 con alternativas malformadas descarta solo las inválidas', () => {
    const buena = { inicio: '2026-11-16T13:30:00-03:00', fin: '2026-11-16T14:00:00-03:00', sillon_id: 3 };
    const e = interpretarRespuestaError(409, {
      motivo: 'sillon',
      alternativas: [buena, { inicio: 5 }, null, 'x'],
    });
    expect(e).toEqual({ tipo: 'conflicto', motivo: 'sillon', alternativas: [buena] });
  });

  it('409 sin alternativas es un conflicto con lista vacía', () => {
    const e = interpretarRespuestaError(409, { motivo: 'sillon', alternativas: [] });
    expect(e).toEqual({ tipo: 'conflicto', motivo: 'sillon', alternativas: [] });
  });

  it('cuerpos inesperados y 5xx caen en un error genérico con instrucción de reintento', () => {
    const casos: ReadonlyArray<readonly [number, unknown]> = [
      [500, null],
      [502, 'Bad Gateway'],
      [422, { algo: 1 }],
      [422, { detail: 42 }],
    ];
    for (const [status, cuerpo] of casos) {
      const e = interpretarRespuestaError(status, cuerpo);
      expect(e.tipo).toBe('desconocido');
      if (e.tipo !== 'desconocido') return;
      expect(e.mensaje).toMatch(/intentá de nuevo/i);
    }
  });
});

describe('interpretarRespuestaError: 429 (C-15)', () => {
  it.each([
    ['300', 'Hiciste muchos pedidos seguidos. Probá de nuevo en 5 minutos.'],
    [null, 'Hiciste muchos pedidos seguidos. Probá de nuevo en 1 minuto.'],
  ])('Retry-After %s es un error de límite con su mensaje', (retryAfter, mensaje) => {
    expect(interpretarRespuestaError(429, { detail: 'x', motivo: 'demasiados_intentos' }, retryAfter)).toEqual({ tipo: 'limite', mensaje });
  });

  it('un 429 con cuerpo ilegible sigue siendo límite (el estado manda)', () => {
    expect(interpretarRespuestaError(429, null, '120').tipo).toBe('limite');
  });

  it('un 409 y un 422 no se confunden con el límite', () => {
    expect(interpretarRespuestaError(409, { motivo: 'profesional', alternativas: [] }, '300').tipo).toBe('conflicto');
    expect(interpretarRespuestaError(422, { detail: 'x' }, '300').tipo).toBe('fuera_de_horario');
  });
});
