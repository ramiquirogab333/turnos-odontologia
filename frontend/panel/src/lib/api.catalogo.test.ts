import { describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorApiPanel, ErrorDeRespuesta } from './api';
import { ErrorSesion, Sesion } from './sesion';

/** Contratos de C-14: lectura del catálogo en paralelo, escrituras por recurso, impacto y errores con motivo. */

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
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

const cuerpoEnviado = (llamada: Parameters<typeof fetch> | undefined): string => {
  const cuerpo = llamada?.[1]?.body;
  return typeof cuerpo === 'string' ? cuerpo : '';
};

const TRATAMIENTO = { id: 1, nombre: 'Limpieza dental', duracion_minutos: 45, precio_base: '18500.00', activo: true };
const PROFESIONAL = { id: 2, nombre: 'Dra. Ana Ficticia', matricula: 'MP-99001', especialidad: '', activo: true };
const SILLON = { id: 3, nombre: 'Sillón 1', estado: 'activo' };
const FRANJA = { id: 4, profesional_id: 2, dia_semana: 0, hora_inicio: '09:00:00', hora_fin: '13:00:00', sillon_defecto_id: null, activo: true };

const POR_RUTA: Record<string, unknown> = {
  '/api/admin/tratamientos': [TRATAMIENTO],
  '/api/admin/profesionales': [PROFESIONAL],
  '/api/admin/sillones': [SILLON],
  '/api/admin/disponibilidad': [FRANJA],
};

describe('catalogo()', () => {
  it('dispara las cuatro lecturas antes de resolver la primera (sin cascada, R2)', async () => {
    const resolvers: (() => void)[] = [];
    const fetchFn = vi.fn<typeof fetch>((entrada) => {
      const ruta = typeof entrada === 'string' ? entrada : '';
      return new Promise<Response>((resolver) => {
        resolvers.push(() => {
          resolver(json(POR_RUTA[ruta]));
        });
      });
    });
    const pendiente = api(fetchFn).catalogo();
    await vi.waitFor(() => {
      expect(fetchFn).toHaveBeenCalledTimes(4);
    });
    expect(fetchFn.mock.calls.map(urlDe).sort()).toEqual(Object.keys(POR_RUTA).sort());
    resolvers.forEach((resolver) => {
      resolver();
    });
    const catalogo = await pendiente;
    expect(catalogo.tratamientos).toEqual([TRATAMIENTO]);
    expect(catalogo.profesionales[0]?.nombre).toBe('Dra. Ana Ficticia');
    expect(catalogo.sillones[0]?.estado).toBe('activo');
    expect(catalogo.franjas[0]?.hora_inicio).toBe('09:00:00');
  });

  it('una respuesta malformada se descarta con ErrorDeRespuesta', async () => {
    const fetchFn = vi.fn<typeof fetch>((entrada) => {
      const ruta = typeof entrada === 'string' ? entrada : '';
      return Promise.resolve(json(ruta.endsWith('sillones') ? [{ id: 3, nombre: 'Sillón 1', estado: 'roto' }] : POR_RUTA[ruta]));
    });
    await expect(api(fetchFn).catalogo()).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('si una lectura falla con 500 todo el catálogo falla (no hay listas vacías engañosas)', async () => {
    const fetchFn = vi.fn<typeof fetch>((entrada) => {
      const ruta = typeof entrada === 'string' ? entrada : '';
      return Promise.resolve(ruta.endsWith('sillones') ? json({ detail: 'boom' }, 500) : json(POR_RUTA[ruta]));
    });
    await expect(api(fetchFn).catalogo()).rejects.toBeInstanceOf(ErrorApiPanel);
  });
});

describe('impacto()', () => {
  it('pide /impacto del recurso y valida la respuesta', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(json({ turnos_futuros: 3, primero: '2026-11-16T14:30:00-03:00' })));
    const r = await api(fetchFn).impactoCatalogo('disponibilidad', 4);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/admin/disponibilidad/4/impacto');
    expect(r).toEqual({ turnos_futuros: 3, primero: '2026-11-16T14:30:00-03:00' });
  });

  it('una respuesta sin el contrato falla con ErrorDeRespuesta y un 404 con ErrorApiPanel', async () => {
    await expect(api(vi.fn<typeof fetch>(() => Promise.resolve(json({ turnos_futuros: 'tres' })))).impactoCatalogo('sillones', 1)).rejects.toBeInstanceOf(
      ErrorDeRespuesta,
    );
    await expect(api(vi.fn<typeof fetch>(() => Promise.resolve(json({ detail: 'no existe' }, 404)))).impactoCatalogo('sillones', 9)).rejects.toMatchObject({
      status: 404,
    });
  });
});

