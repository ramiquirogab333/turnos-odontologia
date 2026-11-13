import { describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorApiPanel, ErrorDeRespuesta } from './api';
import { Sesion } from './sesion';

/** Contratos de C-09: listado de recordatorios, marcar enviado y marcar "no se pudo enviar". */

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

const LINK = 'https://wa.me/5491144445555?text=Hola%20Carlos';
const RECORDATORIO = {
  id: 7,
  turno_id: 11,
  estado: 'pendiente',
  motivo: null,
  turno_inicio: '2031-11-18T09:00:00-03:00',
  profesional: 'Dra. Ana Ficticia',
  tratamiento: 'Limpieza dental',
  contacto_nombre: 'Carlos Sintético',
  enviado_en: null,
  intentos_fallidos: 0,
  link: LINK,
};

describe('recordatorios()', () => {
  it('pide pendientes, fallidos y enviados con el access token y devuelve la lista validada', async () => {
    const fetchFn = servidor(() => json({ items: [RECORDATORIO] }));
    expect(await api(fetchFn).recordatorios()).toEqual([RECORDATORIO]);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/recordatorios?estado=pendiente&estado=fallido&estado=enviado');
    expect(new Headers(fetchFn.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer ACCESS-1');
  });

  it('acepta un recordatorio sin link (sin teléfono) y sin nombre', async () => {
    const fila = { ...RECORDATORIO, link: null, contacto_nombre: null, estado: 'fallido', motivo: 'sin_telefono' };
    expect(await api(servidor(() => json({ items: [fila] }))).recordatorios()).toEqual([fila]);
  });

  it.each([
    ['sin items', {}],
    ['estado desconocido', { items: [{ ...RECORDATORIO, estado: 'perdido' }] }],
    ['link que no es texto', { items: [{ ...RECORDATORIO, link: 42 }] }],
    ['id que no es número', { items: [{ ...RECORDATORIO, id: '7' }] }],
    ['un link que no es https de WhatsApp', { items: [{ ...RECORDATORIO, link: 'javascript:alert(1)' }] }],
  ])('una respuesta fuera de contrato se descarta (%s)', async (_caso, cuerpo) => {
    await expect(api(servidor(() => json(cuerpo))).recordatorios()).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('un error HTTP conserva el estado y el motivo', async () => {
    const error = await api(servidor(() => json({ detail: 'Rol requerido' }, 403))).recordatorios().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ErrorApiPanel);
    expect((error as ErrorApiPanel).status).toBe(403);
  });
});

describe('marcarRecordatorioEnviado()', () => {
  it('hace POST sin cuerpo a la ruta del recordatorio y devuelve la fila actualizada', async () => {
    const enviado = { ...RECORDATORIO, estado: 'enviado', enviado_en: '2031-11-17T10:00:00-03:00' };
    const fetchFn = servidor(() => json(enviado));
    const r = await api(fetchFn).marcarRecordatorioEnviado(7);
    expect(r).toEqual({ ok: true, valor: enviado });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/recordatorios/7/enviado');
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('POST');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toBeUndefined();
  });

  it.each([
    [409, { detail: 'x', motivo: 'recordatorio_no_vigente' }, 'no_vigente'],
    [404, { detail: 'x', motivo: 'recordatorio_inexistente' }, 'no_encontrado'],
    [403, { detail: 'x' }, 'sin_permiso'],
    [500, {}, 'desconocido'],
  ])('un %i se traduce a un error tipado (%s)', async (status, cuerpo, tipo) => {
    const r = await api(servidor(() => json(cuerpo, status))).marcarRecordatorioEnviado(7);
    expect(r).toEqual({ ok: false, error: { tipo } });
  });

  it('un 200 con un cuerpo roto es un error desconocido', async () => {
    const r = await api(servidor(() => json({ estado: 'enviado' }))).marcarRecordatorioEnviado(7);
    expect(r).toEqual({ ok: false, error: { tipo: 'desconocido' } });
  });

  it('sin red es un error desconocido, no una excepción', async () => {
    const r = await api(vi.fn<typeof fetch>(() => Promise.reject(new TypeError('red')))).marcarRecordatorioEnviado(7);
    expect(r).toEqual({ ok: false, error: { tipo: 'desconocido' } });
  });
});

describe('marcarRecordatorioFallido()', () => {
  it.each(['numero_invalido', 'sin_whatsapp', 'otro'] as const)('envía el motivo %s en el cuerpo', async (motivo) => {
    const fallido = { ...RECORDATORIO, estado: 'fallido', motivo };
    const fetchFn = servidor(() => json(fallido));
    const r = await api(fetchFn).marcarRecordatorioFallido(7, motivo);
    expect(r).toEqual({ ok: true, valor: fallido });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/recordatorios/7/fallido');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ motivo });
  });

  it('un 409 es no_vigente y un 422 es desconocido', async () => {
    expect(
      await api(servidor(() => json({ detail: 'x', motivo: 'recordatorio_no_vigente' }, 409))).marcarRecordatorioFallido(7, 'otro'),
    ).toEqual({ ok: false, error: { tipo: 'no_vigente' } });
    expect(await api(servidor(() => json({ detail: [] }, 422))).marcarRecordatorioFallido(7, 'otro')).toEqual({
      ok: false,
      error: { tipo: 'desconocido' },
    });
  });
});
