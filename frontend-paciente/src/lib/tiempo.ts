import type { Slot } from './tipos';

/**
 * Zona horaria de la clínica (APP_TZ del backend). Toda hora que ve el paciente
 * se formatea en esta zona, nunca en la del navegador.
 */
export const ZONA_CLINICA = 'America/Argentina/Buenos_Aires';

const formatoHora = new Intl.DateTimeFormat('es-AR', {
  timeZone: ZONA_CLINICA,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

const formatoDia = new Intl.DateTimeFormat('en-CA', {
  timeZone: ZONA_CLINICA,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const formatoCorto = new Intl.DateTimeFormat('es-AR', { timeZone: 'UTC', weekday: 'short', day: 'numeric' });
const formatoLargo = new Intl.DateTimeFormat('es-AR', {
  timeZone: 'UTC',
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});

/** Un instante ISO (con cualquier offset) a "HH:mm" en hora de la clínica. */
export function horaClinica(iso: string): string {
  return formatoHora.format(new Date(iso));
}

/** Fecha local de la clínica ("YYYY-MM-DD") de un instante. */
export function diaClinica(iso: string): string {
  return formatoDia.format(new Date(iso));
}

/** "Hoy" según la clínica, no según el navegador. */
export function hoyClinica(ahora: Date): string {
  return formatoDia.format(ahora);
}

function aUtcMediodia(dia: string): Date {
  return new Date(`${dia}T12:00:00Z`);
}

/** Suma días calendario a "YYYY-MM-DD" (aritmética en UTC: sin saltos de horario). */
export function sumarDias(dia: string, dias: number): string {
  const fecha = aUtcMediodia(dia);
  fecha.setUTCDate(fecha.getUTCDate() + dias);
  return fecha.toISOString().slice(0, 10);
}

/** "lun 16". */
export function etiquetaDiaCorta(dia: string): string {
  return formatoCorto
    .format(aUtcMediodia(dia))
    .replace('.', '')
    .replace(/^(\S+),?\s+/, '$1 ');
}

/** "lunes 16 de noviembre". */
export function etiquetaDiaLarga(dia: string): string {
  return formatoLargo.format(aUtcMediodia(dia)).replace(',', '');
}

/** Agrupa slots por día de la clínica; días y horarios en orden cronológico. */
export function agruparPorDia(slots: readonly Slot[]): Map<string, Slot[]> {
  const ordenados = [...slots].sort((a, b) => Date.parse(a.inicio) - Date.parse(b.inicio));
  const grupos = new Map<string, Slot[]>();
  for (const slot of ordenados) {
    const dia = diaClinica(slot.inicio);
    const lista = grupos.get(dia);
    if (lista) lista.push(slot);
    else grupos.set(dia, [slot]);
  }
  return grupos;
}

const formatoSemana = new Intl.DateTimeFormat('es-AR', { timeZone: 'UTC', weekday: 'long' });

/** "martes 17/11" (día de la semana y fecha numérica, para frases cortas). */
export function etiquetaDiaNumerica(dia: string): string {
  const [, mes, numero] = dia.split('-');
  return `${formatoSemana.format(aUtcMediodia(dia))} ${numero ?? ''}/${mes ?? ''}`;
}
