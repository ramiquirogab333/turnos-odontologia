import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { crearApi } from './lib/api';
import { Sesion, type Canal } from './lib/sesion';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

const ME = { id: 1, email: 'recepcion@turnos.test', nombre_completo: 'Rita Recepción', roles: ['recepcion'] };
const AGENDA = { vista: 'dia', desde: '2031-11-18', hasta: '2031-11-18', turnos: [] };
const OPCIONES = {
  profesionales: [{ id: 1, nombre: 'Dra. Ana Ficticia' }],
  sillones: [{ id: 2, nombre: 'Sillón 1' }],
  tratamientos: [{ id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 }],
  puede_escribir: true,
};

type Manejador = (url: string, init?: RequestInit) => Response | undefined;

/** Servidor falso: cada prueba declara qué responde a cada URL. */
function servidor(...manejadores: Manejador[]) {
  return vi.fn<typeof fetch>((entrada, init) => {
    const url = entrada instanceof Request ? entrada.url : urlDe(entrada);
    for (const m of manejadores) {
      const r = m(url, init);
      if (r) return Promise.resolve(r.clone());
    }
    return Promise.resolve(json({ detail: 'sin ruta' }, 500));
  });
}

const ruta = (metodoUrl: string, cuerpo: unknown, status = 200): Manejador => (url, init) =>
  `${init?.method ?? 'GET'} ${url.split('?')[0] ?? ''}` === metodoUrl ? json(cuerpo, status) : undefined;

const panel: Manejador[] = [
  ruta('GET /api/auth/me', ME),
  ruta('GET /api/panel/agenda', AGENDA),
  ruta('GET /api/panel/agenda/opciones', OPCIONES),
];

class CanalFalso implements Canal {
  oyente: ((ev: { data: unknown }) => void) | null = null;
  postMessage(): void {}
  addEventListener(_t: 'message', cb: (ev: { data: unknown }) => void): void {
    this.oyente = cb;
  }
  close(): void {}
}

const urlDe = (entrada: Parameters<typeof fetch>[0]): string =>
  typeof entrada === 'string' ? entrada : entrada instanceof URL ? entrada.href : entrada.url;

function montar(fetchFn: typeof fetch, canal: Canal | null = null) {
  const sesion = new Sesion({ fetchFn, candados: null, canal });
  const api = crearApi(sesion, fetchFn);
  render(<App sesion={sesion} api={api} hoy={() => '2031-11-18'} />);
  return sesion;
}

