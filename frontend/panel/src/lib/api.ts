import { consultaAuditoriaAQuery, nombreArchivo, parametrosExportacion } from './datos';
import { esNumero, esRegistro, esTexto, type Registro } from './guardas';
import { minutosDesdeRetryAfter } from './limite';
import { ErrorSesion, type Sesion } from './sesion';
import type {
  Accion,
  AccionMarcable,
  Acreditacion,
  Ausentismo,
  AusentismoProfesional,
  CajaDia,
  CierreCaja,
  CierreDetalle,
  AccionConflicto,
  CalendarioTurno,
  ConexionGoogle,
  ConflictoGoogle,
  ConsultaPacientes,
  ErrorGoogle,
  OcupadoGoogle,
  Devolucion,
  DiferenciaCierre,
  ErrorCaja,
  ErrorRecordatorio,
  MotivoFallo,
  Recordatorio,
  LineaCaja,
  ListadoPacientes,
  MotivoDeshacer,
  MovimientoCaja,
  Ocupacion,
  OcupacionDia,
  OcupacionSillon,
  PacienteListado,
  Pendiente,
  Rechazo,
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
  ArchivoExportado,
  ConsultaAuditoria,
  ErrorExportacion,
  PaginaAuditoria,
  ParametrosExportacion,
  RegistroAuditoria,
  UsuarioDirectorio,
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
const ACCIONES: readonly string[] = ['atendido', 'ausente', 'cancelar', 'deshacer_atendido'];
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
    (v['acciones'] as unknown[]).every(esAccion) &&
    esCalendario(v['calendario'])
  );
}

const ESTADOS_EVENTO: readonly string[] = ['sin_evento', 'pendiente', 'sincronizado', 'desvinculado'];

function esCalendario(v: unknown): v is CalendarioTurno {
  return (
    esRegistro(v) &&
    esTexto(v['estado']) &&
    ESTADOS_EVENTO.includes(v['estado']) &&
    typeof v['conflicto_abierto'] === 'boolean'
  );
}

function esOcupadoGoogle(v: unknown): v is OcupadoGoogle {
  return esRegistro(v) && esNumero(v['profesional_id']) && esTexto(v['inicio']) && esTexto(v['fin']);
}

function aAgenda(v: unknown): Agenda {
  if (
    !esRegistro(v) ||
    (v['vista'] !== 'dia' && v['vista'] !== 'semana') ||
    !esTexto(v['desde']) ||
    !esTexto(v['hasta']) ||
    !Array.isArray(v['turnos']) ||
    !(v['turnos'] as unknown[]).every(esTurno) ||
    !Array.isArray(v['ocupados_google']) ||
    !(v['ocupados_google'] as unknown[]).every(esOcupadoGoogle)
  ) {
    throw new ErrorDeRespuesta();
  }
  return {
    vista: v['vista'],
    desde: v['desde'],
    hasta: v['hasta'],
    turnos: v['turnos'] as TurnoAgenda[],
    ocupados_google: v['ocupados_google'] as OcupadoGoogle[],
  };
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
    esTexto(v['codigo_gestion']) &&
    typeof v['aviso_google_calendar'] === 'boolean'
  );
}

function esCambio(v: unknown): v is CambioEstado {
  return esRegistro(v) && esNumero(v['turno_id']) && esTexto(v['estado']) && textoONulo(v['estado_sena']);
}

// --- guardas de C-12 (caja, indicadores, pacientes) ------------------------------------------------------------

const CONCEPTOS: readonly string[] = ['sena', 'pago_presupuesto', 'devolucion_sena'];
const MEDIOS: readonly string[] = ['mercadopago', 'transferencia'];
const DECIMAL = /^-?\d+(\.\d+)?$/;

function esDinero(v: unknown): v is string {
  return esTexto(v) && DECIMAL.test(v);
}

function dineroONulo(v: unknown): v is string | null {
  return v === null || esDinero(v);
}

function esLinea(v: unknown): v is LineaCaja {
  return (
    esRegistro(v) &&
    esTexto(v['concepto']) &&
    CONCEPTOS.includes(v['concepto']) &&
    esTexto(v['medio']) &&
    MEDIOS.includes(v['medio']) &&
    esNumero(v['cantidad']) &&
    esDinero(v['total'])
  );
}

