import { esNumero, esRegistro, esTexto } from './guardas';
import type { Alternativa } from './tipos';
import { mensajeLimite } from './limite';
import { EJEMPLO_TELEFONO } from './validacion';

export interface CamposConError {
  nombre?: string;
  telefono?: string;
}

export type ErrorApi =
  | { readonly tipo: 'validacion'; readonly campos: CamposConError; readonly generales: readonly string[] }
  | { readonly tipo: 'fuera_de_horario'; readonly mensaje: string }
  | { readonly tipo: 'conflicto'; readonly motivo: 'profesional' | 'sillon'; readonly alternativas: readonly Alternativa[] }
  | { readonly tipo: 'limite'; readonly mensaje: string }
  | { readonly tipo: 'desconocido'; readonly mensaje: string };

const MENSAJE_CAMPO: Readonly<Record<keyof CamposConError, string>> = {
  nombre: 'Ingresá tu nombre completo (hasta 200 caracteres).',
  telefono: `Ingresá el teléfono con código de país, por ejemplo ${EJEMPLO_TELEFONO}.`,
};

const DESCONOCIDO: ErrorApi = {
  tipo: 'desconocido',
  mensaje: 'No pudimos completar la operación. Intentá de nuevo en unos minutos.',
};

function esAlternativa(valor: unknown): valor is Alternativa {
  return esRegistro(valor) && esTexto(valor['inicio']) && esTexto(valor['fin']) && esNumero(valor['sillon_id']);
}

function esCampoConocido(campo: unknown): campo is keyof CamposConError {
  return campo === 'nombre' || campo === 'telefono';
}

function limpiarMensaje(msg: string): string {
  return msg.replace(/^Value error,\s*/i, '');
}

function interpretar422(detail: unknown): ErrorApi {
  if (esTexto(detail)) {
    // El backend usa texto plano para horario fuera de la agenda o referencias inexistentes.
    return { tipo: 'fuera_de_horario', mensaje: 'Ese horario ya no está disponible. Elegí otro horario.' };
  }
  if (!Array.isArray(detail)) return DESCONOCIDO;
  const campos: CamposConError = {};
  const generales: string[] = [];
  for (const item of detail as unknown[]) {
    if (!esRegistro(item)) continue;
    const loc = item['loc'];
    const campo = Array.isArray(loc) ? (loc as unknown[]).at(-1) : undefined;
    if (esCampoConocido(campo)) campos[campo] = MENSAJE_CAMPO[campo];
    else if (esTexto(item['msg'])) generales.push(limpiarMensaje(item['msg']));
  }
  return { tipo: 'validacion', campos, generales };
}

function interpretar409(cuerpo: Record<string, unknown>): ErrorApi {
  const { motivo, alternativas } = cuerpo;
  if (motivo !== 'profesional' && motivo !== 'sillon') return DESCONOCIDO;
  const lista = Array.isArray(alternativas) ? (alternativas as unknown[]).filter(esAlternativa) : [];
  return { tipo: 'conflicto', motivo, alternativas: lista };
}

/** Normaliza cualquier respuesta de error de POST /api/public/turnos a un tipo cerrado. */
export function interpretarRespuestaError(status: number, cuerpo: unknown, retryAfter: string | null = null): ErrorApi {
  if (status === 429) return { tipo: 'limite', mensaje: mensajeLimite(retryAfter) };
  if (!esRegistro(cuerpo)) return DESCONOCIDO;
  if (status === 422) return interpretar422(cuerpo['detail']);
  if (status === 409) return interpretar409(cuerpo);
  return DESCONOCIDO;
}
