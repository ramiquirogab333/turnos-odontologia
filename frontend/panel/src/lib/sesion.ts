import { esRegistro, esTexto } from './guardas';
import { minutosDesdeRetryAfter } from './limite';

/**
 * Sesión del panel (C-08, D10).
 *
 * - El access token vive SOLO en memoria: nada en localStorage, sessionStorage ni cookies legibles.
 * - El refresh viaja en una cookie HttpOnly que JavaScript no puede leer; acá solo se pide la renovación
 *   (`POST /api/auth/refresh` con la cabecera `X-Panel-Csrf`, mismo origen gracias al proxy: sin CORS).
 * - Como el refresh se ROTA en cada uso, dos renovaciones simultáneas harían perder a una y cerrar la sesión: en cada
 *   pestaña hay una sola renovación compartida y entre pestañas se coordina con `navigator.locks`.
 * - `BroadcastChannel('panel-sesion')` avisa el cierre de sesión a las demás pestañas.
 */

export const CABECERA_CSRF = 'X-Panel-Csrf';
const CANDADO = 'panel-refresh';
const CANAL = 'panel-sesion';
const AVISO_SALIDA = 'salio';

/** Falla de red o del servidor al renovar: NO significa "sin sesión". */
export class ErrorDeRed extends Error {
  constructor(mensaje = 'No hay conexión con el servidor') {
    super(mensaje);
    this.name = 'ErrorDeRed';
  }
}

/** No hay sesión, o venció y no se pudo renovar. */
export class ErrorSesion extends Error {
  constructor() {
    super('Sesión vencida');
    this.name = 'ErrorSesion';
  }
}

export interface Candados {
  request<T>(nombre: string, callback: () => Promise<T>): Promise<T>;
}

export interface Canal {
  postMessage(mensaje: unknown): void;
  addEventListener(tipo: 'message', oyente: (evento: { readonly data: unknown }) => void): void;
  close(): void;
}

export interface OpcionesSesion {
  /** `undefined`: el `fetch` global. */
  readonly fetchFn?: typeof fetch;
  /** `undefined`: `navigator.locks` si existe. `null`: sin coordinación entre pestañas. */
  readonly candados?: Candados | null;
  /** `undefined`: un `BroadcastChannel` si existe. `null`: sin aviso entre pestañas. */
  readonly canal?: Canal | null;
}

export type ResultadoIngreso =
  | { readonly ok: true }
  | { readonly ok: false; readonly motivo: 'credenciales' | 'red' | 'servidor' }
  /** 429 (C-15): demasiados intentos; `minutos` sale de `Retry-After`. */
  | { readonly ok: false; readonly motivo: 'limite'; readonly minutos: number };

/** Por qué terminó la sesión local: la pantalla de ingreso lo explica distinto en cada caso. */
export type MotivoCierre = 'vencida' | 'otra_pestana' | 'salida';

type Oyente = (token: string | null, motivo?: MotivoCierre) => void;

function candadosDelNavegador(): Candados | null {
  if (typeof navigator === 'undefined') return null;
  const locks: unknown = (navigator as { locks?: unknown }).locks;
  return esRegistro(locks) && typeof locks['request'] === 'function' ? (locks as unknown as Candados) : null;
}

function canalDelNavegador(): Canal | null {
  return typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(CANAL);
}

function tokenDe(cuerpo: unknown): string | null {
  return esRegistro(cuerpo) && esTexto(cuerpo['access_token']) && cuerpo['access_token'] !== '' ? cuerpo['access_token'] : null;
}

async function leerJson(r: Response): Promise<unknown> {
  try {
    return (await r.json()) as unknown;
  } catch {
    return null;
  }
}

export class Sesion {
  private acceso: string | null = null;
  private renovacion: Promise<string | null> | null = null;
  private readonly oyentes = new Set<Oyente>();
  private readonly fetchFn: typeof fetch;
  private readonly candados: Candados | null;
  private readonly canal: Canal | null;