function esMovimiento(v: unknown): v is MovimientoCaja {
  return (
    esRegistro(v) &&
    esTexto(v['concepto']) &&
    CONCEPTOS.includes(v['concepto']) &&
    esTexto(v['medio']) &&
    MEDIOS.includes(v['medio']) &&
    esDinero(v['importe']) &&
    esTexto(v['hora']) &&
    textoONulo(v['referencia'])
  );
}

function aCaja(v: unknown): CajaDia {
  if (
    !esRegistro(v) ||
    !esTexto(v['dia']) ||
    (v['estado'] !== 'abierto' && v['estado'] !== 'cerrado') ||
    !(v['cierre_id'] === null || esNumero(v['cierre_id'])) ||
    !esDinero(v['total_ingresos']) ||
    !esDinero(v['total_egresos']) ||
    !esDinero(v['total_neto']) ||
    !esRegistro(v['senas_retenidas']) ||
    !esNumero(v['senas_retenidas']['cantidad']) ||
    !esDinero(v['senas_retenidas']['total'])
  ) {
    throw new ErrorDeRespuesta();
  }
  return {
    dia: v['dia'],
    estado: v['estado'],
    cierre_id: v['cierre_id'],
    lineas: lista(v['lineas'], esLinea),
    total_ingresos: v['total_ingresos'],
    total_egresos: v['total_egresos'],
    total_neto: v['total_neto'],
    senas_retenidas: { cantidad: v['senas_retenidas']['cantidad'], total: v['senas_retenidas']['total'] },
    movimientos: lista(v['movimientos'], esMovimiento),
  };
}

function esPendiente(v: unknown): v is Pendiente {
  return (
    esRegistro(v) &&
    (v['tipo'] === 'revision' || v['tipo'] === 'sena' || v['tipo'] === 'excedente_mp') &&
    esNumero(v['id']) &&
    esNumero(v['pago_id']) &&
    esNumero(v['turno_id']) &&
    esTexto(v['estado_turno']) &&
    esTexto(v['medio']) &&
    MEDIOS.includes(v['medio']) &&
    dineroONulo(v['importe']) &&
    typeof v['importe_a_verificar'] === 'boolean' &&
    textoONulo(v['mp_payment_id']) &&
    esTexto(v['pendiente_desde'])
  );
}

const ESTADOS_RECORDATORIO: readonly string[] = ['pendiente', 'enviado', 'confirmado', 'fallido'];

function esRecordatorio(v: unknown): v is Recordatorio {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esNumero(v['turno_id']) &&
    esTexto(v['estado']) &&
    ESTADOS_RECORDATORIO.includes(v['estado']) &&
    textoONulo(v['motivo']) &&
    esTexto(v['turno_inicio']) &&
    esTexto(v['profesional']) &&
    esTexto(v['tratamiento']) &&
    textoONulo(v['contacto_nombre']) &&
    textoONulo(v['enviado_en']) &&
    esNumero(v['intentos_fallidos']) &&
    (v['link'] === null || (esTexto(v['link']) && v['link'].startsWith('https://wa.me/')))
  );
}

function errorRecordatorio(status: number, cuerpo: Registro): ErrorRecordatorio {
  if (status === 403) return { tipo: 'sin_permiso' };
  if (status === 404) return { tipo: 'no_encontrado' };
  if (status === 409 && cuerpo['motivo'] === 'recordatorio_no_vigente') return { tipo: 'no_vigente' };
  return { tipo: 'desconocido' };
}

// --- guardas de C-10 (Google Calendar) ---------------------------------------------------------------------------

const ESTADOS_CONEXION: readonly string[] = ['sin_conectar', 'pendiente', 'activa', 'revocada', 'desconectada'];
const TIPOS_CONFLICTO: readonly string[] = ['movido_en_google', 'borrado_en_google', 'solapa_evento_externo'];
const ACCIONES_CONFLICTO: readonly string[] = ['restaurar_en_google', 'desvincular', 'revisado'];

