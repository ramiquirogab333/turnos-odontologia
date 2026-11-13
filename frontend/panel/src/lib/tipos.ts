/** Contratos del API del panel (C-08). Los montos viajan como texto decimal: solo se formatean, nunca se operan. */

export type Rol = 'admin' | 'odontologo' | 'recepcion';
export type EstadoTurno = 'en_espera' | 'reservado' | 'confirmado' | 'cancelado' | 'ausente' | 'atendido';
export type Accion = 'atendido' | 'ausente' | 'cancelar' | 'deshacer_atendido';
/** Las acciones que se resuelven con un POST sin cuerpo; deshacer lleva un motivo. */
export type AccionMarcable = Exclude<Accion, 'deshacer_atendido'>;
export type MotivoDeshacer = 'turno_equivocado' | 'paciente_no_asistio' | 'otro';
export type Vista = 'dia' | 'semana';

export interface Usuario {
  readonly id: number;
  readonly email: string;
  readonly nombre_completo: string;
  readonly roles: readonly Rol[];
}

export interface Ref {
  readonly id: number;
  readonly nombre: string;
}

export interface TratamientoRef extends Ref {
  readonly duracion_minutos: number;
}

export interface SenaAgenda {
  readonly estado: string;
  readonly monto: string;
}

export interface TurnoAgenda {
  readonly id: number;
  readonly inicio: string;
  readonly fin: string;
  readonly estado: EstadoTurno;
  readonly bloquea_agenda: boolean;
  readonly origen: string;
  readonly profesional: Ref;
  readonly sillon: Ref;
  readonly tratamiento: TratamientoRef;
  readonly paciente_nombre: string | null;
  readonly paciente_telefono: string | null;
  readonly sena: SenaAgenda | null;
  readonly vence_en: string | null;
  readonly acciones: readonly Accion[];
  /** Estado del evento en Google Calendar y si hay un conflicto abierto (C-10). */
  readonly calendario: CalendarioTurno;
}

export type EstadoEvento = 'sin_evento' | 'pendiente' | 'sincronizado' | 'desvinculado';

export interface CalendarioTurno {
  readonly estado: EstadoEvento;
  readonly conflicto_abierto: boolean;
}

/** Franja ocupada en el Google Calendar de la profesional: solo horario, sin título (C-10, O19). */
export interface OcupadoGoogle {
  readonly profesional_id: number;
  readonly inicio: string;
  readonly fin: string;
}

export interface Agenda {
  readonly vista: Vista;
  readonly desde: string;
  readonly hasta: string;
  readonly turnos: readonly TurnoAgenda[];
  readonly ocupados_google: readonly OcupadoGoogle[];
}

export interface Opciones {
  readonly profesionales: readonly Ref[];
  readonly sillones: readonly Ref[];
  readonly tratamientos: readonly TratamientoRef[];
  readonly puede_escribir: boolean;
}

export interface Consulta {
  readonly vista: Vista;
  readonly fecha: string;
  readonly profesionalId: number | null;
  readonly sillonId: number | null;
}

export interface Slot {
  readonly inicio: string;
  readonly fin: string;
  readonly profesional_id: number;
  readonly sillon_id: number;
}

export interface Alternativa {
  readonly inicio: string;
  readonly fin: string;
  readonly sillon_id: number;
}

export interface DatosAlta {
  readonly profesionalId: number;
  readonly tratamientoId: number;
  readonly inicio: string;
  readonly nombre: string;
  readonly telefono: string;
}

export interface TurnoCreado {
  readonly id: number;
  readonly inicio: string;
  readonly fin: string;
  readonly estado: 'reservado';
  readonly origen: 'manual';
  readonly profesional_id: number;
  readonly sillon_id: number;
  readonly tratamiento_id: number;
  readonly codigo_gestion: string;
  /** El horario figura ocupado en el Google Calendar de la profesional (C-10, O10): el turno se creó igual. */
  readonly aviso_google_calendar: boolean;
}

export interface CambioEstado {
  readonly turno_id: number;
  readonly estado: string;
  readonly estado_sena: string | null;
}

