import { afterEach, describe, expect, it, vi } from 'vitest';
import { cargarCatalogo, obtenerDisponibilidad, reservarTurno } from './api';

const TRATAMIENTO = { id: 1, nombre: 'Limpieza', duracion_minutos: 30, precio_base: '1000.00' };
const PROFESIONAL = { id: 7, nombre: 'Dra. Sintética', especialidad: 'General' };

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function diferido(): { promesa: Promise<Response>; resolver: (r: Response) => void } {
  let resolver: (r: Response) => void = () => undefined;
  const promesa = new Promise<Response>((res) => {
    resolver = res;
  });
  return { promesa, resolver };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('cargarCatalogo (R2: sin cascadas)', () => {
  it('lanza tratamientos y profesionales a la vez, antes de que responda cualquiera', async () => {
    const a = diferido();
    const b = diferido();
    const fetchMock = vi
      .fn<(url: string) => Promise<Response>>()
      .mockImplementation((url) => (url.includes('tratamientos') ? a.promesa : b.promesa));
    vi.stubGlobal('fetch', fetchMock);

    const pendiente = cargarCatalogo();

    // Nada resolvió todavía y ya salieron las dos peticiones.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.map(([url]) => url).sort()).toEqual([
      '/api/public/profesionales',
      '/api/public/tratamientos',
    ]);

    b.resolver(json([PROFESIONAL]));
    a.resolver(json([TRATAMIENTO]));
    await expect(pendiente).resolves.toEqual({ tratamientos: [TRATAMIENTO], profesionales: [PROFESIONAL] });
  });

  it('falla con un mensaje legible si una de las dos respuestas no es 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => Promise.resolve(url.includes('tratamientos') ? json([TRATAMIENTO]) : json({}, 500))),
    );
    await expect(cargarCatalogo()).rejects.toThrow(/no pudimos cargar/i);
  });

  it('falla si el cuerpo no respeta el contrato', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(url.includes('tratamientos') ? json([{ id: 'x' }]) : json([PROFESIONAL])),
      ),
    );
    await expect(cargarCatalogo()).rejects.toThrow(/no pudimos cargar/i);
  });
});

describe('obtenerDisponibilidad', () => {
  it('pide un único rango con los ids y devuelve los slots tal cual', async () => {
    const slot = { inicio: '2026-11-16T10:00:00-03:00', fin: '2026-11-16T10:30:00-03:00', profesional_id: 7, sillon_id: 2 };
    const fetchMock = vi.fn((url: string) => Promise.resolve(url ? json({ slots: [slot] }) : json({}, 500)));
    vi.stubGlobal('fetch', fetchMock);

    const slots = await obtenerDisponibilidad({
      profesionalId: 7,
      tratamientoId: 1,
      desde: '2026-11-16',
      hasta: '2026-11-30',
    });

    expect(slots).toEqual([slot]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = new URL(fetchMock.mock.calls[0]?.[0] ?? '', 'http://x');
    expect(url.pathname).toBe('/api/public/disponibilidad');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      profesional_id: '7',
      tratamiento_id: '1',
      desde: '2026-11-16',
      hasta: '2026-11-30',
    });
  });

  it('una lista vacía es un resultado válido, no un error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ slots: [] }))));
    await expect(
      obtenerDisponibilidad({ profesionalId: 7, tratamientoId: 1, desde: '2026-11-16', hasta: '2026-11-17' }),
    ).resolves.toEqual([]);
  });

  it('rechaza si el servidor responde error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({}, 503))));
    await expect(
      obtenerDisponibilidad({ profesionalId: 7, tratamientoId: 1, desde: '2026-11-16', hasta: '2026-11-17' }),
    ).rejects.toThrow(/horarios/i);
  });
});

describe('reservarTurno', () => {
  const peticion = {
    nombre: '  Carlos Sintético ',
    telefono: '+54 9 11 4444-5555',
    tratamiento_id: 1,
    profesional_id: 7,
    inicio: '2026-11-16T10:00:00-03:00',
  };

  it('envía nombre recortado y teléfono normalizado, y devuelve la reserva en un 201', async () => {
    const creada = {
      turno_id: 5,
      codigo_gestion: 'ABCD2345',
      estado: 'reservado',
      inicio: peticion.inicio,
      fin: '2026-11-16T10:30:00-03:00',
    };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(url && init ? json(creada, 201) : json({}, 500)));
    vi.stubGlobal('fetch', fetchMock);

    const r = await reservarTurno(peticion);

    expect(r).toEqual({ ok: true, reserva: creada });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/public/turnos');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(typeof init?.body === 'string' ? init.body : 'null') as unknown).toEqual({
      nombre: 'Carlos Sintético',
      telefono: '+5491144445555',
      tratamiento_id: 1,
      profesional_id: 7,
      inicio: '2026-11-16T10:00:00-03:00',
    });
  });

  it('traduce el 409 a conflicto con alternativas', async () => {
    const alternativa = { inicio: '2026-11-16T10:30:00-03:00', fin: '2026-11-16T11:00:00-03:00', sillon_id: 2 };
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(json({ detail: 'Solape por profesional', motivo: 'profesional', alternativas: [alternativa] }, 409)),
      ),
    );
    await expect(reservarTurno(peticion)).resolves.toEqual({
      ok: false,
      error: { tipo: 'conflicto', motivo: 'profesional', alternativas: [alternativa] },
    });
  });

  it('traduce el 422 de teléfono (lista) y el 422 de horario (texto) sin confundirlos', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json({ detail: [{ loc: ['body', 'telefono'], msg: 'Value error, x', type: 'value_error' }] }, 422))
        .mockResolvedValueOnce(json({ detail: 'El horario solicitado está fuera de la disponibilidad del profesional' }, 422)),
    );
    const a = await reservarTurno(peticion);
    const b = await reservarTurno(peticion);
    expect(a.ok === false && a.error.tipo).toBe('validacion');
    expect(b.ok === false && b.error.tipo).toBe('fuera_de_horario');
  });

  it('si la red falla devuelve un error desconocido en vez de lanzar', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
    const r = await reservarTurno(peticion);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.error.tipo).toBe('desconocido');
  });

  it('un cuerpo no JSON en un error no rompe la interpretación', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>Bad Gateway</html>', { status: 502 }))));
    const r = await reservarTurno(peticion);
    expect(r.ok === false && r.error.tipo).toBe('desconocido');
  });
});