function esConexionGoogle(v: unknown): v is ConexionGoogle {
  return (
    esRegistro(v) &&
    esNumero(v['profesional_id']) &&
    esTexto(v['profesional_nombre']) &&
    esTexto(v['estado']) &&
    ESTADOS_CONEXION.includes(v['estado']) &&
    textoONulo(v['cuenta_email']) &&
    textoONulo(v['ultima_sync_ok_en']) &&
    esNumero(v['conflictos_abiertos']) &&
    textoONulo(v['indicacion'])
  );
}

function esAccionConflicto(v: unknown): v is AccionConflicto {
  return esTexto(v) && ACCIONES_CONFLICTO.includes(v);
}

function esConflictoGoogle(v: unknown): v is ConflictoGoogle {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esTexto(v['tipo']) &&
    TIPOS_CONFLICTO.includes(v['tipo']) &&
    (v['estado'] === 'abierto' || v['estado'] === 'resuelto') &&
    esTexto(v['criterio']) &&
    esNumero(v['turno_id']) &&
    esNumero(v['profesional_id']) &&
    esTexto(v['profesional_nombre']) &&
    esTexto(v['tratamiento']) &&
    esTexto(v['sistema_inicio']) &&
    esTexto(v['sistema_fin']) &&
    textoONulo(v['google_inicio']) &&
    textoONulo(v['google_fin']) &&
    Array.isArray(v['acciones']) &&
    (v['acciones'] as unknown[]).every(esAccionConflicto) &&
    textoONulo(v['resolucion']) &&
    esTexto(v['detectado_en']) &&
    textoONulo(v['resuelto_en'])
  );
}

function esIniciar(v: unknown): v is { readonly url_autorizacion: string } {
  return esRegistro(v) && esTexto(v['url_autorizacion']) && v['url_autorizacion'].startsWith('http');
}

function errorGoogle(status: number, cuerpo: Registro): ErrorGoogle {
  const motivo = cuerpo['motivo'];
  if (status === 403) return { tipo: 'sin_permiso' };
  if (status === 404) return { tipo: 'no_encontrado' };
  if (status === 409 && motivo === 'conexion_activa') return { tipo: 'conexion_activa' };
  if (status === 409 && motivo === 'conflicto_cerrado') return { tipo: 'conflicto_cerrado' };
  if (status === 422 && motivo === 'accion_no_valida') return { tipo: 'accion_no_valida' };
  if (status === 503 && motivo === 'gcal_no_configurado') return { tipo: 'no_configurado' };
  return { tipo: 'desconocido' };
}

function esRechazo(v: unknown): v is Rechazo {
  return (
    esRegistro(v) &&
    esNumero(v['pago_id']) &&
    esNumero(v['turno_id']) &&
    esTexto(v['estado_pago']) &&
    esTexto(v['estado_turno']) &&
    esDinero(v['importe'])
  );
}

function esAcreditacion(v: unknown): v is Acreditacion {
  return (
    esRegistro(v) &&
    esNumero(v['pago_id']) &&
    esNumero(v['turno_id']) &&
    esTexto(v['efecto']) &&
    esTexto(v['estado_pago']) &&
    esTexto(v['estado_turno'])
  );
}

function esDevolucion(v: unknown): v is Devolucion {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    (v['tipo'] === 'sena' || v['tipo'] === 'excedente_mp') &&
    esNumero(v['pago_id']) &&
    esNumero(v['turno_id']) &&
    dineroONulo(v['importe']) &&
    esTexto(v['reembolsado_en']) &&
    esTexto(v['referencia'])
  );
}

function esCierre(v: unknown): v is CierreCaja {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esTexto(v['dia']) &&
    (v['estado'] === 'vigente' || v['estado'] === 'anulado') &&
    esDinero(v['total_ingresos']) &&
    esDinero(v['total_egresos']) &&
    esDinero(v['total_neto']) &&
    textoONulo(v['observaciones']) &&
    textoONulo(v['cerrado_por_nombre']) &&
    esTexto(v['cerrado_en']) &&
    textoONulo(v['anulado_en']) &&
    textoONulo(v['anulado_motivo']) &&
    Array.isArray(v['lineas']) &&
    (v['lineas'] as unknown[]).every(esLinea)
  );
}

function esDiferencia(v: unknown): v is DiferenciaCierre {
  return (
    esRegistro(v) &&
    esTexto(v['concepto']) &&
    CONCEPTOS.includes(v['concepto']) &&
    esTexto(v['medio']) &&
    MEDIOS.includes(v['medio']) &&
    esDinero(v['total_cierre']) &&
    esDinero(v['total_actual']) &&
    esNumero(v['cantidad_cierre']) &&
    esNumero(v['cantidad_actual'])
  );
}

