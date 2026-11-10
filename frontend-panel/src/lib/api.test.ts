import { beforeEach, describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorApiPanel, ErrorDeRespuesta } from './api';
import { ErrorSesion, Sesion } from './sesion';
import type { Consulta } from './tipos';

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

type Manejador = (url: string, init?: RequestInit) => Response | Promise<Response> | undefined;

function servidor(...manejadores: Manejador[]) {
  return vi.fn<typeof fetch>(async (entrada, init) => {
    const url = entrada instanceof Request ? entrada.url : String(entrada);
    for (const m of manejadores) {
      const r = await m(url, init);
      if (r) return r.clone();
    }
    return json({ detail: 'sin ruta' }, 500);
  });
}

const refrescar = (token: string): Manejador => (url) =>
  url === '/api/auth/refresh' ? json({ access_token: token, token_type: 'bearer' }) : undefined;

const urlDe = (llamada: Parameters<typeof fetch> | undefined): string => {
  const u = llamada?.[0];
  if (u === undefined) return '';
  return typeof u === 'string' ? u : u instanceof URL ? u.href : u.url;
};

const bearer = (init?: RequestInit): string | null => new Headers(init?.headers).get('Authorization');

const TURNO = {
  id: 11,
  inicio: '2031-11-18T09:00:00-03:00',
  fin: '2031-11-18T09:30:00-03:00',
  estado: 'reservado',
  bloquea_agenda: true,
  origen: 'web',
  profesional: { id: 1, nombre: 'Dra. Ana Ficticia' },
  sillon: { id: 2, nombre: 'Sillón 1' },
  tratamiento: { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 },
  paciente_nombre: 'Carlos Sintético',
  paciente_telefono: '+5491144445555',
  sena: { estado: 'acreditado', monto: '3000.00' },
  vence_en: null,
  acciones: ['atendido'],
};
const AGENDA = { vista: 'dia', desde: '2031-11-18', hasta: '2031-11-18', turnos: [TURNO] };
const CONSULTA: Consulta = { vista: 'dia', fecha: '2031-11-18', profesionalId: null, sillonId: null };

function api(fetchFn: typeof fetch, token: string | null = 'ACCESS-1') {
  const sesion = new Sesion({ fetchFn, candados: null, canal: null });
  sesion.fijarToken(token);
  return { sesion, api: crearApi(sesion, fetchFn) };
}

describe('crearApi: autenticación', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('manda el access como Bearer y valida la agenda', async () => {
    const fetchFn = servidor((url) => (url.startsWith('/api/panel/agenda?') ? json(AGENDA) : undefined));
    const { api: a } = api(fetchFn);
    const agenda = await a.agenda(CONSULTA);
    expect(agenda.turnos[0]?.paciente_nombre).toBe('Carlos Sintético');
    expect(bearer(fetchFn.mock.calls[0]?.[1])).toBe('Bearer ACCESS-1');
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/agenda?vista=dia&fecha=2031-11-18');
  });

  it('arma los filtros solo cuando están elegidos', async () => {
    const fetchFn = servidor(() => json(AGENDA));
    const { api: a } = api(fetchFn);
    await a.agenda({ vista: 'semana', fecha: '2031-11-18', profesionalId: 1, sillonId: 2 });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/agenda?vista=semana&fecha=2031-11-18&profesional_id=1&sillon_id=2');
  });

  it('sin access renueva primero y después pide', async () => {
    const fetchFn = servidor(refrescar('NUEVO'), (url) => (url.startsWith('/api/panel/agenda') ? json(AGENDA) : undefined));
    const { api: a } = api(fetchFn, null);
    await a.agenda(CONSULTA);
    expect(fetchFn.mock.calls.map((c) => urlDe(c).split('?')[0])).toEqual(['/api/auth/refresh', '/api/panel/agenda']);
    expect(bearer(fetchFn.mock.calls[1]?.[1])).toBe('Bearer NUEVO');
  });

  it('sin access y sin sesión lanza ErrorSesion', async () => {
    const fetchFn = servidor(() => json({ detail: 'x' }, 401));
    const { api: a } = api(fetchFn, null);
    await expect(a.agenda(CONSULTA)).rejects.toBeInstanceOf(ErrorSesion);
  });

  it('dos 401 simultáneos disparan UNA sola renovación y dos reintentos', async () => {
    const fetchFn = servidor(refrescar('NUEVO'), (url, init) => {
      if (!url.startsWith('/api/panel/agenda')) return undefined;
      return bearer(init) === 'Bearer NUEVO' ? json(AGENDA) : json({ detail: 'vencido' }, 401);
    });
    const { api: a } = api(fetchFn, 'VIEJO');
    const [uno, dos] = await Promise.all([a.agenda(CONSULTA), a.agenda({ ...CONSULTA, fecha: '2031-11-19' })]);
    expect(uno.turnos).toHaveLength(1);
    expect(dos.turnos).toHaveLength(1);
    const llamadas = fetchFn.mock.calls.map((c) => urlDe(c).split('?')[0]);
    expect(llamadas.filter((u) => u === '/api/auth/refresh')).toHaveLength(1);
    expect(llamadas.filter((u) => u === '/api/panel/agenda')).toHaveLength(4); // 2 intentos + 2 reintentos
  });

  it('un 401 después de renovar no hace un bucle: cierra la sesión local y lanza ErrorSesion', async () => {
    const fetchFn = servidor(refrescar('NUEVO'), (url) => (url.startsWith('/api/panel/agenda') ? json({ detail: 'x' }, 401) : undefined));
    const { api: a, sesion } = api(fetchFn, 'VIEJO');
    const alCambiar = vi.fn();
    sesion.alCambiar(alCambiar);
    await expect(a.agenda(CONSULTA)).rejects.toBeInstanceOf(ErrorSesion);
    expect(fetchFn).toHaveBeenCalledTimes(3); // pedido, renovación, un único reintento
    expect(sesion.token()).toBeNull();
    expect(alCambiar).toHaveBeenLastCalledWith(null, 'vencida');
  });

  it('si la renovación responde "sin sesión", lanza ErrorSesion', async () => {
    const fetchFn = servidor(
      (url) => (url === '/api/auth/refresh' ? json({ detail: 'x' }, 401) : undefined),
      (url) => (url.startsWith('/api/panel/agenda') ? json({ detail: 'x' }, 401) : undefined),
    );
    const { api: a } = api(fetchFn, 'VIEJO');
    await expect(a.agenda(CONSULTA)).rejects.toBeInstanceOf(ErrorSesion);
  });
});

