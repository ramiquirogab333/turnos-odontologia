import { esNumero, esRegistro, esTexto } from './guardas';

/**
 * Seña en curso que sobrevive a la redirección a Mercado Pago. El retorno puede abrirse en una pestaña
 * nueva, así que se guarda en localStorage (no por pestaña) y con vencimiento: la pre-reserva más una
 * gracia de 30 minutos, con tope de 24 horas. Se guarda lo mínimo (turno y código de gestión), con la
 * clave versionada; el código nunca viaja en la URL. Todo acceso va en try/catch: el almacenamiento
 * puede estar bloqueado (modo privado, política del navegador) y la app tiene que seguir funcionando.
 */
const CLAVE = 'sena-pendiente-v2';
const VERSION = 2;
const GRACIA_MS = 30 * 60_000;
const TOPE_MS = 24 * 3_600_000;

export interface SenaPendiente {
  readonly turnoId: number;
  readonly codigoGestion: string;
}

export interface SenaAGuardar extends SenaPendiente {
  /** Vencimiento de la pre-reserva (ISO), `vence_en` de la respuesta de la API. */
  readonly venceEn: string;
}

export function guardarPendiente(pendiente: SenaAGuardar, ahora: number = Date.now()): void {
  const vence = Date.parse(pendiente.venceEn);
  const limite = ahora + TOPE_MS;
  const expira = Number.isNaN(vence) ? limite : Math.min(vence + GRACIA_MS, limite);
  try {
    localStorage.setItem(
      CLAVE,
      JSON.stringify({ v: VERSION, turnoId: pendiente.turnoId, codigoGestion: pendiente.codigoGestion, expira }),
    );
  } catch {
    // sin almacenamiento: el retorno del checkout mostrará el aviso de "no encontramos tu reserva"
  }
}

export function leerPendiente(ahora: number = Date.now()): SenaPendiente | null {
  try {
    const crudo = localStorage.getItem(CLAVE);
    if (crudo === null) return null;
    const dato = JSON.parse(crudo) as unknown;
    if (
      esRegistro(dato) &&
      dato['v'] === VERSION &&
      esNumero(dato['turnoId']) &&
      esTexto(dato['codigoGestion']) &&
      esNumero(dato['expira'])
    ) {
      if (dato['expira'] > ahora) return { turnoId: dato['turnoId'], codigoGestion: dato['codigoGestion'] };
      localStorage.removeItem(CLAVE); // vencido: se limpia solo
    }
  } catch {
    // JSON corrupto o almacenamiento bloqueado
  }
  return null;
}

export function borrarPendiente(): void {
  try {
    localStorage.removeItem(CLAVE);
  } catch {
    // nada que borrar
  }
}
