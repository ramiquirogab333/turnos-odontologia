import { describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorDeRespuesta } from './api';
import { Sesion } from './sesion';

/** Contratos de C-10: conexión, conflictos y su resolución, y los campos nuevos de la agenda y del alta. */

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function servidor(responder: () => Response) {
  return vi.fn<typeof fetch>(() => Promise.resolve(responder()));
}

function api(fetchFn: typeof fetch) {
  const sesion = new Sesion({ fetchFn, candados: null, canal: null });
  sesion.fijarToken('ACCESS-1');
  return crearApi(sesion, fetchFn);
}

const urlDe = (llamada: Parameters<typeof fetch> | undefined): string => {
  const u = llamada?.[0];
  if (u === undefined) return '';
  return typeof u === 'string' ? u : u instanceof URL ? u.href : u.url;
};
const metodoDe = (llamada: Parameters<typeof fetch> | undefined): string | undefined => llamada?.[1]?.method;
const cuerpoDe = (llamada: Parameters<typeof fetch> | undefined): unknown => {
  const cuerpo = llamada?.[1]?.body;
  return typeof cuerpo === 'string' ? (JSON.parse(cuerpo) as unknown) : undefined;
};

const BASE = '/api/panel/google-calendar';
const CONEXION = {
  profesional_id: 7,
  profesional_nombre: 'Dra. Ana Ficticia',
  estado: 'activa',
  cuenta_email: 'ana.prueba@example.com',
  ultima_sync_ok_en: '2031-11-18T08:30:00-03:00',
  conflictos_abiertos: 1,
  indicacion: null,
};
const CONFLICTO = {
  id: 21,
  tipo: 'movido_en_google',
  estado: 'abierto',
  criterio: 'El evento se movió en Google Calendar.',
  turno_id: 11,
  profesional_id: 7,
  profesional_nombre: 'Dra. Ana Ficticia',
  tratamiento: 'Limpieza dental',
  sistema_inicio: '2031-11-18T10:00:00-03:00',
  sistema_fin: '2031-11-18T10:30:00-03:00',
  google_inicio: '2031-11-18T12:00:00-03:00',
  google_fin: '2031-11-18T12:30:00-03:00',
  acciones: ['restaurar_en_google', 'desvincular'],
  resolucion: null,
  detectado_en: '2031-11-18T09:00:00-03:00',
  resuelto_en: null,
};

describe('conexionesGoogle()', () => {
  it('pide el estado por profesional con el access token y devuelve la lista validada', async () => {
    const fetchFn = servidor(() => json([CONEXION, { ...CONEXION, profesional_id: 8, estado: 'sin_conectar', cuenta_email: null, ultima_sync_ok_en: null, conflictos_abiertos: 0 }]));
    const lista = await api(fetchFn).conexionesGoogle();
    expect(lista.map((c) => c.estado)).toEqual(['activa', 'sin_conectar']);
    expect(urlDe(fetchFn.mock.calls[0])).toBe(`${BASE}/conexiones`);
    expect(new Headers(fetchFn.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer ACCESS-1');
  });

  it.each([
    ['estado desconocido', [{ ...CONEXION, estado: 'perdida' }]],
    ['conflictos que no son número', [{ ...CONEXION, conflictos_abiertos: '1' }]],
    ['no es una lista', { items: [] }],
    ['email que no es texto', [{ ...CONEXION, cuenta_email: 5 }]],
  ])('una respuesta fuera de contrato se descarta (%s)', async (_caso, cuerpo) => {
    await expect(api(servidor(() => json(cuerpo))).conexionesGoogle()).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });
});

describe('conflictosGoogle()', () => {
  it('pide los abiertos y acepta un conflicto de borrado sin horario de Google', async () => {
    const borrado = { ...CONFLICTO, id: 22, tipo: 'borrado_en_google', google_inicio: null, google_fin: null };
    const fetchFn = servidor(() => json([CONFLICTO, borrado]));
    const lista = await api(fetchFn).conflictosGoogle();
    expect(lista).toHaveLength(2);
    expect(urlDe(fetchFn.mock.calls[0])).toBe(`${BASE}/conflictos?estado=abierto`);
  });

  it.each([
    ['tipo desconocido', [{ ...CONFLICTO, tipo: 'otro' }]],
    ['acción desconocida', [{ ...CONFLICTO, acciones: ['borrar_todo'] }]],
    ['sin horario del sistema', [{ ...CONFLICTO, sistema_inicio: null }]],
  ])('descarta una respuesta fuera de contrato (%s)', async (_caso, cuerpo) => {
    await expect(api(servidor(() => json(cuerpo))).conflictosGoogle()).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });
});

describe('iniciarGoogle()', () => {
  it('hace POST sin cuerpo y devuelve la URL de autorización', async () => {
    const fetchFn = servidor(() => json({ url_autorizacion: 'https://accounts.google.com/o/oauth2/v2/auth?state=x' }));
    const r = await api(fetchFn).iniciarGoogle();
    expect(r).toEqual({ ok: true, valor: { url_autorizacion: 'https://accounts.google.com/o/oauth2/v2/auth?state=x' } });
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('POST');
    expect(urlDe(fetchFn.mock.calls[0])).toBe(`${BASE}/conexion/iniciar`);
  });

  it.each([
    [403, {}, 'sin_permiso'],
    [409, { motivo: 'conexion_activa' }, 'conexion_activa'],
    [503, { motivo: 'gcal_no_configurado' }, 'no_configurado'],
    [500, {}, 'desconocido'],
  ])('traduce el %i a "%s"', async (status, cuerpo, tipo) => {
    const r = await api(servidor(() => json(cuerpo, status))).iniciarGoogle();
    expect(r).toEqual({ ok: false, error: { tipo } });
  });
});

describe('desconectarGoogle()', () => {
  it('hace DELETE a la profesional indicada y un 204 es éxito', async () => {
    const fetchFn = servidor(() => new Response(null, { status: 204 }));
    const r = await api(fetchFn).desconectarGoogle(7);
    expect(r).toEqual({ ok: true, valor: null });
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('DELETE');
    expect(urlDe(fetchFn.mock.calls[0])).toBe(`${BASE}/conexiones/7`);
  });

  it.each([
    [403, 'sin_permiso'],
    [404, 'no_encontrado'],
    [500, 'desconocido'],
  ])('traduce el %i a "%s"', async (status, tipo) => {
    const r = await api(servidor(() => json({}, status))).desconectarGoogle(7);
    expect(r).toEqual({ ok: false, error: { tipo } });
  });
});

describe('resolverConflicto()', () => {
  it('manda la acción elegida y devuelve el conflicto resuelto', async () => {
    const resuelto = { ...CONFLICTO, estado: 'resuelto', acciones: [], resolucion: 'restaurar_en_google', resuelto_en: '2031-11-18T09:10:00-03:00' };
    const fetchFn = servidor(() => json(resuelto));
    const r = await api(fetchFn).resolverConflicto(21, 'restaurar_en_google');
    expect(r.ok && r.valor.estado).toBe('resuelto');
    expect(urlDe(fetchFn.mock.calls[0])).toBe(`${BASE}/conflictos/21/resolver`);
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ accion: 'restaurar_en_google' });
  });

  it.each([
    [403, {}, 'sin_permiso'],
    [404, { motivo: 'conflicto_inexistente' }, 'no_encontrado'],
    [409, { motivo: 'conflicto_cerrado' }, 'conflicto_cerrado'],
    [422, { motivo: 'accion_no_valida' }, 'accion_no_valida'],
    [500, {}, 'desconocido'],
  ])('traduce el %i a "%s"', async (status, cuerpo, tipo) => {
    const r = await api(servidor(() => json(cuerpo, status))).resolverConflicto(21, 'revisado');
    expect(r).toEqual({ ok: false, error: { tipo } });
  });
});

