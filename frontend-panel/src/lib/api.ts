import { esNumero, esRegistro, esTexto, type Registro } from './guardas';
import { ErrorSesion, type Sesion } from './sesion';
import type {
  Accion,
  Agenda,
  Alternativa,
  CambioEstado,
  Consulta,
  DatosAlta,
  ErrorAlta,
  ErrorEstado,
  Opciones,
  Ref,
  Resultado,
  Rol,
  SenaAgenda,
  Slot,
  TratamientoRef,
  TurnoAgenda,
  TurnoCreado,
  Usuario,
} from './tipos';

/** El servidor respondió algo que no cumple el contrato: se descarta en vez de dibujar datos inventados. */
export class ErrorDeRespuesta extends Error {
  constructor(mensaje = 'La respuesta del servidor no tiene el formato esperado') {
    super(mensaje);
    this.name = 'ErrorDeRespuesta';
  }
}

/** Una lectura terminó con un estado HTTP de error; conserva el motivo y el mensaje del servidor. */
export class ErrorApiPanel extends Error {
  constructor(
    readonly status: number,
    mensaje: string,
    readonly motivo: string | null,
  ) {
    super(mensaje);
    this.name = 'ErrorApiPanel';
  }
}

// --- guardas -------------------------------------------------------------------------------------------------

const ESTADOS: readonly string[] = ['en_espera', 'reservado', 'confirmado', 'cancelado', 'ausente', 'atendido'];
const ACCIONES: readonly string[] = ['atendido', 'ausente', 'cancelar'];
const ROLES: readonly string[] = ['admin', 'odontologo', 'recepcion'];

function textoONulo(v: unknown): v is string | null {
  return v === null || esTexto(v);
}

function esRef(v: unknown): v is Ref {
  return esRegistro(v) && esNumero(v['id']) && esTexto(v['nombre']);
}

function esTratamientoRef(v: unknown): v is TratamientoRef {
  return esRef(v) && esNumero((v as unknown as Registro)['duracion_minutos']);
}

function esSena(v: unknown): v is SenaAgenda {
  return esRegistro(v) && esTexto(v['estado']) && esTexto(v['monto']);
}

function esAccion(v: unknown): v is Accion {
  return esTexto(v) && ACCIONES.includes(v);
}

function esTurno(v: unknown): v is TurnoAgenda {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esTexto(v['inicio']) &&
    esTexto(v['fin']) &&
    esTexto(v['estado']) &&
    ESTADOS.includes(v['estado']) &&
    typeof v['bloquea_agenda'] === 'boolean' &&
    esTexto(v['origen']) &&
    esRef(v['profesional']) &&
    esRef(v['sillon']) &&
    esTratamientoRef(v['tratamiento']) &&
    textoONulo(v['paciente_nombre']) &&
    textoONulo(v['paciente_telefono']) &&
    (v['sena'] === null || esSena(v['sena'])) &&
    textoONulo(v['vence_en']) &&
    Array.isArray(v['acciones']) &&
    (v['acciones'] as unknown[]).every(esAccion)
  );
}

function aAgenda(v: unknown): Agenda {
  if (
    !esRegistro(v) ||
    (v['vista'] !== 'dia' && v['vista'] !== 'semana') ||
    !esTexto(v['desde']) ||
    !esTexto(v['hasta']) ||
    !Array.isArray(v['turnos']) ||
    !(v['turnos'] as unknown[]).every(esTurno)
  ) {
    throw new ErrorDeRespuesta();
  }
  return { vista: v['vista'], desde: v['desde'], hasta: v['hasta'], turnos: v['turnos'] as TurnoAgenda[] };
}

function lista<T>(v: unknown, guarda: (x: unknown) => x is T): readonly T[] {
  if (!Array.isArray(v) || !(v as unknown[]).every(guarda)) throw new ErrorDeRespuesta();
  return v as T[];
}

function aOpciones(v: unknown): Opciones {
  if (!esRegistro(v) || typeof v['puede_escribir'] !== 'boolean') throw new ErrorDeRespuesta();
  return {
    profesionales: lista(v['profesionales'], esRef),
    sillones: lista(v['sillones'], esRef),
    tratamientos: lista(v['tratamientos'], esTratamientoRef),
    puede_escribir: v['puede_escribir'],
  };
}