/** Monta la app y deja correr las promesas de arranque (restauración de la sesión). */
const abrir = (fetchFn: typeof fetch, canal: Canal | null = null) =>
  act(() => {
    montar(fetchFn, canal);
    return Promise.resolve();
  });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('App: restauración de la sesión', () => {
  it('con una cookie vigente restaura la sesión sin pedir ingreso: refresh, me y después agenda y opciones', async () => {
    const fetchFn = servidor(ruta('POST /api/auth/refresh', { access_token: 'ACCESS-1', token_type: 'bearer' }), ...panel);
    await abrir(fetchFn);
    expect(await screen.findByRole('heading', { name: 'Agenda' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Contraseña')).toBeNull();
    const llamadas = fetchFn.mock.calls.map((c) => urlDe(c[0]).split('?')[0]);
    expect(llamadas.slice(0, 2)).toEqual(['/api/auth/refresh', '/api/auth/me']);
    expect(new Set(llamadas.slice(2))).toEqual(new Set(['/api/panel/agenda', '/api/panel/agenda/opciones']));
  });

  it('mientras restaura, no muestra el formulario de ingreso ni la agenda', async () => {
    const fetchFn = vi.fn<typeof fetch>(() => new Promise<Response>(() => undefined));
    await abrir(fetchFn);
    expect(screen.getByRole('status')).toHaveTextContent('Abriendo el panel…');
    expect(screen.queryByLabelText('Contraseña')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
  });

  it('sin sesión (401) muestra el ingreso, sin error visible ni nada de la agenda', async () => {
    const fetchFn = servidor(ruta('POST /api/auth/refresh', { detail: 'x' }, 401), ...panel);
    await abrir(fetchFn);
    expect(await screen.findByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
    expect(fetchFn.mock.calls.some((c) => urlDe(c[0]).startsWith('/api/panel'))).toBe(false);
  });

  it('si el servidor no responde al restaurar NO pide ingreso: ofrece reintentar', async () => {
    let falla = true;
    const fetchFn = servidor(
      (url) => (url === '/api/auth/refresh' && falla ? json({ detail: 'x' }, 503) : undefined),
      ruta('POST /api/auth/refresh', { access_token: 'ACCESS-1', token_type: 'bearer' }),
      ...panel,
    );
    await abrir(fetchFn);
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('No pudimos abrir el panel');
    expect(screen.queryByLabelText('Contraseña')).toBeNull();
    falla = false;
    await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByRole('heading', { name: 'Agenda' })).toBeInTheDocument();
  });

  it('al volver desde el historial (bfcache) vuelve a comprobar la sesión', async () => {
    let vigente = true;
    const fetchFn = servidor(
      (url) => (url === '/api/auth/refresh' ? (vigente ? json({ access_token: 'A', token_type: 'bearer' }) : json({ detail: 'x' }, 401)) : undefined),
      ...panel,
    );
    await abrir(fetchFn);
    await screen.findByRole('heading', { name: 'Agenda' });
    vigente = false;
    await act(() => {
      window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
      return Promise.resolve();
    });
    expect(await screen.findByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
  });
});

describe('App: ingreso y salida', () => {
  const sinSesion = ruta('POST /api/auth/refresh', { detail: 'x' }, 401);

  it('ingresa con credenciales correctas y muestra la agenda', async () => {
    const fetchFn = servidor(sinSesion, ruta('POST /api/auth/login', { access_token: 'ACCESS-2', token_type: 'bearer' }), ...panel);
    await abrir(fetchFn);
    await usuario.type(await screen.findByLabelText('Correo electrónico'), 'recepcion@turnos.test');
    await usuario.type(screen.getByLabelText('Contraseña'), 'clave-sintetica-123');
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(await screen.findByRole('heading', { name: 'Agenda' })).toBeInTheDocument();
    expect(screen.getByText('Rita Recepción')).toBeInTheDocument();
  });

  it('credenciales inválidas: mismo mensaje y sigue en el ingreso', async () => {
    const fetchFn = servidor(sinSesion, ruta('POST /api/auth/login', { detail: 'Credenciales inválidas' }, 401), ...panel);
    await abrir(fetchFn);
    await usuario.type(await screen.findByLabelText('Correo electrónico'), 'nadie@turnos.test');
    await usuario.type(screen.getByLabelText('Contraseña'), 'clave-sintetica-123');
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('El correo o la contraseña no son correctos.');
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
  });

  it('un usuario sin ningún rol del panel no ve la agenda y puede salir', async () => {
    const fetchFn = servidor(
      sinSesion,
      ruta('POST /api/auth/login', { access_token: 'ACCESS-3', token_type: 'bearer' }),
      ruta('GET /api/auth/me', { ...ME, roles: [] }),
      ruta('POST /api/auth/logout', { detalle: 'ok' }),
      ...panel,
    );
    await abrir(fetchFn);
    await usuario.type(await screen.findByLabelText('Correo electrónico'), 'sinrol@turnos.test');
    await usuario.type(screen.getByLabelText('Contraseña'), 'clave-sintetica-123');
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(await screen.findByRole('heading', { name: 'Tu usuario no tiene acceso al panel' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
    expect(fetchFn.mock.calls.some((c) => urlDe(c[0]).startsWith('/api/panel'))).toBe(false);
    await usuario.click(screen.getByRole('button', { name: 'Salir' }));
    expect(await screen.findByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
  });

  it('salir revoca la sesión y vuelve al ingreso con el aviso', async () => {
    const fetchFn = servidor(
      ruta('POST /api/auth/refresh', { access_token: 'A', token_type: 'bearer' }),
      ruta('POST /api/auth/logout', { detalle: 'ok' }),
      ...panel,
    );
    await abrir(fetchFn);
    await usuario.click(await screen.findByRole('button', { name: 'Salir' }));
    expect(await screen.findByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Saliste del panel.');
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
  });

  it('si falla la red al salir avisa que la sesión sigue abierta y permite reintentar', async () => {
    let cae = true;
    const fetchFn = vi.fn<typeof fetch>((entrada) => {
      const url = urlDe(entrada);
      if (url === '/api/auth/logout') return cae ? Promise.reject(new TypeError('Failed to fetch')) : Promise.resolve(json({ detalle: 'ok' }));
      if (url === '/api/auth/refresh') return Promise.resolve(json({ access_token: 'A', token_type: 'bearer' }));
      if (url === '/api/auth/me') return Promise.resolve(json(ME));
      if (url.startsWith('/api/panel/agenda/opciones')) return Promise.resolve(json(OPCIONES));
      return Promise.resolve(json(AGENDA));
    });
    await abrir(fetchFn);
    await usuario.click(await screen.findByRole('button', { name: 'Salir' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cerrar tu sesión');
    expect(screen.getByRole('heading', { name: 'Agenda' })).toBeInTheDocument();
    cae = false;
    await usuario.click(screen.getByRole('button', { name: 'Salir' }));
    expect(await screen.findByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
  });

  it('cuando la sesión vence y no se puede renovar vuelve al ingreso con el aviso', async () => {
    let vencida = false;
    const fetchFn = vi.fn<typeof fetch>((entrada, init) => {
      const url = urlDe(entrada);
      if (url === '/api/auth/refresh') return Promise.resolve(vencida ? json({ detail: 'x' }, 401) : json({ access_token: 'A', token_type: 'bearer' }));
      if (url === '/api/auth/me') return Promise.resolve(json(ME));
      if (url.startsWith('/api/panel/agenda/opciones')) return Promise.resolve(json(OPCIONES));
      if (url.startsWith('/api/panel/agenda')) {
        void init;
        return Promise.resolve(vencida ? json({ detail: 'x' }, 401) : json(AGENDA));
      }
      return Promise.resolve(json({}, 500));
    });
    await abrir(fetchFn);
    await screen.findByRole('heading', { name: 'Agenda' });
    vencida = true;
    await usuario.click(screen.getByRole('button', { name: 'Hoy' }));
    expect(await screen.findByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Tu sesión venció.');
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
  });

  it('un cierre de sesión desde otra pestaña saca a esta del panel', async () => {
    const canal = new CanalFalso();
    const fetchFn = servidor(ruta('POST /api/auth/refresh', { access_token: 'A', token_type: 'bearer' }), ...panel);
    await abrir(fetchFn, canal);
    await screen.findByRole('heading', { name: 'Agenda' });
    await act(() => {
      canal.oyente?.({ data: 'salio' });
      return Promise.resolve();
    });
    expect(await screen.findByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Cerraste la sesión en otra pestaña.');
    expect(screen.queryByRole('heading', { name: 'Agenda' })).toBeNull();
  });
});