/** Rechazos de negocio del alta: la pantalla decide qué decir según el tipo. */
export type ErrorAlta =
  | { readonly tipo: 'conflicto'; readonly motivo: 'profesional' | 'sillon'; readonly alternativas: readonly Alternativa[] }
  | { readonly tipo: 'fuera_de_disponibilidad' }
  | { readonly tipo: 'inicio_pasado' }
  | { readonly tipo: 'validacion'; readonly mensaje: string }
  | { readonly tipo: 'sin_permiso' }
  | { readonly tipo: 'desconocido' };

/** Rechazos de negocio de ausente, atendido y cancelar. */
export type ErrorEstado =
  | { readonly tipo: 'marcado_no_habilitado'; readonly habilitadoDesde: string | null }
  | { readonly tipo: 'fuera_de_plazo'; readonly limiteCambios: string | null }
  | { readonly tipo: 'transicion_invalida' }
  | { readonly tipo: 'plazo_vencido'; readonly limiteCorreccion: string | null }
  | { readonly tipo: 'no_encontrado' }
  | { readonly tipo: 'sin_permiso' }
  | { readonly tipo: 'reintentar' }
  | { readonly tipo: 'desconocido' };

export type Resultado<T, E> = { readonly ok: true; readonly valor: T } | { readonly ok: false; readonly error: E };

// --- Caja, cierres y pendientes (C-12). Los importes y porcentajes viajan como texto decimal. ---------------------

export type ConceptoCaja = 'sena' | 'pago_presupuesto' | 'devolucion_sena';
export type MedioCaja = 'mercadopago' | 'transferencia';

export interface LineaCaja {
  readonly concepto: ConceptoCaja;
  readonly medio: MedioCaja;
  readonly cantidad: number;
  readonly total: string;
}

export interface MovimientoCaja {
  readonly concepto: ConceptoCaja;
  readonly medio: MedioCaja;
  readonly importe: string;
  readonly hora: string;
  readonly referencia: string | null;
  readonly turno_id: number | null;
  readonly presupuesto_id: number | null;
}

export interface CajaDia {
  readonly dia: string;
  readonly estado: 'abierto' | 'cerrado';
  readonly cierre_id: number | null;
  readonly lineas: readonly LineaCaja[];
  readonly total_ingresos: string;
  readonly total_egresos: string;
  readonly total_neto: string;
  readonly senas_retenidas: { readonly cantidad: number; readonly total: string };
  readonly movimientos: readonly MovimientoCaja[];
}

export interface Pendiente {
  readonly tipo: 'revision' | 'sena' | 'excedente_mp';
  readonly id: number;
  readonly pago_id: number;
  readonly turno_id: number;
  readonly estado_turno: string;
  readonly medio: MedioCaja;
  readonly importe: string | null;
  readonly importe_a_verificar: boolean;
  readonly mp_payment_id: string | null;
  readonly pendiente_desde: string;
}

export interface Rechazo {
  readonly pago_id: number;
  readonly turno_id: number;
  readonly estado_pago: string;
  readonly estado_turno: string;
  readonly importe: string;
}

export interface Acreditacion {
  readonly pago_id: number;
  readonly turno_id: number;
  readonly efecto: string;
  readonly estado_pago: string;
  readonly estado_turno: string;
}

export interface Devolucion {
  readonly id: number;
  readonly tipo: 'sena' | 'excedente_mp';
  readonly pago_id: number;
  readonly turno_id: number;
  readonly importe: string | null;
  readonly reembolsado_en: string;
  readonly referencia: string;
}

export interface CierreCaja {
  readonly id: number;
  readonly dia: string;
  readonly estado: 'vigente' | 'anulado';
  readonly total_ingresos: string;
  readonly total_egresos: string;
  readonly total_neto: string;
  readonly observaciones: string | null;
  readonly cerrado_por_nombre: string | null;
  readonly cerrado_en: string;
  readonly anulado_en: string | null;
  readonly anulado_motivo: string | null;
  readonly lineas: readonly LineaCaja[];
}