function esRol(v: unknown): v is Rol {
  return esTexto(v) && ROLES.includes(v);
}

function aUsuario(v: unknown): Usuario {
  if (!esRegistro(v) || !esNumero(v['id']) || !esTexto(v['email']) || !esTexto(v['nombre_completo'])) {
    throw new ErrorDeRespuesta();
  }
  return { id: v['id'], email: v['email'], nombre_completo: v['nombre_completo'], roles: lista(v['roles'], esRol) };
}

function esSlot(v: unknown): v is Slot {
  return (
    esRegistro(v) && esTexto(v['inicio']) && esTexto(v['fin']) && esNumero(v['profesional_id']) && esNumero(v['sillon_id'])
  );
}

function esAlternativa(v: unknown): v is Alternativa {
  return esRegistro(v) && esTexto(v['inicio']) && esTexto(v['fin']) && esNumero(v['sillon_id']);
}

function esTurnoCreado(v: unknown): v is TurnoCreado {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esTexto(v['inicio']) &&
    esTexto(v['fin']) &&
    v['estado'] === 'reservado' &&
    v['origen'] === 'manual' &&
    esNumero(v['profesional_id']) &&
    esNumero(v['sillon_id']) &&
    esNumero(v['tratamiento_id']) &&
    esTexto(v['codigo_gestion'])
  );
}

function esCambio(v: unknown): v is CambioEstado {
  return esRegistro(v) && esNumero(v['turno_id']) && esTexto(v['estado']) && textoONulo(v['estado_sena']);
}

async function cuerpoDe(r: Response): Promise<Registro> {
  try {
    const v: unknown = await r.json();
    return esRegistro(v) ? v : {};
  } catch {
    return {};
  }
}

function limpiar(msg: string): string {
  return msg.replace(/^Value error,\s*/i, '');
}

function mensajeDeValidacion(detail: unknown): string {
  if (Array.isArray(detail)) {
    for (const item of detail as unknown[]) {
      if (esRegistro(item) && esTexto(item['msg'])) return limpiar(item['msg']);
    }
  }
  return 'Revisá los datos del turno.';
}

function errorAlta(status: number, cuerpo: Registro): ErrorAlta {
  const motivo = cuerpo['motivo'];
  if (status === 403) return { tipo: 'sin_permiso' };
  if (status === 409 && (motivo === 'profesional' || motivo === 'sillon')) {
    const alternativas = Array.isArray(cuerpo['alternativas']) ? (cuerpo['alternativas'] as unknown[]).filter(esAlternativa) : [];
    return { tipo: 'conflicto', motivo, alternativas };
  }
  if (status === 422) {
    if (motivo === 'fuera_de_disponibilidad') return { tipo: 'fuera_de_disponibilidad' };
    if (motivo === 'inicio_pasado') return { tipo: 'inicio_pasado' };
    return { tipo: 'validacion', mensaje: mensajeDeValidacion(cuerpo['detail']) };
  }
  return { tipo: 'desconocido' };
}

function errorEstado(status: number, cuerpo: Registro): ErrorEstado {
  const motivo = cuerpo['motivo'];
  if (status === 403) return { tipo: 'sin_permiso' };
  if (status === 404) return { tipo: 'no_encontrado' };
  if (status === 503) return { tipo: 'reintentar' };
  if (status === 409 && motivo === 'marcado_no_habilitado') {
    return { tipo: 'marcado_no_habilitado', habilitadoDesde: esTexto(cuerpo['habilitado_desde']) ? cuerpo['habilitado_desde'] : null };
  }
  if (status === 409 && motivo === 'fuera_de_plazo') {
    return { tipo: 'fuera_de_plazo', limiteCambios: esTexto(cuerpo['limite_cambios']) ? cuerpo['limite_cambios'] : null };
  }
  if (status === 409 && motivo === 'transicion_invalida') return { tipo: 'transicion_invalida' };
  return { tipo: 'desconocido' };
}

// --- API -----------------------------------------------------------------------------------------------------

export interface Api {
  me(): Promise<Usuario>;
  agenda(consulta: Consulta): Promise<Agenda>;
  opciones(): Promise<Opciones>;
  disponibilidad(profesionalId: number, tratamientoId: number, dia: string): Promise<readonly Slot[]>;
  crearTurno(datos: DatosAlta): Promise<Resultado<TurnoCreado, ErrorAlta>>;
  marcar(turnoId: number, accion: Accion): Promise<Resultado<CambioEstado, ErrorEstado>>;
}