function aCierreDetalle(v: unknown): CierreDetalle {
  if (!esCierre(v) || !esRegistro(v)) throw new ErrorDeRespuesta();
  const cuadra = v['cuadra'];
  if (!(cuadra === null || typeof cuadra === 'boolean')) throw new ErrorDeRespuesta();
  return { ...v, cuadra, diferencias: lista(v['diferencias'], esDiferencia) };
}

function esDiaOcupacion(v: unknown): v is OcupacionDia {
  return (
    esRegistro(v) &&
    esTexto(v['dia']) &&
    esNumero(v['minutos_ocupados']) &&
    esNumero(v['minutos_atencion']) &&
    dineroONulo(v['porcentaje']) &&
    esNumero(v['turnos']) &&
    esNumero(v['minutos_perdidos'])
  );
}

function esSillonOcupacion(v: unknown): v is OcupacionSillon {
  return (
    esRegistro(v) &&
    esNumero(v['sillon_id']) &&
    esTexto(v['nombre']) &&
    (v['estado'] === 'activo' || v['estado'] === 'inactivo' || v['estado'] === 'mantenimiento') &&
    Array.isArray(v['dias']) &&
    (v['dias'] as unknown[]).every(esDiaOcupacion)
  );
}

function aOcupacion(v: unknown): Ocupacion {
  if (!esRegistro(v) || !esTexto(v['desde']) || !esTexto(v['hasta'])) throw new ErrorDeRespuesta();
  return { desde: v['desde'], hasta: v['hasta'], sillones: lista(v['sillones'], esSillonOcupacion) };
}

function esAusentismoProfesional(v: unknown): v is AusentismoProfesional {
  return (
    esRegistro(v) &&
    esNumero(v['profesional_id']) &&
    esTexto(v['nombre']) &&
    esNumero(v['atendidos']) &&
    esNumero(v['ausentes']) &&
    dineroONulo(v['tasa']) &&
    esNumero(v['sin_marcar'])
  );
}

function aAusentismo(v: unknown): Ausentismo {
  if (
    !esRegistro(v) ||
    !esTexto(v['desde']) ||
    !esTexto(v['hasta']) ||
    !esNumero(v['atendidos']) ||
    !esNumero(v['ausentes']) ||
    !dineroONulo(v['tasa']) ||
    !esNumero(v['sin_marcar']) ||
    !esRegistro(v['recupero']) ||
    !esNumero(v['recupero']['senas_retenidas']) ||
    !esDinero(v['recupero']['importe_retenido']) ||
    !dineroONulo(v['recupero']['porcentaje'])
  ) {
    throw new ErrorDeRespuesta();
  }
  return {
    desde: v['desde'],
    hasta: v['hasta'],
    atendidos: v['atendidos'],
    ausentes: v['ausentes'],
    tasa: v['tasa'],
    sin_marcar: v['sin_marcar'],
    por_profesional: lista(v['por_profesional'], esAusentismoProfesional),
    recupero: {
      senas_retenidas: v['recupero']['senas_retenidas'],
      importe_retenido: v['recupero']['importe_retenido'],
      porcentaje: v['recupero']['porcentaje'],
    },
  };
}

function esPacienteListado(v: unknown): v is PacienteListado {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esTexto(v['nombre']) &&
    esTexto(v['apellido']) &&
    esTexto(v['dni']) &&
    esTexto(v['telefono']) &&
    (v['obra_social'] === null || esRef(v['obra_social'])) &&
    esNumero(v['atendidos']) &&
    esNumero(v['ausentes']) &&
    textoONulo(v['ultimo_turno'])
  );
}

function aListado(v: unknown): ListadoPacientes {
  if (!esRegistro(v) || !esNumero(v['total']) || !esNumero(v['pagina']) || !esNumero(v['por_pagina'])) {
    throw new ErrorDeRespuesta();
  }
  return { total: v['total'], pagina: v['pagina'], por_pagina: v['por_pagina'], pacientes: lista(v['pacientes'], esPacienteListado) };
}

