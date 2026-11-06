/** Contrato de la API pública (backend/src/app/public/schemas.py). */

export interface Tratamiento {
  readonly id: number;
  readonly nombre: string;
  readonly duracion_minutos: number;
  /** Decimal serializado como texto (R4: nunca float para dinero). */
  readonly precio_base: string;
}

export interface Profesional {
  readonly id: number;
  readonly nombre: string;
  readonly especialidad: string;
}

export interface Slot {
  readonly inicio: string;
  readonly fin: string;
  readonly profesional_id: number;
  readonly sillon_id: number;
}

/** Alternativa libre devuelta por el 409 (mismo profesional). */
export interface Alternativa {
  readonly inicio: string;
  readonly fin: string;
  readonly sillon_id: number;
}

export interface Catalogo {
  readonly tratamientos: readonly Tratamiento[];
  readonly profesionales: readonly Profesional[];
}

export type MedioSena = 'mercadopago' | 'transferencia';

/** Seña a pagar (C-06). El monto es un decimal serializado como texto (R4: nunca float). */
export interface SenaInfo {
  readonly monto: string;
  readonly vence_en: string;
  readonly medios_habilitados: readonly MedioSena[];
  readonly texto_politica_reembolso: string;
}

interface ReservaBase {
  readonly turno_id: number;
  readonly codigo_gestion: string;
  readonly inicio: string;
  readonly fin: string;
}

/** Pre-reserva: no bloquea la agenda hasta que se acredita la seña. */
export interface ReservaEnEspera extends ReservaBase {
  readonly estado: 'en_espera';
  readonly sena: SenaInfo;
}

/** Turno ya reservado (por ejemplo, tratamiento exento de seña). */
export interface ReservaConfirmada extends ReservaBase {
  readonly estado: 'reservado';
  readonly sena: null;
}

export type ReservaCreada = ReservaEnEspera | ReservaConfirmada;

export type EstadoTurno = 'en_espera' | 'reservado' | 'confirmado' | 'cancelado' | 'ausente' | 'atendido';
export type EstadoPago = 'pendiente' | 'acreditado' | 'vencido' | 'no_reembolsado' | 'a_reembolsar' | 'en_revision';

/** Datos comunes del pago devueltos por POST y GET /api/public/turnos/{id}/sena. */
interface DatosPago {
  readonly turno_id: number;
  readonly pago_id: number | null;
  readonly medio: MedioSena | null;
  readonly monto: string;
  readonly vence_en: string | null;
  readonly texto_politica_reembolso: string;
  readonly referencia_externa: string | null;
  readonly checkout_url: string | null;
  readonly alias: string | null;
  readonly cbu: string | null;
  readonly titular: string | null;
  readonly referencia_concepto: string | null;
}

export interface InicioSena extends DatosPago {
  readonly estado: EstadoPago;
}

export interface EstadoSena extends DatosPago {
  readonly estado_turno: EstadoTurno;
  readonly estado_pago: EstadoPago | null;
  /** El servidor ya considera vencida la pre-reserva (aunque el barrido todavía no la cancele). */
  readonly vencida: boolean;
  readonly medios_habilitados: readonly MedioSena[];
  readonly inicio: string;
  readonly fin: string;
  readonly tratamiento_nombre: string;
  readonly profesional_nombre: string;
}

/** Errores tipados de los endpoints de seña. */
export type ErrorSena =
  | { readonly tipo: 'vencida' }
  | { readonly tipo: 'horario_tomado' }
  | { readonly tipo: 'no_encontrada' }
  | { readonly tipo: 'medio'; readonly mensaje: string }
  | { readonly tipo: 'pasarela'; readonly mensaje: string }
  | { readonly tipo: 'desconocido'; readonly mensaje: string };

export interface ReservaRequest {
  readonly nombre: string;
  readonly telefono: string;
  readonly tratamiento_id: number;
  readonly profesional_id: number;
  readonly inicio: string;
}