export function crearApi(sesion: Sesion, fetchFn: typeof fetch = (...args) => fetch(...args)): Api {
  /** Pedido autenticado: si el access venció renueva UNA vez (compartida) y reintenta UNA vez; nunca hace bucle. */
  async function pedir(ruta: string, init: RequestInit = {}): Promise<Response> {
    const enviar = (token: string): Promise<Response> =>
      fetchFn(ruta, { ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` } });

    const usado = sesion.token() ?? (await sesion.renovar());
    if (usado === null) throw new ErrorSesion();
    let respuesta = await enviar(usado);
    if (respuesta.status !== 401) return respuesta;

    // Si otro pedido ya renovó mientras éste volaba, el token actual es nuevo: no se renueva de nuevo.
    const actual = sesion.token();
    const nuevo = actual !== null && actual !== usado ? actual : await sesion.renovar();
    if (nuevo === null) throw new ErrorSesion();
    respuesta = await enviar(nuevo);
    if (respuesta.status === 401) {
      sesion.cerrarLocal();
      throw new ErrorSesion();
    }
    return respuesta;
  }

  async function leer(ruta: string): Promise<unknown> {
    const r = await pedir(ruta);
    if (!r.ok) {
      const c = await cuerpoDe(r);
      const mensaje = esTexto(c['detail']) ? c['detail'] : `Error ${String(r.status)}`;
      throw new ErrorApiPanel(r.status, mensaje, esTexto(c['motivo']) ? c['motivo'] : null);
    }
    return (await r.json()) as unknown;
  }

  async function escribir<T, E>(
    ruta: string,
    cuerpo: unknown,
    esValido: (v: unknown) => v is T,
    interpretar: (status: number, c: Registro) => E,
    desconocido: E,
  ): Promise<Resultado<T, E>> {
    let r: Response;
    try {
      r = await pedir(ruta, {
        method: 'POST',
        ...(cuerpo === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) }),
      });
    } catch (e) {
      if (e instanceof ErrorSesion) throw e;
      return { ok: false, error: desconocido };
    }
    if (r.ok) {
      const valor: unknown = await r.json().catch(() => null);
      return esValido(valor) ? { ok: true, valor } : { ok: false, error: desconocido };
    }
    return { ok: false, error: interpretar(r.status, await cuerpoDe(r)) };
  }

  return {
    async me() {
      return aUsuario(await leer('/api/auth/me'));
    },
    async agenda(c) {
      const q = new URLSearchParams({ vista: c.vista, fecha: c.fecha });
      if (c.profesionalId !== null) q.set('profesional_id', String(c.profesionalId));
      if (c.sillonId !== null) q.set('sillon_id', String(c.sillonId));
      return aAgenda(await leer(`/api/panel/agenda?${q.toString()}`));
    },
    async opciones() {
      return aOpciones(await leer('/api/panel/agenda/opciones'));
    },
    async disponibilidad(profesionalId, tratamientoId, dia) {
      const q = new URLSearchParams({
        profesional_id: String(profesionalId),
        tratamiento_id: String(tratamientoId),
        desde: dia,
        hasta: dia,
      });
      const r = await fetchFn(`/api/public/disponibilidad?${q.toString()}`);
      if (!r.ok) throw new ErrorApiPanel(r.status, 'No pudimos consultar los horarios', null);
      const cuerpo = await cuerpoDe(r);
      return lista(cuerpo['slots'], esSlot);
    },
    crearTurno(d) {
      return escribir(
        '/api/panel/turnos',
        {
          profesional_id: d.profesionalId,
          tratamiento_id: d.tratamientoId,
          inicio: d.inicio,
          nombre: d.nombre,
          telefono: d.telefono,
        },
        esTurnoCreado,
        errorAlta,
        { tipo: 'desconocido' },
      );
    },
    marcar(turnoId, accion) {
      return escribir(`/api/panel/turnos/${String(turnoId)}/${accion}`, undefined, esCambio, errorEstado, {
        tipo: 'desconocido',
      });
    },
  };
}