function mensajeDeCaja(cuerpo: Registro): string {
  const detail = cuerpo['detail'];
  if (esTexto(detail)) return detail;
  if (Array.isArray(detail)) {
    for (const item of detail as unknown[]) {
      if (esRegistro(item) && esTexto(item['msg'])) return limpiar(item['msg']);
    }
  }
  return 'Revisá los datos que escribiste.';
}

function errorCaja(status: number, cuerpo: Registro): ErrorCaja {
  const motivo = cuerpo['motivo'];
  if (status === 403) return { tipo: 'sin_permiso' };
  if (status === 404) return { tipo: 'no_encontrado' };
  if (status === 503) return { tipo: 'reintentar' };
  if (status === 409) {
    if (motivo === 'caja_cerrada') return { tipo: 'caja_cerrada', dia: esTexto(cuerpo['dia']) ? cuerpo['dia'] : null };
    if (motivo === 'dia_no_terminado') {
      return { tipo: 'dia_no_terminado', cerrableDesde: esTexto(cuerpo['cerrable_desde']) ? cuerpo['cerrable_desde'] : null };
    }
    if (motivo === 'dia_ya_cerrado') return { tipo: 'dia_ya_cerrado' };
    return { tipo: 'estado_cambiado' }; // el pago ya no está en el estado que se mostraba
  }
  if (status === 422) return { tipo: 'validacion', mensaje: mensajeDeCaja(cuerpo) };
  return { tipo: 'desconocido' };
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
  if (status === 409 && motivo === 'plazo_vencido') {
    return { tipo: 'plazo_vencido', limiteCorreccion: esTexto(cuerpo['limite_correccion']) ? cuerpo['limite_correccion'] : null };
  }
  return { tipo: 'desconocido' };
}

// --- guardas de C-13 (auditoría y directorio de usuarios) -----------------------------------------------------------

function esRegistroAuditoria(v: unknown): v is RegistroAuditoria {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esTexto(v['fecha_hora']) &&
    (v['usuario'] === null || (esRegistro(v['usuario']) && esNumero(v['usuario']['id']) && esTexto(v['usuario']['nombre_completo']))) &&
    esTexto(v['accion']) &&
    esTexto(v['tipo']) &&
    esTexto(v['tipo_etiqueta']) &&
    esTexto(v['entidad']) &&
    textoONulo(v['entidad_id']) &&
    textoONulo(v['ip']) &&
    'datos_antes' in v &&
    'datos_despues' in v
  );
}

function aPaginaAuditoria(v: unknown): PaginaAuditoria {
  if (!esRegistro(v) || !textoONulo(v['siguiente'])) throw new ErrorDeRespuesta();
  return { items: lista(v['items'], esRegistroAuditoria), siguiente: v['siguiente'] };
}

function esUsuarioDirectorio(v: unknown): v is UsuarioDirectorio {
  return esRegistro(v) && esNumero(v['id']) && esTexto(v['nombre_completo']) && typeof v['activo'] === 'boolean';
}

function errorExportacion(r: Response): ErrorExportacion {
  if (r.status === 403) return { tipo: 'sin_permiso' };
  if (r.status === 422) return { tipo: 'validacion' };
  if (r.status === 429) return { tipo: 'limite', minutos: minutosDesdeRetryAfter(r.headers.get('Retry-After')) };
  return { tipo: 'servidor' };
}

// --- API -----------------------------------------------------------------------------------------------------

