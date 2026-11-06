import { interpretarRespuestaError, type ErrorApi } from './errores';
import { esNumero, esRegistro, esTexto, type Registro } from './guardas';
import type {
  Catalogo,
  ErrorSena,
  EstadoPago,
  EstadoSena,
  EstadoTurno,
  InicioSena,
  MedioSena,
  Profesional,
  ReservaCreada,
  ReservaRequest,
  SenaInfo,
  Slot,
  Tratamiento,
} from './tipos';
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

function esMedio(v: unknown): v is MedioSena {
  return v === 'mercadopago' || v === 'transferencia';
}

function esSenaInfo(v: unknown): v is SenaInfo {
  return (
    esRegistro(v) &&
    esTexto(v['monto']) &&
    esTexto(v['vence_en']) &&
    esTexto(v['texto_politica_reembolso']) &&
    Array.isArray(v['medios_habilitados']) &&
    (v['medios_habilitados'] as unknown[]).every(esMedio)
  );
}

function esReserva(v: unknown): v is ReservaCreada {
  if (
    !esRegistro(v) ||
    !esNumero(v['turno_id']) ||
    !esTexto(v['codigo_gestion']) ||
    !esTexto(v['inicio']) ||
    !esTexto(v['fin'])
  ) {
    return false;
  }
  if (v['estado'] === 'en_espera') return esSenaInfo(v['sena']);
  return v['estado'] === 'reservado' && (v['sena'] === null || v['sena'] === undefined);
}

const ESTADOS_TURNO: readonly string[] = ['en_espera', 'reservado', 'confirmado', 'cancelado', 'ausente', 'atendido'];
const ESTADOS_PAGO: readonly string[] = ['pendiente', 'acreditado', 'vencido', 'no_reembolsado', 'a_reembolsar', 'en_revision'];

function esEstadoTurno(v: unknown): v is EstadoTurno {
  return esTexto(v) && ESTADOS_TURNO.includes(v);
}

function esEstadoPago(v: unknown): v is EstadoPago {
  return esTexto(v) && ESTADOS_PAGO.includes(v);
}

function textoONulo(v: unknown): boolean {
  return v === null || esTexto(v);
}

function esDatosPago(v: Registro): boolean {
  return (
    esNumero(v['turno_id']) &&
    (v['pago_id'] === null || esNumero(v['pago_id'])) &&
    (v['medio'] === null || esMedio(v['medio'])) &&
    esTexto(v['monto']) &&
    textoONulo(v['vence_en']) &&
    esTexto(v['texto_politica_reembolso']) &&
    ['referencia_externa', 'checkout_url', 'alias', 'cbu', 'titular', 'referencia_concepto'].every((k) =>
      textoONulo(v[k]),
    )
  );
}

function esInicioSena(v: unknown): v is InicioSena {
  return esRegistro(v) && esDatosPago(v) && esEstadoPago(v['estado']);
}

function esEstadoSena(v: unknown): v is EstadoSena {
  return (
    esRegistro(v) &&
    esDatosPago(v) &&
    esEstadoTurno(v['estado_turno']) &&
    (v['estado_pago'] === null || esEstadoPago(v['estado_pago'])) &&
    typeof v['vencida'] === 'boolean' &&
    Array.isArray(v['medios_habilitados']) &&
    (v['medios_habilitados'] as unknown[]).every(esMedio) &&
    esTexto(v['inicio']) &&
    esTexto(v['fin']) &&
    esTexto(v['tratamiento_nombre']) &&
    esTexto(v['profesional_nombre'])
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

// --- Seña (C-06) -------------------------------------------------------------------------------

const ERROR_SENA_DESCONOCIDO: ErrorSena = {
  tipo: 'desconocido',
  mensaje: 'No pudimos conectar con la clínica. Revisá tu conexión e intentá de nuevo.',
};

function mensajeDe(cuerpo: unknown, porDefecto: string): string {
  return esRegistro(cuerpo) && esTexto(cuerpo['detail']) ? cuerpo['detail'] : porDefecto;
}

function interpretarErrorSena(status: number, cuerpo: unknown): ErrorSena {
  if (status === 404) return { tipo: 'no_encontrada' };
  if (status === 409 && esRegistro(cuerpo)) {
    if (cuerpo['motivo'] === 'estado_invalido') return { tipo: 'vencida' };
    if (cuerpo['motivo'] === 'profesional' || cuerpo['motivo'] === 'sillon') return { tipo: 'horario_tomado' };
  }
  if (status === 422) return { tipo: 'medio', mensaje: mensajeDe(cuerpo, 'Ese medio de pago no está disponible.') };
  if (status === 502 || status === 503) {
    return { tipo: 'pasarela', mensaje: mensajeDe(cuerpo, 'No pudimos conectar con Mercado Pago. Probá de nuevo en unos minutos.') };
  }
  return { tipo: 'desconocido', mensaje: 'No pudimos completar la operación. Intentá de nuevo en unos minutos.' };
}

const rutaSena = (turnoId: number): string => `${BASE}/turnos/${String(turnoId)}/sena`;

export type ResultadoIniciarSena =
  | { readonly ok: true; readonly sena: InicioSena; /** false = reintento idempotente (200). */ readonly creada: boolean }
  | { readonly ok: false; readonly error: ErrorSena };

/** Inicia (o reanuda) la seña con el medio elegido. El código de gestión viaja en una cabecera, nunca en la URL. */
export async function iniciarSena(turnoId: number, codigoGestion: string, medio: MedioSena): Promise<ResultadoIniciarSena> {
  let respuesta: Response;
  try {
    respuesta = await fetch(rutaSena(turnoId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Codigo-Gestion': codigoGestion },
      body: JSON.stringify({ medio }),
    });
  } catch {
    return { ok: false, error: ERROR_SENA_DESCONOCIDO };
  }
  const json = await leerJson(respuesta);
  if ((respuesta.status === 201 || respuesta.status === 200) && esInicioSena(json)) {
    return { ok: true, sena: json, creada: respuesta.status === 201 };
  }
  return { ok: false, error: interpretarErrorSena(respuesta.status, json) };
}

export type ResultadoConsultaSena =
  | { readonly ok: true; readonly estado: EstadoSena }
  | { readonly ok: false; readonly error: ErrorSena };

/** Estado del turno y de su último pago (único recurso que se sondea: sin cascadas, R2). */
export async function consultarSena(turnoId: number, codigoGestion: string): Promise<ResultadoConsultaSena> {
  let respuesta: Response;
  try {
    respuesta = await fetch(rutaSena(turnoId), { headers: { 'X-Codigo-Gestion': codigoGestion } });
  } catch {
    return { ok: false, error: ERROR_SENA_DESCONOCIDO };
  }
  const json = await leerJson(respuesta);
  if (respuesta.status === 200 && esEstadoSena(json)) return { ok: true, estado: json };
  return { ok: false, error: interpretarErrorSena(respuesta.status, json) };
}