export interface DiferenciaCierre {
  readonly concepto: ConceptoCaja;
  readonly medio: MedioCaja;
  readonly total_cierre: string;
  readonly total_actual: string;
  readonly cantidad_cierre: number;
  readonly cantidad_actual: number;
}

export interface CierreDetalle extends CierreCaja {
  readonly cuadra: boolean | null;
  readonly diferencias: readonly DiferenciaCierre[];
}

/** Rechazos de negocio de la caja, los cierres y los pendientes. */
export type ErrorCaja =
  | { readonly tipo: 'caja_cerrada'; readonly dia: string | null }
  | { readonly tipo: 'dia_no_terminado'; readonly cerrableDesde: string | null }
  | { readonly tipo: 'dia_ya_cerrado' }
  | { readonly tipo: 'estado_cambiado' }
  | { readonly tipo: 'no_encontrado' }
  | { readonly tipo: 'validacion'; readonly mensaje: string }
  | { readonly tipo: 'sin_permiso' }
  | { readonly tipo: 'reintentar' }
  | { readonly tipo: 'desconocido' };

// --- Indicadores y listado de pacientes (C-12) ---------------------------------------------------------------------

export interface OcupacionDia {
  readonly dia: string;
  readonly minutos_ocupados: number;
  readonly minutos_atencion: number;
  readonly porcentaje: string | null;
  readonly turnos: number;
  readonly minutos_perdidos: number;
}

export interface OcupacionSillon {
  readonly sillon_id: number;
  readonly nombre: string;
  readonly estado: 'activo' | 'inactivo' | 'mantenimiento';
  readonly dias: readonly OcupacionDia[];
}

export interface Ocupacion {
  readonly desde: string;
  readonly hasta: string;
  readonly sillones: readonly OcupacionSillon[];
}

export interface AusentismoProfesional {
  readonly profesional_id: number;
  readonly nombre: string;
  readonly atendidos: number;
  readonly ausentes: number;
  readonly tasa: string | null;
  readonly sin_marcar: number;
}

export interface Ausentismo {
  readonly desde: string;
  readonly hasta: string;
  readonly atendidos: number;
  readonly ausentes: number;
  readonly tasa: string | null;
  readonly sin_marcar: number;
  readonly por_profesional: readonly AusentismoProfesional[];
  readonly recupero: {
    readonly senas_retenidas: number;
    readonly importe_retenido: string;
    readonly porcentaje: string | null;
  };
}

export interface ConsultaPacientes {
  readonly q: string | null;
  readonly pagina: number;
  readonly porPagina: number;
  readonly conAusencias: boolean;
}

export interface PacienteListado {
  readonly id: number;
  readonly nombre: string;
  readonly apellido: string;
  readonly dni: string;
  readonly telefono: string;
  readonly obra_social: Ref | null;
  readonly atendidos: number;
  readonly ausentes: number;
  readonly ultimo_turno: string | null;
}

export interface ListadoPacientes {
  readonly total: number;
  readonly pagina: number;
  readonly por_pagina: number;
  readonly pacientes: readonly PacienteListado[];
}

// --- Recordatorios de WhatsApp (C-09) ----------------------------------------------------------------------------

export type EstadoRecordatorio = 'pendiente' | 'enviado' | 'confirmado' | 'fallido';
/** Motivos que recepción puede declarar al marcar "No se pudo enviar". */
export type MotivoFallo = 'numero_invalido' | 'sin_whatsapp' | 'otro';

export interface Recordatorio {
  readonly id: number;
  readonly turno_id: number;
  readonly estado: EstadoRecordatorio;
  readonly motivo: string | null;
  readonly turno_inicio: string;
  readonly profesional: string;
  readonly tratamiento: string;
  readonly contacto_nombre: string | null;
  readonly enviado_en: string | null;
  readonly intentos_fallidos: number;
  /** `https://wa.me/...` armado por el servidor; `null` si no hay teléfono válido o ya no corresponde avisar. */
  readonly link: string | null;
}

