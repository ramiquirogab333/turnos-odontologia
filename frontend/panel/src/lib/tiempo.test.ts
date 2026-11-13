import { describe, expect, it } from 'vitest';
import { diaClinica, etiquetaSemana, fechaCorta, horaClinica, inicioSemana, sumarDias } from './tiempo';

describe('tiempo (hora de la clínica)', () => {
  it('muestra la hora de Buenos Aires aunque el navegador esté en Tokyo', () => {
    expect(horaClinica('2031-11-18T12:00:00Z')).toBe('09:00');
    expect(horaClinica('2031-11-18T09:00:00-03:00')).toBe('09:00');
  });

  it('el día de un instante es el de la clínica, no el UTC', () => {
    expect(diaClinica('2031-11-19T02:30:00Z')).toBe('2031-11-18');
    expect(fechaCorta('2031-11-19T02:30:00Z')).toBe('18/11');
  });

  it.each([
    ['2031-11-17', '2031-11-17'], // lunes
    ['2031-11-18', '2031-11-17'],
    ['2031-11-23', '2031-11-17'], // domingo
    ['2031-11-24', '2031-11-24'],
  ])('el lunes de la semana de %s es %s', (dia, lunes) => {
    expect(inicioSemana(dia)).toBe(lunes);
  });

  it('suma días calendario cruzando mes y año', () => {
    expect(sumarDias('2031-12-31', 1)).toBe('2032-01-01');
    expect(sumarDias('2031-11-01', -1)).toBe('2031-10-31');
  });

  it('rotula la semana, también cuando cruza de mes', () => {
    expect(etiquetaSemana('2031-11-18')).toBe('Semana del 17 al 23 de noviembre');
    expect(etiquetaSemana('2031-12-01')).toBe('Semana del 1 al 7 de diciembre');
    expect(etiquetaSemana('2031-12-31')).toBe('Semana del 29 de diciembre al 4 de enero');
  });
});
