/**
 * Zona horaria de la clínica (APP_TZ del backend). Toda hora que ve el paciente
 * se formatea en esta zona, nunca en la del navegador (también en el panel).
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

/** Lunes de la semana (lunes a domingo) que contiene a `dia`, como "YYYY-MM-DD". */
export function inicioSemana(dia: string): string {
  const diaSemana = (aUtcMediodia(dia).getUTCDay() + 6) % 7; // 0 = lunes
  return sumarDias(dia, -diaSemana);
}

const formatoDiaMes = new Intl.DateTimeFormat('es-AR', { timeZone: 'UTC', day: 'numeric', month: 'long' });
const formatoSoloDia = new Intl.DateTimeFormat('es-AR', { timeZone: 'UTC', day: 'numeric' });

/** "Semana del 17 al 23 de noviembre" (o "del 30 de noviembre al 6 de diciembre" si cruza de mes). */
export function etiquetaSemana(dia: string): string {
  const lunes = inicioSemana(dia);
  const domingo = sumarDias(lunes, 6);
  const mismoMes = lunes.slice(0, 7) === domingo.slice(0, 7);
  return mismoMes
    ? `Semana del ${formatoSoloDia.format(aUtcMediodia(lunes))} al ${formatoDiaMes.format(aUtcMediodia(domingo))}`
    : `Semana del ${formatoDiaMes.format(aUtcMediodia(lunes))} al ${formatoDiaMes.format(aUtcMediodia(domingo))}`;
}

/** "18/11" para mostrar un instante en la fecha de la clínica. */
export function fechaCorta(iso: string): string {
  const [, mes, dia] = diaClinica(iso).split('-');
  return `${dia ?? ''}/${mes ?? ''}`;
}
