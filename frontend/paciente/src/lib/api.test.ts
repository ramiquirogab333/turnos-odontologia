import { afterEach, describe, expect, it, vi } from 'vitest';
import { cargarCatalogo, consultarSena, iniciarSena, obtenerDisponibilidad, reservarTurno } from './api';

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


const SENA_INFO = {
  monto: '3000.00',
  vence_en: '2026-11-16T09:30:00-03:00',
  medios_habilitados: ['mercadopago', 'transferencia'],
  texto_politica_reembolso: 'Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve.',
};

describe('reservarTurno con seña (C-06)', () => {
  it('acepta la respuesta en_espera con el bloque sena y conserva el monto como texto decimal', async () => {
    const creada = {
      turno_id: 5,
      codigo_gestion: 'ABCD2345',
      estado: 'en_espera',
      inicio: '2026-11-16T10:00:00-03:00',
      fin: '2026-11-16T10:30:00-03:00',
      sena: SENA_INFO,
    };
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(creada, 201))));
    const r = await reservarTurno({
      nombre: 'Carlos Sintético',
      telefono: '+5491144445555',
      tratamiento_id: 1,
      profesional_id: 7,
      inicio: creada.inicio,
    });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.reserva.estado).toBe('en_espera');
    if (r.reserva.estado === 'en_espera') {
      expect(r.reserva.sena.monto).toBe('3000.00');
      expect(typeof r.reserva.sena.monto).toBe('string');
      expect(r.reserva.sena.medios_habilitados).toEqual(['mercadopago', 'transferencia']);
    }
  });

  it('acepta una reserva exenta de seña (reservado, sena null)', async () => {
    const creada = { turno_id: 6, codigo_gestion: 'ZZZZ2345', estado: 'reservado', inicio: 'a', fin: 'b', sena: null };
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(creada, 201))));
    const r = await reservarTurno({ nombre: 'Ana Ficticia', telefono: '+5491155556666', tratamiento_id: 1, profesional_id: 7, inicio: 'a' });
    expect(r.ok && r.reserva.estado).toBe('reservado');
  });

  it('rechaza un en_espera sin bloque sena (contrato roto)', async () => {
    const rota = { turno_id: 5, codigo_gestion: 'ABCD2345', estado: 'en_espera', inicio: 'a', fin: 'b', sena: null };
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(rota, 201))));
    const r = await reservarTurno({ nombre: 'Ana Ficticia', telefono: '+5491155556666', tratamiento_id: 1, profesional_id: 7, inicio: 'a' });
    expect(r.ok).toBe(false);
  });
});

const INICIO_MP = {
  turno_id: 5,
  pago_id: 11,
  estado: 'pendiente',
  medio: 'mercadopago',
  monto: '3000.00',
  vence_en: SENA_INFO.vence_en,
  texto_politica_reembolso: SENA_INFO.texto_politica_reembolso,
  referencia_externa: 'abc123abc123abc123abc123abc123ab',
  checkout_url: 'http://localhost:5173/?pago=retorno&turno=5',
  alias: null,
  cbu: null,
  titular: null,
  referencia_concepto: null,
};

describe('iniciarSena', () => {
  it('envía el medio con la cabecera X-Codigo-Gestion y devuelve la seña pendiente (201)', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(url && init ? json(INICIO_MP, 201) : json({}, 500)));
    vi.stubGlobal('fetch', fetchMock);

    const r = await iniciarSena(5, 'ABCD2345', 'mercadopago');

    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.creada).toBe(true);
    expect(r.sena.monto).toBe('3000.00');
    expect(r.sena.checkout_url).toBe(INICIO_MP.checkout_url);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/public/turnos/5/sena');
    expect(init?.method).toBe('POST');
    const cabeceras = new Headers(init?.headers);
    expect(cabeceras.get('X-Codigo-Gestion')).toBe('ABCD2345');
    expect(JSON.parse(typeof init?.body === 'string' ? init.body : 'null') as unknown).toEqual({ medio: 'mercadopago' });
  });

  it('un 200 es el reintento idempotente: misma seña, creada=false', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(INICIO_MP, 200))));
    const r = await iniciarSena(5, 'ABCD2345', 'mercadopago');
    expect(r.ok && r.creada).toBe(false);
  });

  it('transferencia: devuelve alias, CBU y código de referencia', async () => {
    const tr = {
      ...INICIO_MP,
      medio: 'transferencia',
      checkout_url: null,
      alias: 'clinica.demo.sintetica',
      cbu: '0000003100000000000043',
      titular: 'Clínica Demo',
      referencia_concepto: 'SENA-5-A1B2C3',
    };
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(tr, 201))));
    const r = await iniciarSena(5, 'ABCD2345', 'transferencia');
    expect(r.ok && r.sena.alias).toBe('clinica.demo.sintetica');
    expect(r.ok && r.sena.referencia_concepto).toBe('SENA-5-A1B2C3');
  });

  it.each([
    [409, { detail: 'La reserva venció', motivo: 'estado_invalido' }, 'vencida'],
    [409, { detail: 'Solape por profesional', motivo: 'profesional', alternativas: [] }, 'horario_tomado'],
    [404, { detail: 'Turno no encontrado' }, 'no_encontrada'],
    [422, { detail: 'Medio no habilitado: transferencia', medios_habilitados: ['mercadopago'] }, 'medio'],
    [502, { detail: 'No pudimos conectar con Mercado Pago.' }, 'pasarela'],
    [500, { detail: 'x' }, 'desconocido'],
  ])('traduce el %i a un error de seña tipado (%#)', async (status, cuerpo, tipo) => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(cuerpo, status))));
    const r = await iniciarSena(5, 'ABCD2345', 'mercadopago');
    expect(r.ok === false && r.error.tipo).toBe(tipo);
  });

  it('si la red falla devuelve error desconocido en vez de lanzar', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
    const r = await iniciarSena(5, 'ABCD2345', 'mercadopago');
    expect(r.ok === false && r.error.tipo).toBe('desconocido');
  });
});