describe('crearApi: lecturas validadas', () => {
  it('una agenda que no cumple el contrato es ErrorDeRespuesta (sin aserciones ciegas)', async () => {
    const rota = { ...AGENDA, turnos: [{ ...TURNO, estado: 'inventado' }] };
    const { api: a } = api(servidor(() => json(rota)));
    await expect(a.agenda(CONSULTA)).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it.each([
    ['acciones con algo desconocido', { ...TURNO, acciones: ['borrar'] }],
    ['sin profesional', { ...TURNO, profesional: null }],
    ['seña mal formada', { ...TURNO, sena: { estado: 1 } }],
  ])('rechaza un turno con %s', async (_n, turno) => {
    const { api: a } = api(servidor(() => json({ ...AGENDA, turnos: [turno] })));
    await expect(a.agenda(CONSULTA)).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('un 5xx es ErrorApiPanel con su status; un 403 conserva el motivo y el mensaje', async () => {
    const { api: caida } = api(servidor(() => json({ detail: 'x' }, 500)));
    await expect(caida.agenda(CONSULTA)).rejects.toMatchObject({ name: 'ErrorApiPanel', status: 500 });
    const { api: prohibida } = api(servidor(() =>
      json({ detail: 'Pedile a la clínica que lo asocie.', motivo: 'sin_profesional_asociado' }, 403)));
    const error = await prohibida.agenda(CONSULTA).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ErrorApiPanel);
    expect(error).toMatchObject({ status: 403, motivo: 'sin_profesional_asociado', message: 'Pedile a la clínica que lo asocie.' });
  });

  it('valida las opciones y el usuario', async () => {
    const opciones = {
      profesionales: [{ id: 1, nombre: 'Dra. Ana Ficticia' }],
      sillones: [{ id: 2, nombre: 'Sillón 1' }],
      tratamientos: [{ id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 }],
      puede_escribir: true,
    };
    const me = { id: 1, email: 'recepcion@turnos.test', nombre_completo: 'Rita Recepción', roles: ['recepcion'] };
    const { api: a } = api(servidor((url) => (url === '/api/panel/agenda/opciones' ? json(opciones) : json(me))));
    expect((await a.opciones()).puede_escribir).toBe(true);
    expect((await a.me()).roles).toEqual(['recepcion']);
    const { api: mala } = api(servidor(() => json({ ...me, roles: ['superusuario'] })));
    await expect(mala.me()).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('la disponibilidad se pide al endpoint público, sin credenciales', async () => {
    const slots = { slots: [{ inicio: '2031-11-18T11:00:00-03:00', fin: '2031-11-18T11:30:00-03:00', profesional_id: 1, sillon_id: 2 }] };
    const fetchFn = servidor(() => json(slots));
    const { api: a } = api(fetchFn);
    const lista = await a.disponibilidad(1, 3, '2031-11-18');
    expect(lista).toHaveLength(1);
    expect(urlDe(fetchFn.mock.calls[0])).toBe(
      '/api/public/disponibilidad?profesional_id=1&tratamiento_id=3&desde=2031-11-18&hasta=2031-11-18',
    );
    expect(bearer(fetchFn.mock.calls[0]?.[1])).toBeNull();
  });
});

const ALTA = { profesionalId: 1, tratamientoId: 3, inicio: '2031-11-18T11:00:00-03:00', nombre: 'Carlos Sintético', telefono: '+5491144445555' };

describe('crearApi: alta manual', () => {
  it('201 devuelve el turno con su código de gestión y manda el cuerpo del contrato', async () => {
    const creado = {
      id: 5, inicio: ALTA.inicio, fin: '2031-11-18T11:45:00-03:00', estado: 'reservado', origen: 'manual',
      profesional_id: 1, sillon_id: 2, tratamiento_id: 3, codigo_gestion: 'CODIGO-SINTETICO-1',
    };
    const fetchFn = servidor(() => json(creado, 201));
    const r = await api(fetchFn).api.crearTurno(ALTA);
    expect(r).toEqual({ ok: true, valor: creado });
    const init = fetchFn.mock.calls[0]?.[1];
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/turnos');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(typeof init?.body === 'string' ? init.body : '')).toEqual({
      profesional_id: 1, tratamiento_id: 3, inicio: ALTA.inicio, nombre: 'Carlos Sintético', telefono: '+5491144445555',
    });
  });

  it('409 trae el motivo y las alternativas', async () => {
    const alternativa = { inicio: '2031-11-18T11:30:00-03:00', fin: '2031-11-18T12:00:00-03:00', sillon_id: 2 };
    const r = await api(servidor(() => json({ detail: 'Solape por profesional', motivo: 'profesional', alternativas: [alternativa, 'basura'] }, 409))).api.crearTurno(ALTA);
    expect(r).toEqual({ ok: false, error: { tipo: 'conflicto', motivo: 'profesional', alternativas: [alternativa] } });
  });

  it.each([
    [422, { detail: 'x', motivo: 'fuera_de_disponibilidad' }, { tipo: 'fuera_de_disponibilidad' }],
    [422, { detail: 'x', motivo: 'inicio_pasado' }, { tipo: 'inicio_pasado' }],
    [422, { detail: [{ loc: ['body', 'telefono'], msg: 'Value error, telefono debe tener formato E.164' }] }, { tipo: 'validacion', mensaje: 'telefono debe tener formato E.164' }],
    [403, { detail: 'x' }, { tipo: 'sin_permiso' }],
    [500, { detail: 'x' }, { tipo: 'desconocido' }],
  ])('un %i se traduce a un rechazo de negocio', async (status, cuerpo, error) => {
    const r = await api(servidor(() => json(cuerpo, status))).api.crearTurno(ALTA);
    expect(r).toEqual({ ok: false, error });
  });

  it('una falla de red en el alta es "desconocido", no una excepción', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'));
    expect(await api(fetchFn).api.crearTurno(ALTA)).toEqual({ ok: false, error: { tipo: 'desconocido' } });
  });
});

describe('crearApi: marcar y cancelar', () => {
  it.each(['atendido', 'ausente', 'cancelar'] as const)('POST /api/panel/turnos/7/%s', async (accion) => {
    const cambio = { turno_id: 7, estado: 'ausente', estado_sena: 'no_reembolsado' };
    const fetchFn = servidor(() => json(cambio));
    expect(await api(fetchFn).api.marcar(7, accion)).toEqual({ ok: true, valor: cambio });
    expect(urlDe(fetchFn.mock.calls[0])).toBe(`/api/panel/turnos/7/${accion}`);
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe('POST');
  });

  it.each([
    [409, { detail: 'x', motivo: 'marcado_no_habilitado', habilitado_desde: '2031-11-18T09:10:00-03:00' }, { tipo: 'marcado_no_habilitado', habilitadoDesde: '2031-11-18T09:10:00-03:00' }],
    [409, { detail: 'x', motivo: 'fuera_de_plazo', limite_cambios: '2031-11-17T09:00:00-03:00' }, { tipo: 'fuera_de_plazo', limiteCambios: '2031-11-17T09:00:00-03:00' }],
    [409, { detail: 'x', motivo: 'transicion_invalida' }, { tipo: 'transicion_invalida' }],
    [404, { detail: 'x' }, { tipo: 'no_encontrado' }],
    [403, { detail: 'x' }, { tipo: 'sin_permiso' }],
    [503, { detail: 'reintentar' }, { tipo: 'reintentar' }],
    [500, { detail: 'x' }, { tipo: 'desconocido' }],
  ])('un %i se traduce a un rechazo de negocio', async (status, cuerpo, error) => {
    expect(await api(servidor(() => json(cuerpo, status))).api.marcar(7, 'ausente')).toEqual({ ok: false, error });
  });
});