export interface Api {
  me(): Promise<Usuario>;
  agenda(consulta: Consulta): Promise<Agenda>;
  opciones(): Promise<Opciones>;
  disponibilidad(profesionalId: number, tratamientoId: number, dia: string): Promise<readonly Slot[]>;
  crearTurno(datos: DatosAlta): Promise<Resultado<TurnoCreado, ErrorAlta>>;
  marcar(turnoId: number, accion: AccionMarcable): Promise<Resultado<CambioEstado, ErrorEstado>>;
  deshacerAtendido(turnoId: number, motivo: MotivoDeshacer): Promise<Resultado<CambioEstado, ErrorEstado>>;
  // Caja, pendientes y cierres (C-12)
  caja(dia: string): Promise<CajaDia>;
  pendientes(): Promise<readonly Pendiente[]>;
  rechazarRevision(pagoId: number): Promise<Resultado<Rechazo, ErrorCaja>>;
  acreditarRevision(pagoId: number): Promise<Resultado<Acreditacion, ErrorCaja>>;
  registrarDevolucion(pagoId: number, referencia: string): Promise<Resultado<Devolucion, ErrorCaja>>;
  registrarDevolucionExcedente(aprobacionId: number, referencia: string): Promise<Resultado<Devolucion, ErrorCaja>>;
  cerrarCaja(dia: string): Promise<Resultado<CierreCaja, ErrorCaja>>;
  cierre(cierreId: number): Promise<CierreDetalle>;
  anularCierre(cierreId: number, motivo: string): Promise<Resultado<CierreCaja, ErrorCaja>>;
  // Indicadores y pacientes (C-12)
  ocupacion(desde: string, hasta: string): Promise<Ocupacion>;
  ausentismo(desde: string, hasta: string): Promise<Ausentismo>;
  listarPacientes(consulta: ConsultaPacientes): Promise<ListadoPacientes>;
  // Recordatorios de WhatsApp (C-09)
  recordatorios(): Promise<readonly Recordatorio[]>;
  marcarRecordatorioEnviado(id: number): Promise<Resultado<Recordatorio, ErrorRecordatorio>>;
  marcarRecordatorioFallido(id: number, motivo: MotivoFallo): Promise<Resultado<Recordatorio, ErrorRecordatorio>>;
  // Google Calendar (C-10)
  conexionesGoogle(): Promise<readonly ConexionGoogle[]>;
  conflictosGoogle(): Promise<readonly ConflictoGoogle[]>;
  iniciarGoogle(): Promise<Resultado<{ readonly url_autorizacion: string }, ErrorGoogle>>;
  desconectarGoogle(profesionalId: number): Promise<Resultado<null, ErrorGoogle>>;
  resolverConflicto(id: number, accion: AccionConflicto): Promise<Resultado<ConflictoGoogle, ErrorGoogle>>;
  // Datos: exportación y auditoría (C-13)
  /** Descarga el CSV con la sesión vigente (el token viaja en la cabecera, no en la URL); `hoy` da el nombre de respaldo. */
  descargarExportacion(parametros: ParametrosExportacion, hoy: string): Promise<Resultado<ArchivoExportado, ErrorExportacion>>;
  consultarAuditoria(consulta: ConsultaAuditoria): Promise<PaginaAuditoria>;
  listarUsuarios(): Promise<readonly UsuarioDirectorio[]>;
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