export type ErrorRecordatorio =
  | { readonly tipo: 'no_vigente' }
  | { readonly tipo: 'no_encontrado' }
  | { readonly tipo: 'sin_permiso' }
  | { readonly tipo: 'desconocido' };

// --- Google Calendar (C-10) -------------------------------------------------------------------------------------

export type EstadoConexion = 'sin_conectar' | 'pendiente' | 'activa' | 'revocada' | 'desconectada';

export interface ConexionGoogle {
  readonly profesional_id: number;
  readonly profesional_nombre: string;
  readonly estado: EstadoConexion;
  readonly cuenta_email: string | null;
  readonly ultima_sync_ok_en: string | null;
  readonly conflictos_abiertos: number;
  /** Qué hacer ("Volvé a conectar Google Calendar") cuando la conexión necesita atención. */
  readonly indicacion: string | null;
}

export type TipoConflicto = 'movido_en_google' | 'borrado_en_google' | 'solapa_evento_externo';
export type AccionConflicto = 'restaurar_en_google' | 'desvincular' | 'revisado';

export interface ConflictoGoogle {
  readonly id: number;
  readonly tipo: TipoConflicto;
  readonly estado: 'abierto' | 'resuelto';
  /** Criterio visible (RN-GC-02): qué pasó y qué se puede hacer. */
  readonly criterio: string;
  readonly turno_id: number;
  readonly profesional_id: number;
  readonly profesional_nombre: string;
  readonly tratamiento: string;
  readonly sistema_inicio: string;
  readonly sistema_fin: string;
  readonly google_inicio: string | null;
  readonly google_fin: string | null;
  /** Vacío para la odontóloga: ve el conflicto sin acciones. */
  readonly acciones: readonly AccionConflicto[];
  readonly resolucion: string | null;
  readonly detectado_en: string;
  readonly resuelto_en: string | null;
}

export type ErrorGoogle =
  | { readonly tipo: 'sin_permiso' }
  | { readonly tipo: 'no_encontrado' }
  | { readonly tipo: 'conexion_activa' }
  | { readonly tipo: 'no_configurado' }
  | { readonly tipo: 'conflicto_cerrado' }
  | { readonly tipo: 'accion_no_valida' }
  | { readonly tipo: 'desconocido' };

// --- Datos: exportación y auditoría (C-13) ------------------------------------------------------------------------

export type EntidadExportable = 'turnos' | 'pacientes' | 'cierres_caja';

export interface ParametrosExportacion {
  readonly entidad: EntidadExportable;
  /** Fechas locales de la clínica `AAAA-MM-DD`; vacías o `null` = sin ese extremo. */
  readonly desde: string | null;
  readonly hasta: string | null;
  readonly incluirInactivos: boolean;
}

export interface ArchivoExportado {
  readonly blob: Blob;
  readonly nombre: string;
}

export type ErrorExportacion =
  | { readonly tipo: 'sin_permiso' }
  | { readonly tipo: 'limite'; readonly minutos: number }
  | { readonly tipo: 'validacion' }
  | { readonly tipo: 'servidor' }
  | { readonly tipo: 'red' };

export interface UsuarioDirectorio {
  readonly id: number;
  readonly nombre_completo: string;
  readonly activo: boolean;
}

export interface UsuarioAuditoria {
  readonly id: number;
  readonly nombre_completo: string;
}

export interface RegistroAuditoria {
  readonly id: number;
  readonly fecha_hora: string;
  readonly usuario: UsuarioAuditoria | null;
  readonly accion: string;
  readonly tipo: string;
  readonly tipo_etiqueta: string;
  readonly entidad: string;
  readonly entidad_id: string | null;
  readonly datos_antes: unknown;
  readonly datos_despues: unknown;
  readonly ip: string | null;
}

export interface PaginaAuditoria {
  readonly items: readonly RegistroAuditoria[];
  readonly siguiente: string | null;
}

export interface ConsultaAuditoria {
  readonly desde: string | null;
  readonly hasta: string | null;
  readonly usuarioId: number | null;
  readonly tipo: string | null;
  readonly entidad: string | null;
  readonly entidadId: string | null;
  readonly cursor: string | null;
}
