import { describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorApiPanel, ErrorDeRespuesta } from './api';
import { Sesion } from './sesion';

/** Contratos de C-13: descarga autenticada del CSV, consulta de auditoría y directorio de usuarios. */

function json(cuerpo: unknown, status = 200, cabeceras: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json', ...cabeceras } });
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

function leerTexto(blob: Blob): Promise<string> {
  return new Promise((resolver, rechazar) => {
    const lector = new FileReader();
    lector.onload = () => {
      resolver(typeof lector.result === 'string' ? lector.result : '');
    };
    lector.onerror = () => {
      rechazar(new Error('lectura fallida'));
    };
    lector.readAsText(blob);
  });
}

const SOLO_TURNOS = { entidad: 'turnos', desde: null, hasta: null, incluirInactivos: false } as const;
const CSV = '﻿id,inicio\r\n1,2026-11-16T09:00:00-03:00\r\n';

function archivo(status = 200, cabeceras: Record<string, string> = {}): Response {
  return new Response(CSV, {
    status,
    headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="turnos_2026-11-13.csv"', ...cabeceras },
  });
}

describe('descargarExportacion()', () => {
  it('pide el CSV con el access en la cabecera (nunca en la URL) y devuelve el Blob con el nombre del servidor', async () => {
    const fetchFn = servidor(() => archivo());
    const r = await api(fetchFn).descargarExportacion(
      { entidad: 'cierres_caja', desde: '2026-11-01', hasta: '2026-11-30', incluirInactivos: false },
      '2026-11-13',
    );
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/export?entidad=cierres_caja&formato=csv&desde=2026-11-01&hasta=2026-11-30');
    expect(urlDe(fetchFn.mock.calls[0])).not.toContain('ACCESS');
    expect(new Headers(fetchFn.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer ACCESS-1');
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.valor.nombre).toBe('turnos_2026-11-13.csv');
    // El Blob conserva los bytes tal cual llegaron (con el BOM): se compara el tamaño y el texto decodificado.
    expect(r.valor.blob.size).toBe(new TextEncoder().encode(CSV).length);
    expect(await leerTexto(r.valor.blob)).toBe(CSV.slice(1));
    expect(r.valor.blob.type).toContain('text/csv');
  });

  it('sin Content-Disposition arma entidad_fecha.csv', async () => {
    const fetchFn = servidor(() => new Response(CSV, { status: 200, headers: { 'Content-Type': 'text/csv' } }));
    const r = await api(fetchFn).descargarExportacion({ ...SOLO_TURNOS, entidad: 'pacientes' }, '2026-11-13');
    expect(r.ok && r.valor.nombre).toBe('pacientes_2026-11-13.csv');
  });

  it.each([
    [403, {}, { tipo: 'sin_permiso' }],
    [422, {}, { tipo: 'validacion' }],
    [500, {}, { tipo: 'servidor' }],
    [503, {}, { tipo: 'servidor' }],
    [429, { 'Retry-After': '600' }, { tipo: 'limite', minutos: 10 }],
    [429, {}, { tipo: 'limite', minutos: 1 }],
  ])('el estado %i se traduce a un error de la pantalla', async (status, cabeceras, esperado) => {
    const fetchFn = servidor(() => json({ detail: 'x' }, status, cabeceras));
    expect(await api(fetchFn).descargarExportacion(SOLO_TURNOS, '2026-11-13')).toEqual({ ok: false, error: esperado });
  });

  it('un corte de red es un error de red, no una excepción', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.reject(new TypeError('Failed to fetch')));
    expect(await api(fetchFn).descargarExportacion(SOLO_TURNOS, '2026-11-13')).toEqual({ ok: false, error: { tipo: 'red' } });
  });

  it('con el access vencido renueva una vez y reintenta (como el resto de la API)', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ detail: 'vencido' }, 401))
      .mockResolvedValueOnce(json({ access_token: 'ACCESS-2' }))
      .mockResolvedValueOnce(archivo());
    const r = await api(fetchFn).descargarExportacion(SOLO_TURNOS, '2026-11-13');
    expect(r.ok).toBe(true);
    expect(fetchFn).toHaveBeenCalledTimes(3);
  });
});

const REGISTRO = {
  id: 91,
  fecha_hora: '2026-11-13T09:05:00-03:00',
  usuario: { id: 3, nombre_completo: 'Recepción Ficticia' },
  accion: 'cierre_caja',
  tipo: 'cierre_caja',
  tipo_etiqueta: 'Cierre de caja',
  entidad: 'cierre_caja',
  entidad_id: '42',
  datos_antes: null,
  datos_despues: { total_neto: '15000.00' },
  ip: '203.0.113.20',
};
const SIN_FILTROS = { desde: null, hasta: null, usuarioId: null, tipo: null, entidad: null, entidadId: null, cursor: null };

describe('consultarAuditoria()', () => {
  it('manda solo los filtros con valor y devuelve la página validada', async () => {
    const fetchFn = servidor(() => json({ items: [REGISTRO, { ...REGISTRO, id: 90, usuario: null, ip: null }], siguiente: 'abc' }));
    const pagina = await api(fetchFn).consultarAuditoria({ ...SIN_FILTROS, tipo: 'cierre_caja', cursor: 'xyz' });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/auditoria?tipo=cierre_caja&cursor=xyz');
    expect(pagina.items.map((i) => i.id)).toEqual([91, 90]);
    expect(pagina.items[1]?.usuario).toBeNull();
    expect(pagina.siguiente).toBe('abc');
  });

  it('sin filtros pide la ruta limpia', async () => {
    const fetchFn = servidor(() => json({ items: [], siguiente: null }));
    expect(await api(fetchFn).consultarAuditoria(SIN_FILTROS)).toEqual({ items: [], siguiente: null });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/auditoria');
  });

  it('un 403 conserva el estado para que la pantalla diga que falta permiso', async () => {
    const fetchFn = servidor(() => json({ detail: 'Rol requerido: admin' }, 403));
    await expect(api(fetchFn).consultarAuditoria(SIN_FILTROS)).rejects.toMatchObject({ status: 403 });
    await expect(api(fetchFn).consultarAuditoria(SIN_FILTROS)).rejects.toBeInstanceOf(ErrorApiPanel);
  });

  it.each([[{ items: [{ id: 1 }], siguiente: null }], [{ items: [], siguiente: 7 }], [{ siguiente: null }], [null]])(
    'una respuesta que no cumple el contrato se descarta (%j)',
    async (cuerpo) => {
      const fetchFn = servidor(() => json(cuerpo));
      await expect(api(fetchFn).consultarAuditoria(SIN_FILTROS)).rejects.toBeInstanceOf(ErrorDeRespuesta);
    },
  );
});

describe('listarUsuarios()', () => {
  it('devuelve el directorio validado', async () => {
    const fetchFn = servidor(() => json([{ id: 3, nombre_completo: 'Recepción Ficticia', activo: true }, { id: 4, nombre_completo: 'Ex Ficticio', activo: false }]));
    const lista = await api(fetchFn).listarUsuarios();
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/usuarios');
    expect(lista.map((u) => [u.id, u.activo])).toEqual([[3, true], [4, false]]);
  });

  it('un elemento mal formado descarta toda la respuesta', async () => {
    const fetchFn = servidor(() => json([{ id: 3, nombre_completo: 'Sin estado' }]));
    await expect(api(fetchFn).listarUsuarios()).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });
});
