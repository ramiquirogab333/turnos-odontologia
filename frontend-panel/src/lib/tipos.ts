/** Contratos del API del panel (C-08). Los montos viajan como texto decimal: solo se formatean, nunca se operan. */

export type Rol = 'admin' | 'odontologo' | 'recepcion';
export type EstadoTurno = 'en_espera' | 'reservado' | 'confirmado' | 'cancelado' | 'ausente' | 'atendido';
export type Accion = 'atendido' | 'ausente' | 'cancelar';
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
}

export interface Agenda {
  readonly vista: Vista;
  readonly desde: string;
  readonly hasta: string;
  readonly turnos: readonly TurnoAgenda[];
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
  | { readonly tipo: 'no_encontrado' }
  | { readonly tipo: 'sin_permiso' }
  | { readonly tipo: 'reintentar' }
  | { readonly tipo: 'desconocido' };

export type Resultado<T, E> = { readonly ok: true; readonly valor: T } | { readonly ok: false; readonly error: E };
