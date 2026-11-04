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

export interface ReservaCreada {
  readonly turno_id: number;
  readonly codigo_gestion: string;
  readonly estado: string;
  readonly inicio: string;
  readonly fin: string;
}

export interface ReservaRequest {
  readonly nombre: string;
  readonly telefono: string;
  readonly tratamiento_id: number;
  readonly profesional_id: number;
  readonly inicio: string;
}