const ESTADO = {
  turno_id: 5,
  estado_turno: 'en_espera',
  estado_pago: null,
  vencida: false,
  medios_habilitados: ['mercadopago'],
  pago_id: null,
  medio: null,
  monto: '3000.00',
  vence_en: SENA_INFO.vence_en,
  texto_politica_reembolso: SENA_INFO.texto_politica_reembolso,
  referencia_externa: null,
  checkout_url: null,
  alias: null,
  cbu: null,
  titular: null,
  referencia_concepto: null,
  inicio: '2026-11-16T10:00:00-03:00',
  fin: '2026-11-16T10:30:00-03:00',
  tratamiento_nombre: 'Limpieza',
  profesional_nombre: 'Dra. Sintética',
};

describe('consultarSena', () => {
  it('pide el estado con la cabecera X-Codigo-Gestion; sin pago iniciado estado_pago es null', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(url && init ? json(ESTADO) : json({}, 500)));
    vi.stubGlobal('fetch', fetchMock);
    const r = await consultarSena(5, 'ABCD2345');
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.estado.estado_turno).toBe('en_espera');
    expect(r.estado.estado_pago).toBeNull();
    expect(r.estado.monto).toBe('3000.00');
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/public/turnos/5/sena');
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe('ABCD2345');
  });

  it.each(['pendiente', 'acreditado', 'vencido', 'a_reembolsar', 'en_revision', 'no_reembolsado'] as const)('entiende el estado de pago %s', async (pago) => {
    const estadoTurno = pago === 'acreditado' ? 'reservado' : 'en_espera';
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ ...ESTADO, estado_turno: estadoTurno, estado_pago: pago }))));
    const r = await consultarSena(5, 'ABCD2345');
    expect(r.ok && r.estado.estado_pago).toBe(pago);
    expect(r.ok && r.estado.estado_turno).toBe(estadoTurno);
  });

  it('un estado desconocido rompe el contrato: error, no un valor inventado', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ ...ESTADO, estado_pago: 'inventado' }))));
    const r = await consultarSena(5, 'ABCD2345');
    expect(r.ok).toBe(false);
  });

  it('404 es no_encontrada y la red caída es desconocido', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ detail: 'x' }, 404))));
    const r404 = await consultarSena(5, 'X');
    expect(r404.ok === false && r404.error.tipo).toBe('no_encontrada');
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
    const rRed = await consultarSena(5, 'X');
    expect(rRed.ok === false && rRed.error.tipo).toBe('desconocido');
  });
});

describe('429 en lo público (C-15)', () => {
  const limite = (segundos: string): Response =>
    new Response(JSON.stringify({ detail: 'x', motivo: 'demasiados_intentos' }), {
      status: 429,
      headers: { 'Content-Type': 'application/json', 'Retry-After': segundos },
    });

  it('la reserva con 429 da error de límite con los minutos de Retry-After', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(limite('300'))));
    const r = await reservarTurno({ nombre: 'Paciente Ficticio', telefono: '+5491100000001', tratamiento_id: 1, profesional_id: 7, inicio: '2026-11-16T10:00:00-03:00' });
    expect(r).toEqual({ ok: false, error: { tipo: 'limite', mensaje: 'Hiciste muchos pedidos seguidos. Probá de nuevo en 5 minutos.' } });
  });

  it('iniciar la seña con 429 da error de límite y no una seña', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(limite('61'))));
    const r = await iniciarSena(5, 'CODIGO-SINTETICO-1', 'transferencia');
    expect(r).toEqual({ ok: false, error: { tipo: 'limite', mensaje: 'Hiciste muchos pedidos seguidos. Probá de nuevo en 2 minutos.' } });
  });

  it('consultar la seña con 429 también es límite', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(limite('120'))));
    const r = await consultarSena(5, 'CODIGO-SINTETICO-1');
    expect(r).toMatchObject({ ok: false, error: { tipo: 'limite' } });
  });

  it('la consulta de horarios con 429 rechaza con el mensaje de límite', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(limite('600'))));
    await expect(
      obtenerDisponibilidad({ profesionalId: 7, tratamientoId: 1, desde: '2026-11-16', hasta: '2026-11-23' }),
    ).rejects.toThrow('Hiciste muchos pedidos seguidos. Probá de nuevo en 10 minutos.');
  });

  it('otros errores de la consulta de horarios conservan su mensaje genérico', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ detail: 'x' }, 500))));
    await expect(
      obtenerDisponibilidad({ profesionalId: 7, tratamientoId: 1, desde: '2026-11-16', hasta: '2026-11-23' }),
    ).rejects.toThrow('No pudimos cargar los horarios. Intentá de nuevo.');
  });
});