describe('escrituras por recurso', () => {
  it('crear: POST con JSON y valida la fila devuelta', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(json(TRATAMIENTO, 201)));
    const datos = { nombre: 'Limpieza dental', duracion_minutos: 45, precio_base: '18500.00' };
    const r = await api(fetchFn).crearCatalogo('tratamientos', datos);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/admin/tratamientos');
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(JSON.parse(cuerpoEnviado(fetchFn.mock.calls[0]))).toEqual(datos);
    expect(r).toEqual({ ok: true, valor: TRATAMIENTO });
  });

  it('actualizar: PUT parcial a /{id}', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(json({ ...FRANJA, activo: false })));
    const r = await api(fetchFn).actualizarCatalogo('disponibilidad', 4, { activo: false });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/admin/disponibilidad/4');
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe('PUT');
    expect(JSON.parse(cuerpoEnviado(fetchFn.mock.calls[0]))).toEqual({ activo: false });
    expect(r.ok && r.valor).toMatchObject({ id: 4, activo: false });
  });

  it('borrar: DELETE y 204 es éxito', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(new Response(null, { status: 204 })));
    const r = await api(fetchFn).borrarCatalogo('sillones', 3);
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe('DELETE');
    expect(r).toEqual({ ok: true, valor: null });
  });

  it('un 409 en_uso conserva el motivo', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(json({ detail: 'en uso', motivo: 'en_uso' }, 409)));
    expect(await api(fetchFn).borrarCatalogo('tratamientos', 1)).toEqual({ ok: false, error: { tipo: 'en_uso' } });
  });

  it('un 409 duplicado trae el campo y un 409 franja_superpuesta la franja que choca', async () => {
    const duplicado = vi.fn<typeof fetch>(() => Promise.resolve(json({ detail: 'x', motivo: 'duplicado', campo: 'matricula' }, 409)));
    expect(await api(duplicado).crearCatalogo('profesionales', { nombre: 'Dr. Juan Ejemplo', matricula: 'mp-99001', especialidad: '' })).toEqual({
      ok: false,
      error: { tipo: 'duplicado', campo: 'matricula' },
    });
    const pisada = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        json({ detail: 'x', motivo: 'franja_superpuesta', franja: { id: 4, dia_semana: 0, hora_inicio: '09:00:00', hora_fin: '13:00:00' } }, 409),
      ),
    );
    const r = await api(pisada).crearCatalogo('disponibilidad', {
      profesional_id: 2,
      dia_semana: 0,
      hora_inicio: '12:00',
      hora_fin: '15:00',
      sillon_defecto_id: null,
    });
    expect(r).toEqual({
      ok: false,
      error: { tipo: 'franja_superpuesta', franja: { id: 4, dia_semana: 0, hora_inicio: '09:00:00', hora_fin: '13:00:00' } },
    });
  });

  it('un 422 de FastAPI se traduce al campo y mensaje; 403, 404 y otros se distinguen', async () => {
    const validacion = vi.fn<typeof fetch>(() =>
      Promise.resolve(json({ detail: [{ loc: ['body', 'duracion_minutos'], msg: 'Value error, duracion_minutos debe ser múltiplo de 5' }] }, 422)),
    );
    expect(await api(validacion).actualizarCatalogo('tratamientos', 1, { duracion_minutos: 7 })).toEqual({
      ok: false,
      error: { tipo: 'validacion', campo: 'duracion_minutos', mensaje: 'duracion_minutos debe ser múltiplo de 5' },
    });
    const estados = [
      [403, { tipo: 'sin_permiso' }],
      [404, { tipo: 'no_encontrado' }],
      [500, { tipo: 'desconocido' }],
    ] as const;
    for (const [status, esperado] of estados) {
      const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(json({ detail: 'x' }, status)));
      expect(await api(fetchFn).borrarCatalogo('sillones', 1)).toEqual({ ok: false, error: esperado });
    }
  });

  it('una fila devuelta que no cumple el contrato es un error desconocido, no un dato inventado', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(json({ id: 'uno' }, 201)));
    expect(await api(fetchFn).crearCatalogo('sillones', { nombre: 'Sillón 2', estado: 'activo' })).toEqual({
      ok: false,
      error: { tipo: 'desconocido' },
    });
  });

  it('si la sesión terminó, la escritura propaga ErrorSesion', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(json({}, 401)));
    const sesion = new Sesion({ fetchFn, candados: null, canal: null });
    sesion.fijarToken('ACCESS-1');
    await expect(crearApi(sesion, fetchFn).crearCatalogo('sillones', { nombre: 'S', estado: 'activo' })).rejects.toBeInstanceOf(ErrorSesion);
  });
});