describe('agenda() y crearTurno() con los campos nuevos', () => {
  const TURNO = {
    id: 11, inicio: '2031-11-18T09:00:00-03:00', fin: '2031-11-18T09:30:00-03:00', estado: 'reservado',
    bloquea_agenda: true, origen: 'web', profesional: { id: 1, nombre: 'Dra. Ana Ficticia' },
    sillon: { id: 2, nombre: 'Sillón 1' }, tratamiento: { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 },
    paciente_nombre: 'Carlos Sintético', paciente_telefono: null, sena: null, vence_en: null, acciones: [],
    calendario: { estado: 'sincronizado', conflicto_abierto: true },
  };

  it('la agenda trae las franjas de Google y el estado del calendario de cada turno', async () => {
    const franja = { profesional_id: 1, inicio: '2031-11-18T15:00:00-03:00', fin: '2031-11-18T16:00:00-03:00' };
    const respuesta = { vista: 'dia', desde: '2031-11-18', hasta: '2031-11-18', turnos: [TURNO], ocupados_google: [franja] };
    const agenda = await api(servidor(() => json(respuesta))).agenda({ vista: 'dia', fecha: '2031-11-18', profesionalId: null, sillonId: null });
    expect(agenda.ocupados_google).toEqual([franja]);
    expect(agenda.turnos[0]?.calendario).toEqual({ estado: 'sincronizado', conflicto_abierto: true });
  });

  it.each([
    ['calendario con estado desconocido', { ...TURNO, calendario: { estado: 'raro', conflicto_abierto: false } }],
    ['calendario sin conflicto_abierto', { ...TURNO, calendario: { estado: 'sin_evento' } }],
  ])('descarta un turno fuera de contrato (%s)', async (_caso, turno) => {
    const respuesta = { vista: 'dia', desde: '2031-11-18', hasta: '2031-11-18', turnos: [turno], ocupados_google: [] };
    await expect(
      api(servidor(() => json(respuesta))).agenda({ vista: 'dia', fecha: '2031-11-18', profesionalId: null, sillonId: null }),
    ).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('el alta devuelve el aviso de Google Calendar', async () => {
    const creado = {
      id: 99, inicio: '2031-11-18T15:00:00-03:00', fin: '2031-11-18T15:30:00-03:00', estado: 'reservado',
      origen: 'manual', profesional_id: 1, sillon_id: 2, tratamiento_id: 3, codigo_gestion: 'CODIGO-SINTETICO-0001',
      aviso_google_calendar: true,
    };
    const r = await api(servidor(() => json(creado, 201))).crearTurno({
      profesionalId: 1, tratamientoId: 3, inicio: creado.inicio, nombre: 'Carlos Sintético', telefono: '+5491144445555',
    });
    expect(r.ok && r.valor.aviso_google_calendar).toBe(true);
  });
});
