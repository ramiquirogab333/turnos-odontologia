import { interpretarRespuestaError, type ErrorApi } from './errores';
import { esNumero, esRegistro, esTexto } from './guardas';
import type { Catalogo, Profesional, ReservaCreada, ReservaRequest, Slot, Tratamiento } from './tipos';
import { normalizarTelefono } from './validacion';

const BASE = '/api/public';

export class ErrorDeCarga extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = 'ErrorDeCarga';
  }
}

function esTratamiento(v: unknown): v is Tratamiento {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esTexto(v['nombre']) &&
    esNumero(v['duracion_minutos']) &&
    esTexto(v['precio_base'])
  );
}

function esProfesional(v: unknown): v is Profesional {
  return esRegistro(v) && esNumero(v['id']) && esTexto(v['nombre']) && esTexto(v['especialidad']);
}

function esSlot(v: unknown): v is Slot {
  return (
    esRegistro(v) &&
    esTexto(v['inicio']) &&
    esTexto(v['fin']) &&
    esNumero(v['profesional_id']) &&
    esNumero(v['sillon_id'])
  );
}

function esReserva(v: unknown): v is ReservaCreada {
  return (
    esRegistro(v) &&
    esNumero(v['turno_id']) &&
    esTexto(v['codigo_gestion']) &&
    esTexto(v['estado']) &&
    esTexto(v['inicio']) &&
    esTexto(v['fin'])
  );
}

function listaDe<T>(valor: unknown, guarda: (v: unknown) => v is T): T[] | null {
  if (!Array.isArray(valor)) return null;
  const items = valor as unknown[];
  return items.every(guarda) ? items : null;
}

async function leerJson(respuesta: Response): Promise<unknown> {
  try {
    return (await respuesta.json()) as unknown;
  } catch {
    return null;
  }
}

/**
 * Carga inicial del flujo (R2): ambas peticiones salen juntas con `Promise.all`;
 * ninguna espera a la otra.
 */
export async function cargarCatalogo(): Promise<Catalogo> {
  const falla = new ErrorDeCarga('No pudimos cargar los tratamientos. Revisá tu conexión e intentá de nuevo.');
  const [rTratamientos, rProfesionales] = await Promise.all([
    fetch(`${BASE}/tratamientos`),
    fetch(`${BASE}/profesionales`),
  ]).catch(() => {
    throw falla;
  });
  if (!rTratamientos.ok || !rProfesionales.ok) throw falla;
  const [tratamientos, profesionales] = await Promise.all([leerJson(rTratamientos), leerJson(rProfesionales)]);
  const t = listaDe(tratamientos, esTratamiento);
  const p = listaDe(profesionales, esProfesional);
  if (t === null || p === null) throw falla;
  return { tratamientos: t, profesionales: p };
}

export interface ConsultaDisponibilidad {
  readonly profesionalId: number;
  readonly tratamientoId: number;
  /** Fechas locales de la clínica, "YYYY-MM-DD". */
  readonly desde: string;
  readonly hasta: string;
}

export async function obtenerDisponibilidad(consulta: ConsultaDisponibilidad): Promise<Slot[]> {
  const falla = new ErrorDeCarga('No pudimos cargar los horarios. Intentá de nuevo.');
  const params = new URLSearchParams({
    profesional_id: String(consulta.profesionalId),
    tratamiento_id: String(consulta.tratamientoId),
    desde: consulta.desde,
    hasta: consulta.hasta,
  });
  const respuesta = await fetch(`${BASE}/disponibilidad?${params.toString()}`).catch(() => {
    throw falla;
  });
  if (!respuesta.ok) throw falla;
  const cuerpo = await leerJson(respuesta);
  const slots = esRegistro(cuerpo) ? listaDe(cuerpo['slots'], esSlot) : null;
  if (slots === null) throw falla;
  return slots;
}

export type ResultadoReserva =
  | { readonly ok: true; readonly reserva: ReservaCreada }
  | { readonly ok: false; readonly error: ErrorApi };

const ERROR_RED: ErrorApi = {
  tipo: 'desconocido',
  mensaje: 'No pudimos conectar con la clínica. Revisá tu conexión e intentá de nuevo.',
};

export async function reservarTurno(datos: ReservaRequest): Promise<ResultadoReserva> {
  const cuerpo: ReservaRequest = {
    ...datos,
    nombre: datos.nombre.trim(),
    telefono: normalizarTelefono(datos.telefono),
  };
  let respuesta: Response;
  try {
    respuesta = await fetch(`${BASE}/turnos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cuerpo),
    });
  } catch {
    return { ok: false, error: ERROR_RED };
  }
  const json = await leerJson(respuesta);
  if (respuesta.status === 201 && esReserva(json)) return { ok: true, reserva: json };
  return { ok: false, error: interpretarRespuestaError(respuesta.status, json) };
}
