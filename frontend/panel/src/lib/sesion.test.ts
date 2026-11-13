import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ErrorDeRed, Sesion, type Candados, type Canal } from './sesion';

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

type Manejador = (url: string, init?: RequestInit) => Response | Promise<Response> | undefined;

function servidor(...manejadores: Manejador[]) {
  const mock = vi.fn<typeof fetch>(async (entrada, init) => {
    const url = entrada instanceof Request ? entrada.url : String(entrada);
    for (const m of manejadores) {
      const r = await m(url, init);
      if (r) return r.clone();
    }
    return json({ detail: 'sin ruta' }, 500);
  });
  return mock;
}

const refrescar = (token: string): Manejador => (url) =>
  url === '/api/auth/refresh' ? json({ access_token: token, token_type: 'bearer' }) : undefined;

class CanalFalso implements Canal {
  enviados: unknown[] = [];
  oyente: ((ev: { data: unknown }) => void) | null = null;
  postMessage(msg: unknown): void {
    this.enviados.push(msg);
  }
  addEventListener(_tipo: 'message', cb: (ev: { data: unknown }) => void): void {
    this.oyente = cb;
  }
  close(): void {
    this.oyente = null;
  }
  recibir(data: unknown): void {
    this.oyente?.({ data });
  }
}

describe('Sesion', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('ingresar', () => {
    it('guarda el access solo en memoria: nada en localStorage, sessionStorage ni cookies legibles', async () => {
      const fetchFn = servidor((url) =>
        url === '/api/auth/login' ? json({ access_token: 'ACCESS-SINTETICO', token_type: 'bearer' }) : undefined,
      );
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      expect(await sesion.ingresar('recepcion@turnos.test', 'clave-sintetica-123')).toEqual({ ok: true });
      expect(sesion.token()).toBe('ACCESS-SINTETICO');
      expect(localStorage.length).toBe(0);
      expect(sessionStorage.length).toBe(0);
      expect(document.cookie).not.toContain('ACCESS-SINTETICO');
      const [, init] = fetchFn.mock.calls[0] ?? [];
      expect(init?.method).toBe('POST');
      expect(JSON.parse(typeof init?.body === 'string' ? init.body : '')).toEqual({ email: 'recepcion@turnos.test', password: 'clave-sintetica-123' });
    });

    it.each([
      [401, 'credenciales'],
      [500, 'servidor'],
      [503, 'servidor'],
    ] as const)('un %i es "%s" y no deja sesión', async (status, motivo) => {
      const fetchFn = servidor(() => json({ detail: 'x' }, status));
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      expect(await sesion.ingresar('a@turnos.test', 'clave-sintetica-123')).toEqual({ ok: false, motivo });
      expect(sesion.token()).toBeNull();
    });

    it.each([
      ['600', 10],
      ['20', 1],
      ['61', 2],
    ] as const)('un 429 con Retry-After %s es "limite" de %i minuto(s) y no deja sesión', async (retryAfter, minutos) => {
      const fetchFn = servidor(() => new Response(JSON.stringify({ detail: 'x', motivo: 'demasiados_intentos' }), { status: 429, headers: { 'Content-Type': 'application/json', 'Retry-After': retryAfter } }));
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      expect(await sesion.ingresar('a@turnos.test', 'clave-sintetica-123')).toEqual({ ok: false, motivo: 'limite', minutos });
      expect(sesion.token()).toBeNull();
    });

    it('un 429 sin Retry-After cae en 1 minuto', async () => {
      const sesion = new Sesion({ fetchFn: servidor(() => json({ detail: 'x' }, 429)), candados: null, canal: null });
      expect(await sesion.ingresar('a@turnos.test', 'clave-sintetica-123')).toEqual({ ok: false, motivo: 'limite', minutos: 1 });
    });

    it('una falla de red es "red"', async () => {
      const fetchFn = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'));
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      expect(await sesion.ingresar('a@turnos.test', 'clave-sintetica-123')).toEqual({ ok: false, motivo: 'red' });
    });

    it('una respuesta 200 sin access_token no abre sesión', async () => {
      const fetchFn = servidor(() => json({ otra_cosa: 1 }));
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      expect(await sesion.ingresar('a@turnos.test', 'clave-sintetica-123')).toEqual({ ok: false, motivo: 'servidor' });
      expect(sesion.token()).toBeNull();
    });
  });

  describe('renovar', () => {
    it('envía POST /api/auth/refresh con X-Panel-Csrf y sin cuerpo, y guarda el access', async () => {
      const fetchFn = servidor(refrescar('ACCESS-1'));
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      expect(await sesion.renovar()).toBe('ACCESS-1');
      const [url, init] = fetchFn.mock.calls[0] ?? [];
      expect(url).toBe('/api/auth/refresh');
      expect(init?.method).toBe('POST');
      expect(new Headers(init?.headers).get('X-Panel-Csrf')).toBe('1');
      expect(init?.body).toBeUndefined();
      expect(sesion.token()).toBe('ACCESS-1');
    });

    it('un 401 significa sin sesión: devuelve null y limpia el access', async () => {
      const sesion = new Sesion({ fetchFn: servidor(() => json({ detail: 'x' }, 401)), candados: null, canal: null });
      sesion.fijarToken('VIEJO');
      expect(await sesion.renovar()).toBeNull();
      expect(sesion.token()).toBeNull();
    });

    it('un 429 al renovar lanza ErrorDeRed y NO cierra la sesión ni limpia el access', async () => {
      const sesion = new Sesion({ fetchFn: servidor(() => json({ detail: 'x', motivo: 'demasiados_intentos' }, 429)), candados: null, canal: null });
      const cierres: Array<string | null> = [];
      sesion.fijarToken('VIGENTE');
      sesion.alCambiar((t) => cierres.push(t));
      await expect(sesion.renovar()).rejects.toBeInstanceOf(ErrorDeRed);
      expect(sesion.token()).toBe('VIGENTE');
      expect(cierres).toEqual([]);
    });

    it.each([500, 503])('un %i o una falla de red no es "sin sesión": lanza ErrorDeRed y conserva el access', async (status) => {
      const sesion = new Sesion({ fetchFn: servidor(() => json({ detail: 'x' }, status)), candados: null, canal: null });
      sesion.fijarToken('VIEJO');
      await expect(sesion.renovar()).rejects.toBeInstanceOf(ErrorDeRed);
      expect(sesion.token()).toBe('VIEJO');
      const caida = new Sesion({ fetchFn: vi.fn<typeof fetch>().mockRejectedValue(new TypeError('x')), candados: null, canal: null });
      await expect(caida.renovar()).rejects.toBeInstanceOf(ErrorDeRed);
    });

    it('dos renovaciones simultáneas en la misma pestaña comparten un único pedido', async () => {
      const fetchFn = servidor(refrescar('ACCESS-2'));
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      const [a, b] = await Promise.all([sesion.renovar(), sesion.renovar()]);
      expect([a, b]).toEqual(['ACCESS-2', 'ACCESS-2']);
      expect(fetchFn).toHaveBeenCalledTimes(1);
      await sesion.renovar(); // ya terminó la anterior: se puede pedir otra
      expect(fetchFn).toHaveBeenCalledTimes(2);
    });

    it('usa navigator.locks con el nombre panel-refresh para coordinar entre pestañas', async () => {
      const nombres: string[] = [];
      const candados: Candados = {
        request: async <T,>(nombre: string, callback: () => Promise<T>): Promise<T> => {
          nombres.push(nombre);
          return callback();
        },
      };
      const sesion = new Sesion({ fetchFn: servidor(refrescar('ACCESS-3')), candados, canal: null });
      expect(await sesion.renovar()).toBe('ACCESS-3');
      expect(nombres).toEqual(['panel-refresh']);
    });

    it('si el navegador no tiene candados, renueva igual', async () => {
      vi.stubGlobal('navigator', { ...navigator, locks: undefined });
      const sesion = new Sesion({ fetchFn: servidor(refrescar('ACCESS-4')), canal: null });
      expect(await sesion.renovar()).toBe('ACCESS-4');
    });

    it('la segunda pestaña espera el candado y recién ahí pide el refresh (usa la cookie ya rotada)', async () => {
      const orden: string[] = [];
      let cola: Promise<unknown> = Promise.resolve();
      const candados: Candados = {
        request: <T,>(_n: string, callback: () => Promise<T>): Promise<T> => {
          const turno = cola.then(callback);
          cola = turno.catch(() => undefined);
          return turno;
        },
      };
      const fetchFn = vi.fn<typeof fetch>(async () => {
        orden.push('pedido');
        await Promise.resolve();
        orden.push('respuesta');
        return json({ access_token: `T${String(orden.length)}`, token_type: 'bearer' });
      });
      const pestanaA = new Sesion({ fetchFn, candados, canal: null });
      const pestanaB = new Sesion({ fetchFn, candados, canal: null });
      await Promise.all([pestanaA.renovar(), pestanaB.renovar()]);
      expect(orden).toEqual(['pedido', 'respuesta', 'pedido', 'respuesta']); // nunca dos pedidos entrelazados
    });
  });

  describe('salir y las otras pestañas', () => {
    it('salir revoca con el access, limpia la sesión y avisa por el canal', async () => {
      const canal = new CanalFalso();
      const fetchFn = servidor((url) => (url === '/api/auth/logout' ? json({ detalle: 'sesión revocada' }) : undefined));
      const sesion = new Sesion({ fetchFn, candados: null, canal });
      sesion.fijarToken('ACCESS-5');
      expect(await sesion.salir()).toBe('ok');
      const [url, init] = fetchFn.mock.calls[0] ?? [];
      expect(url).toBe('/api/auth/logout');
      expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer ACCESS-5');
      expect(sesion.token()).toBeNull();
      expect(canal.enviados).toEqual(['salio']);
    });

    it('si falla la red no cierra la sesión local y lo informa para reintentar', async () => {
      const canal = new CanalFalso();
      const fetchFn = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'));
      const sesion = new Sesion({ fetchFn, candados: null, canal });
      sesion.fijarToken('ACCESS-6');
      expect(await sesion.salir()).toBe('sin_red');
      expect(sesion.token()).toBe('ACCESS-6');
      expect(canal.enviados).toEqual([]);
    });

    it('si el access ya venció renueva una vez y reintenta el logout', async () => {
      let logout = 0;
      const fetchFn = servidor(
        refrescar('ACCESS-NUEVO'),
        (url, init) => {
          if (url !== '/api/auth/logout') return undefined;
          logout += 1;
          const bearer = new Headers(init?.headers).get('Authorization');
          return bearer === 'Bearer ACCESS-NUEVO' ? json({ detalle: 'ok' }) : json({ detail: 'vencido' }, 401);
        },
      );
      const sesion = new Sesion({ fetchFn, candados: null, canal: null });
      sesion.fijarToken('ACCESS-VIEJO');
      expect(await sesion.salir()).toBe('ok');
      expect(logout).toBe(2);
      expect(sesion.token()).toBeNull();
    });

    it('un aviso "salio" de otra pestaña cierra esta sesión y avisa a los oyentes', () => {
      const canal = new CanalFalso();
      const sesion = new Sesion({ fetchFn: servidor(), candados: null, canal });
      sesion.fijarToken('ACCESS-7');
      const oyente = vi.fn();
      sesion.alCambiar(oyente);
      canal.recibir('salio');
      expect(sesion.token()).toBeNull();
      expect(oyente).toHaveBeenLastCalledWith(null, 'otra_pestana');
    });

    it('un mensaje desconocido del canal se ignora', () => {
      const canal = new CanalFalso();
      const sesion = new Sesion({ fetchFn: servidor(), candados: null, canal });
      sesion.fijarToken('ACCESS-8');
      canal.recibir({ cualquier: 'cosa' });
      expect(sesion.token()).toBe('ACCESS-8');
    });

    it('el oyente se puede quitar', () => {
      const sesion = new Sesion({ fetchFn: servidor(), candados: null, canal: null });
      const oyente = vi.fn();
      const quitar = sesion.alCambiar(oyente);
      quitar();
      sesion.fijarToken('X');
      expect(oyente).not.toHaveBeenCalled();
    });
  });
});
