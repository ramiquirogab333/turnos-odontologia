import type { Antecedentes, DatosFicha, ErrorClinico } from './tipos';

export const MAX_ANTECEDENTE = 2000;

export const CAMPOS_FICHA: readonly { readonly clave: keyof Antecedentes; readonly etiqueta: string }[] = [
  { clave: 'alergias', etiqueta: 'Alergias' },
  { clave: 'medicacion', etiqueta: 'Medicación' },
  { clave: 'antecedentes_medicos', etiqueta: 'Antecedentes médicos' },
  { clave: 'observaciones', etiqueta: 'Observaciones' },
];

/** Campos cuyo texto difiere entre lo guardado y lo escrito, en el orden de la ficha. */
export function camposCambiados(base: Antecedentes, borrador: Antecedentes): readonly (keyof Antecedentes)[] {
  return CAMPOS_FICHA.filter(({ clave }) => base[clave] !== borrador[clave]).map(({ clave }) => clave);
}

/** Cuerpo del `PUT`: los cuatro campos y la versión que se leyó (0 = ficha todavía no creada). */
export function cuerpoDeFicha(borrador: Antecedentes, version: number): DatosFicha {
  return {
    alergias: borrador.alergias,
    medicacion: borrador.medicacion,
    antecedentes_medicos: borrador.antecedentes_medicos,
    observaciones: borrador.observaciones,
    version,
  };
}

export function contador(texto: string): string {
  return `${String(texto.length)}/${String(MAX_ANTECEDENTE)}`;
}

export function mensajeDeFicha(error: ErrorClinico): string {
  switch (error.tipo) {
    case 'version_desactualizada':
      return 'Alguien guardó la ficha mientras la editabas';
    case 'acceso_vencido':
      return 'Tu acceso para editar venció. Para editar, pedí un turno a recepción';
    case 'paciente_ajeno':
      return 'No tenés acceso a esta paciente: el acceso empieza cuando un turno con vos se marca atendido';
    case 'sin_permiso':
      return 'Tu usuario no puede editar la ficha.';
    case 'no_encontrado':
      return 'No encontramos ese paciente.';
    case 'validacion':
      return error.mensaje;
    default:
      return 'No pudimos guardar la ficha. Revisá tu conexión e intentá de nuevo';
  }
}