  /** DELETE sin cuerpo de respuesta (204). */
  async function borrar<E>(
    ruta: string,
    interpretar: (status: number, c: Registro) => E,
    desconocido: E,
  ): Promise<Resultado<null, E>> {
    let r: Response;
    try {
      r = await pedir(ruta, { method: 'DELETE' });
    } catch (e) {
      if (e instanceof ErrorSesion) throw e;
      return { ok: false, error: desconocido };
    }
    if (r.ok) return { ok: true, valor: null };
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
    deshacerAtendido(turnoId, motivo) {
      return escribir(`/api/panel/turnos/${String(turnoId)}/deshacer-atendido`, { motivo }, esCambio, errorEstado, {
        tipo: 'desconocido',
      });
    },
    async caja(dia) {
      return aCaja(await leer(`/api/panel/caja?${new URLSearchParams({ dia }).toString()}`));
    },
    async pendientes() {
      return lista(await leer('/api/panel/caja/pendientes'), esPendiente);
    },
    rechazarRevision(pagoId) {
      return escribir(`/api/panel/caja/revisiones/${String(pagoId)}/rechazar`, undefined, esRechazo, errorCaja, {
        tipo: 'desconocido',
      });
    },
    acreditarRevision(pagoId) {
      return escribir(`/api/admin/pagos-sena/${String(pagoId)}/acreditar`, undefined, esAcreditacion, errorCaja, {
        tipo: 'desconocido',
      });
    },
    registrarDevolucion(pagoId, referencia) {
      return escribir(`/api/panel/caja/devoluciones/senas/${String(pagoId)}`, { referencia }, esDevolucion, errorCaja, {
        tipo: 'desconocido',
      });
    },
    registrarDevolucionExcedente(aprobacionId, referencia) {
      return escribir(
        `/api/panel/caja/devoluciones/excedentes/${String(aprobacionId)}`,
        { referencia },
        esDevolucion,
        errorCaja,
        { tipo: 'desconocido' },
      );
    },
    cerrarCaja(dia) {
      return escribir('/api/panel/caja/cierres', { dia }, esCierre, errorCaja, { tipo: 'desconocido' });
    },
    async cierre(cierreId) {
      return aCierreDetalle(await leer(`/api/panel/caja/cierres/${String(cierreId)}`));
    },
    anularCierre(cierreId, motivo) {
      return escribir(`/api/panel/caja/cierres/${String(cierreId)}/anular`, { motivo }, esCierre, errorCaja, {
        tipo: 'desconocido',
      });
    },
    async ocupacion(desde, hasta) {
      return aOcupacion(await leer(`/api/panel/ocupacion?${new URLSearchParams({ desde, hasta }).toString()}`));
    },
    async ausentismo(desde, hasta) {
      return aAusentismo(await leer(`/api/panel/ausentismo?${new URLSearchParams({ desde, hasta }).toString()}`));
    },
    async listarPacientes(c) {
      const q = new URLSearchParams();
      if (c.q !== null) q.set('q', c.q);
      q.set('pagina', String(c.pagina));
      q.set('por_pagina', String(c.porPagina));
      if (c.conAusencias) q.set('con_ausencias', 'true');
      return aListado(await leer(`/api/panel/pacientes/listado?${q.toString()}`));
    },
    async descargarExportacion(parametros, hoy) {
      let r: Response;
      try {
        r = await pedir(`/api/panel/export?${parametrosExportacion(parametros)}`);
      } catch (e) {
        if (e instanceof ErrorSesion) throw e;
        return { ok: false, error: { tipo: 'red' } };
      }
      if (!r.ok) return { ok: false, error: errorExportacion(r) };
      try {
        const blob = await r.blob();
        return { ok: true, valor: { blob, nombre: nombreArchivo(r.headers.get('Content-Disposition'), parametros.entidad, hoy) } };
      } catch {
        return { ok: false, error: { tipo: 'red' } };
      }
    },
    async consultarAuditoria(consulta) {
      const q = consultaAuditoriaAQuery(consulta);
      return aPaginaAuditoria(await leer(q === '' ? '/api/panel/auditoria' : `/api/panel/auditoria?${q}`));
    },
    async listarUsuarios() {
      return lista(await leer('/api/panel/usuarios'), esUsuarioDirectorio);
    },
    async recordatorios() {
      const cuerpo = await leer('/api/panel/recordatorios?estado=pendiente&estado=fallido&estado=enviado');
      if (!esRegistro(cuerpo)) throw new ErrorDeRespuesta();
      return lista(cuerpo['items'], esRecordatorio);
    },
    marcarRecordatorioEnviado(id) {
      return escribir(`/api/panel/recordatorios/${String(id)}/enviado`, undefined, esRecordatorio, errorRecordatorio, {
        tipo: 'desconocido',
      });
    },
    async conexionesGoogle() {
      return lista(await leer('/api/panel/google-calendar/conexiones'), esConexionGoogle);
    },
    async conflictosGoogle() {
      return lista(await leer('/api/panel/google-calendar/conflictos?estado=abierto'), esConflictoGoogle);
    },
    iniciarGoogle() {
      return escribir('/api/panel/google-calendar/conexion/iniciar', undefined, esIniciar, errorGoogle, {
        tipo: 'desconocido',
      });
    },
    desconectarGoogle(profesionalId) {
      return borrar(`/api/panel/google-calendar/conexiones/${String(profesionalId)}`, errorGoogle, {
        tipo: 'desconocido',
      });
    },
    resolverConflicto(id, accion) {
      return escribir(
        `/api/panel/google-calendar/conflictos/${String(id)}/resolver`,
        { accion },
        esConflictoGoogle,
        errorGoogle,
        { tipo: 'desconocido' },
      );
    },
    marcarRecordatorioFallido(id, motivo) {
      return escribir(`/api/panel/recordatorios/${String(id)}/fallido`, { motivo }, esRecordatorio, errorRecordatorio, {
        tipo: 'desconocido',
      });
    },
  };
}

