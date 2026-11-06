import { afterEach, describe, expect, it, vi } from 'vitest';
import { cancelarTurno, consultarGestion, reprogramarTurno } from './api';

const GESTION = {
  estado: 'reservado',
  inicio: '2026-11-16T10:00:00-03:00',
  fin: '2026-11-16T10:30:00-03:00',
  tratamiento: { id: 1, nombre: 'Limpieza', duracion_minutos: 30 },
  profesional: { id: 7, nombre: 'Dra. Sintética' },
  sena: { monto: '3000.00', estado: 'acreditado' },
  limite_cambios: '2026-11-15T10:00:00-03:00',
  puede_cancelar: true,
  puede_reprogramar: true,
  motivo_no_cancelable: null,
  motivo_no_reprogramable: null,
  texto_politica_reembolso: 'Texto sintético.',
};

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function servidor(respuesta: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(respuesta));
  vi.stubGlobal('fetch', mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('consultarGestion', () => {
  it('manda el código en la cabecera y nunca en la URL', async () => {
    const mock = servidor(json(GESTION));
    const r = await consultarGestion('CODIGO-SINTETICO-1');
    const [url, init] = mock.mock.calls[0] ?? ['', undefined];
    expect(url).toBe('/api/public/gestion');
    expect(url).not.toContain('CODIGO');
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe('CODIGO-SINTETICO-1');
    expect(r).toEqual({ ok: true, gestion: GESTION });
  });

  it('un 404 es no_encontrado', async () => {
    servidor(json({ detail: 'No encontramos un turno con ese código' }, 404));
    expect(await consultarGestion('x')).toEqual({ ok: false, error: { tipo: 'no_encontrado' } });
  });

  it('un cuerpo que rompe el contrato es un error desconocido, no una excepción', async () => {
    servidor(json({ estado: 'reservado' }));
    const r = await consultarGestion('x');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.tipo).toBe('desconocido');
  });

  it('sin red devuelve un error desconocido legible', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('red'))));
    const r = await consultarGestion('x');
    expect(r.ok).toBe(false);
  });
});

describe('cancelarTurno', () => {
  it('POST sin código en la URL; devuelve cancelado y estado de la seña', async () => {
    const mock = servidor(json({ estado: 'cancelado', estado_sena: 'a_reembolsar' }));
    const r = await cancelarTurno('CODIGO-SINTETICO-1');
    const [url, init] = mock.mock.calls[0] ?? ['', undefined];
    expect(url).toBe('/api/public/gestion/cancelar');
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe('CODIGO-SINTETICO-1');
    expect(r).toEqual({ ok: true, cancelacion: { estado: 'cancelado', estado_sena: 'a_reembolsar' } });
  });

  it('409 fuera_de_plazo conserva el límite', async () => {
    servidor(json({ detail: 'x', motivo: 'fuera_de_plazo', limite_cambios: '2026-11-15T10:00:00-03:00' }, 409));
    expect(await cancelarTurno('x')).toEqual({
      ok: false,
      error: { tipo: 'fuera_de_plazo', limite_cambios: '2026-11-15T10:00:00-03:00' },
    });
  });

  it('409 turno_no_modificable', async () => {
    servidor(json({ detail: 'x', motivo: 'turno_no_modificable' }, 409));
    expect(await cancelarTurno('x')).toEqual({ ok: false, error: { tipo: 'turno_no_modificable' } });
  });

  it('404 es no_encontrado y 503 pide reintentar', async () => {
    servidor(json({ detail: 'x' }, 404));
    expect(await cancelarTurno('x')).toEqual({ ok: false, error: { tipo: 'no_encontrado' } });
    servidor(json({ detail: 'reintentar' }, 503));
    const r = await cancelarTurno('x');
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.tipo).toBe('desconocido');
  });
});

describe('reprogramarTurno', () => {
  const OK = { estado: 'reservado', inicio: '2026-11-18T11:00:00-03:00', fin: '2026-11-18T11:30:00-03:00', estado_sena: 'acreditado' };

  it('envía el nuevo inicio en el cuerpo y el código en la cabecera', async () => {
    const mock = servidor(json(OK));
    const r = await reprogramarTurno('CODIGO-SINTETICO-1', '2026-11-18T11:00:00-03:00');
    const [url, init] = mock.mock.calls[0] ?? ['', undefined];
    expect(url).toBe('/api/public/gestion/reprogramar');
    expect(JSON.parse(typeof init?.body === 'string' ? init.body : '')).toEqual({ inicio: '2026-11-18T11:00:00-03:00' });
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe('CODIGO-SINTETICO-1');
    expect(r).toEqual({ ok: true, reprogramacion: OK });
  });

  it('409 de solape trae motivo y alternativas', async () => {
    const alt = { inicio: '2026-11-18T11:30:00-03:00', fin: '2026-11-18T12:00:00-03:00', sillon_id: 2 };
    servidor(json({ detail: 'x', motivo: 'profesional', alternativas: [alt, { basura: 1 }] }, 409));
    expect(await reprogramarTurno('x', 'y')).toEqual({
      ok: false,
      error: { tipo: 'conflicto', motivo: 'profesional', alternativas: [alt] },
    });
  });

  it('409 sena_pendiente y fuera_de_plazo', async () => {
    servidor(json({ detail: 'x', motivo: 'sena_pendiente' }, 409));
    expect(await reprogramarTurno('x', 'y')).toEqual({ ok: false, error: { tipo: 'sena_pendiente' } });
    servidor(json({ detail: 'x', motivo: 'fuera_de_plazo', limite_cambios: 'L' }, 409));
    expect(await reprogramarTurno('x', 'y')).toEqual({ ok: false, error: { tipo: 'fuera_de_plazo', limite_cambios: 'L' } });
  });

  it('422 fuera_de_disponibilidad y mismo_horario son horario_invalido; el de validación también', async () => {
    servidor(json({ detail: 'Ese horario no está dentro de la agenda', motivo: 'fuera_de_disponibilidad' }, 422));
    const r = await reprogramarTurno('x', 'y');
    expect(r).toEqual({ ok: false, error: { tipo: 'horario_invalido', mensaje: expect.stringContaining('horario') as unknown } });
    servidor(json({ detail: [{ loc: ['body', 'inicio'], msg: 'x' }] }, 422));
    const r2 = await reprogramarTurno('x', 'y');
    expect(r2.ok).toBe(false);
    if (!r2.ok) expect(r2.error.tipo).toBe('horario_invalido');
  });
});