  constructor(opciones: OpcionesSesion = {}) {
    this.fetchFn = opciones.fetchFn ?? ((...args) => fetch(...args));
    this.candados = opciones.candados === undefined ? candadosDelNavegador() : opciones.candados;
    this.canal = opciones.canal === undefined ? canalDelNavegador() : opciones.canal;
    this.canal?.addEventListener('message', (evento) => {
      if (evento.data === AVISO_SALIDA) this.cerrarLocal('otra_pestana');
    });
  }

  token(): string | null {
    return this.acceso;
  }

  /** Fija el access (lo usan el ingreso y las pruebas). */
  fijarToken(token: string | null, motivo?: MotivoCierre): void {
    this.acceso = token;
    for (const oyente of this.oyentes) oyente(token, motivo);
  }

  /** Cierra la sesión SOLO en esta pestaña (no revoca nada en el servidor). */
  cerrarLocal(motivo: MotivoCierre = 'vencida'): void {
    this.fijarToken(null, motivo);
  }

  alCambiar(oyente: Oyente): () => void {
    this.oyentes.add(oyente);
    return () => {
      this.oyentes.delete(oyente);
    };
  }

  async ingresar(email: string, password: string): Promise<ResultadoIngreso> {
    let respuesta: Response;
    try {
      respuesta = await this.fetchFn('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
    } catch {
      return { ok: false, motivo: 'red' };
    }
    if (respuesta.status === 401) return { ok: false, motivo: 'credenciales' };
    if (respuesta.status === 429) {
      return { ok: false, motivo: 'limite', minutos: minutosDesdeRetryAfter(respuesta.headers.get('Retry-After')) };
    }
    const token = respuesta.ok ? tokenDe(await leerJson(respuesta)) : null;
    if (token === null) return { ok: false, motivo: 'servidor' };
    this.fijarToken(token);
    return { ok: true };
  }

  /**
   * Renueva el access con la cookie de refresh. `null`: no hay sesión (401). Lanza `ErrorDeRed` si el servidor
   * no respondió bien: eso no cierra la sesión. Las llamadas simultáneas comparten un único pedido.
   */
  renovar(): Promise<string | null> {
    if (this.renovacion === null) {
      const ejecutar = (): Promise<string | null> => this.pedirRefresh();
      const compartida = this.candados ? this.candados.request(CANDADO, ejecutar) : ejecutar();
      this.renovacion = compartida.finally(() => {
        this.renovacion = null;
      });
    }
    return this.renovacion;
  }

  private async pedirRefresh(): Promise<string | null> {
    let respuesta: Response;
    try {
      respuesta = await this.fetchFn('/api/auth/refresh', { method: 'POST', headers: { [CABECERA_CSRF]: '1' } });
    } catch {
      throw new ErrorDeRed();
    }
    if (respuesta.status === 401) {
      this.fijarToken(null, 'vencida');
      return null;
    }
    const token = respuesta.ok ? tokenDe(await leerJson(respuesta)) : null;
    if (token === null) throw new ErrorDeRed('El servidor no pudo renovar la sesión');
    this.fijarToken(token);
    return token;
  }

  /**
   * Revoca la sesión en el servidor. `sin_red`: la cookie sigue viva, así que la sesión local se conserva para
   * poder reintentar (JavaScript no puede borrar una cookie HttpOnly).
   */
  async salir(): Promise<'ok' | 'sin_red'> {
    try {
      let respuesta = await this.cerrarEnServidor(this.acceso);
      if (respuesta.status === 401) {
        const nuevo = await this.renovar();
        if (nuevo !== null) respuesta = await this.cerrarEnServidor(nuevo);
      }
      if (respuesta.status >= 500) return 'sin_red';
    } catch {
      return 'sin_red';
    }
    this.fijarToken(null, 'salida');
    this.canal?.postMessage(AVISO_SALIDA);
    return 'ok';
  }

  private cerrarEnServidor(token: string | null): Promise<Response> {
    return this.fetchFn('/api/auth/logout', {
      method: 'POST',
      headers: token === null ? {} : { Authorization: `Bearer ${token}` },
    });
  }
}
