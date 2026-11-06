import { interpretarRespuestaError, type ErrorApi } from './errores';
import { esNumero, esRegistro, esTexto, type Registro } from './guardas';
import type {
  Alternativa,
  ErrorGestion,
  GestionTurno,
  MotivoNoModificable,
  TurnoCancelado,
  TurnoReprogramado,
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

// --- Gestión del turno (C-07) ------------------------------------------------------------------

const ERROR_GESTION_DESCONOCIDO: ErrorGestion = {
  tipo: 'desconocido',
  mensaje: 'No pudimos conectar con la clínica. Revisá tu conexión e intentá de nuevo.',
};

const MOTIVOS: readonly string[] = ['fuera_de_plazo', 'turno_no_modificable', 'sena_pendiente'];

function esMotivoONulo(v: unknown): v is MotivoNoModificable | null {
  return v === null || (esTexto(v) && MOTIVOS.includes(v));
}

function esAlternativa(v: unknown): v is Alternativa {
  return esRegistro(v) && esTexto(v['inicio']) && esTexto(v['fin']) && esNumero(v['sillon_id']);
}

function esGestionTurno(v: unknown): v is GestionTurno {
  if (!esRegistro(v)) return false;
  const t = v['tratamiento'];
  const p = v['profesional'];
  const s = v['sena'];
  return (
    esEstadoTurno(v['estado']) &&
    esTexto(v['inicio']) &&
    esTexto(v['fin']) &&
    esRegistro(t) &&
    esNumero(t['id']) &&
    esTexto(t['nombre']) &&
    esNumero(t['duracion_minutos']) &&
    esRegistro(p) &&
    esNumero(p['id']) &&
    esTexto(p['nombre']) &&
    (s === null || (esRegistro(s) && esTexto(s['monto']) && esEstadoPago(s['estado']))) &&
    esTexto(v['limite_cambios']) &&
    typeof v['puede_cancelar'] === 'boolean' &&
    typeof v['puede_reprogramar'] === 'boolean' &&
    esMotivoONulo(v['motivo_no_cancelable']) &&
    esMotivoONulo(v['motivo_no_reprogramable']) &&
    esTexto(v['texto_politica_reembolso'])
  );
}

function estadoSenaONulo(v: unknown): boolean {
  return v === null || v === undefined || esEstadoPago(v);
}

function esTurnoCancelado(v: unknown): v is TurnoCancelado {
  return esRegistro(v) && v['estado'] === 'cancelado' && estadoSenaONulo(v['estado_sena']);
}

function esTurnoReprogramado(v: unknown): v is TurnoReprogramado {
  return (
    esRegistro(v) && esEstadoTurno(v['estado']) && esTexto(v['inicio']) && esTexto(v['fin']) && estadoSenaONulo(v['estado_sena'])
  );
}

function interpretarErrorGestion(status: number, cuerpo: unknown): ErrorGestion {
  if (status === 404) return { tipo: 'no_encontrado' };
  if (status === 409 && esRegistro(cuerpo)) {
    const motivo = cuerpo['motivo'];
    if (motivo === 'fuera_de_plazo') {
      return { tipo: 'fuera_de_plazo', limite_cambios: esTexto(cuerpo['limite_cambios']) ? cuerpo['limite_cambios'] : null };
    }
    if (motivo === 'turno_no_modificable') return { tipo: 'turno_no_modificable' };
    if (motivo === 'sena_pendiente') return { tipo: 'sena_pendiente' };
    if (motivo === 'profesional' || motivo === 'sillon') {
      const lista = Array.isArray(cuerpo['alternativas']) ? (cuerpo['alternativas'] as unknown[]).filter(esAlternativa) : [];
      return { tipo: 'conflicto', motivo, alternativas: lista };
    }
  }
  if (status === 422) {
    return { tipo: 'horario_invalido', mensaje: 'Ese horario no está disponible. Elegí otro horario.' };
  }
  return { tipo: 'desconocido', mensaje: 'No pudimos completar la operación. Intentá de nuevo en unos minutos.' };
}

interface RespuestaCruda {
  readonly status: number;
  readonly json: unknown;
}

async function pedirGestion(
  metodo: 'GET' | 'POST',
  ruta: string,
  codigoGestion: string,
  cuerpo?: unknown,
): Promise<RespuestaCruda | null> {
  const headers: Record<string, string> = { 'X-Codigo-Gestion': codigoGestion };
  if (cuerpo !== undefined) headers['Content-Type'] = 'application/json';
  try {
    const respuesta = await fetch(`${BASE}/gestion${ruta}`, {
      method: metodo,
      headers,
      ...(cuerpo !== undefined ? { body: JSON.stringify(cuerpo) } : {}),
    });
    return { status: respuesta.status, json: await leerJson(respuesta) };
  } catch {
    return null;
  }
}

export type ResultadoGestion =
  | { readonly ok: true; readonly gestion: GestionTurno }
  | { readonly ok: false; readonly error: ErrorGestion };

/** Datos del turno para gestionarlo. El código viaja en una cabecera, nunca en la URL (no queda en logs). */
export async function consultarGestion(codigoGestion: string): Promise<ResultadoGestion> {
  const r = await pedirGestion('GET', '', codigoGestion);
  if (r === null) return { ok: false, error: ERROR_GESTION_DESCONOCIDO };
  if (r.status === 200 && esGestionTurno(r.json)) return { ok: true, gestion: r.json };
  return { ok: false, error: interpretarErrorGestion(r.status, r.json) };
}

export type ResultadoCancelacion =
  | { readonly ok: true; readonly cancelacion: TurnoCancelado }
  | { readonly ok: false; readonly error: ErrorGestion };

export async function cancelarTurno(codigoGestion: string): Promise<ResultadoCancelacion> {
  const r = await pedirGestion('POST', '/cancelar', codigoGestion);
  if (r === null) return { ok: false, error: ERROR_GESTION_DESCONOCIDO };
  if (r.status === 200 && esTurnoCancelado(r.json)) return { ok: true, cancelacion: r.json };
  return { ok: false, error: interpretarErrorGestion(r.status, r.json) };
}

export type ResultadoReprogramacion =
  | { readonly ok: true; readonly reprogramacion: TurnoReprogramado }
  | { readonly ok: false; readonly error: ErrorGestion };

export async function reprogramarTurno(codigoGestion: string, inicio: string): Promise<ResultadoReprogramacion> {
  const r = await pedirGestion('POST', '/reprogramar', codigoGestion, { inicio });
  if (r === null) return { ok: false, error: ERROR_GESTION_DESCONOCIDO };
  if (r.status === 200 && esTurnoReprogramado(r.json)) return { ok: true, reprogramacion: r.json };
  return { ok: false, error: interpretarErrorGestion(r.status, r.json) };
}
