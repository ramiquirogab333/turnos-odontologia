import { describe, expect, it } from 'vitest';
import {
  agruparPorDia,
  diaClinica,
  etiquetaDiaCorta,
  etiquetaDiaLarga,
  horaClinica,
  hoyClinica,
  sumarDias,
} from './tiempo';

describe('tiempo (siempre hora de la clínica, -03:00, nunca la del navegador)', () => {
  it('el runner corre en una zona distinta de la clínica', () => {
    expect(new Date('2026-11-16T12:00:00Z').getTimezoneOffset()).not.toBe(180);
  });

  it('horaClinica convierte instantes con distinto offset a la misma hora local', () => {
    expect(horaClinica('2026-11-16T13:00:00Z')).toBe('10:00');
    expect(horaClinica('2026-11-16T10:00:00-03:00')).toBe('10:00');
    expect(horaClinica('2026-11-16T22:00:00+09:00')).toBe('10:00');
  });

  it('horaClinica conserva los minutos y completa con cero', () => {
    expect(horaClinica('2026-11-16T12:05:00Z')).toBe('09:05');
    expect(horaClinica('2026-11-16T20:30:00-03:00')).toBe('20:30');
  });

  it('diaClinica usa la fecha local de la clínica (borde de medianoche)', () => {
    expect(diaClinica('2026-11-17T02:30:00Z')).toBe('2026-11-16'); // 23:30 en Buenos Aires
    expect(diaClinica('2026-11-17T03:00:00Z')).toBe('2026-11-17'); // 00:00 en Buenos Aires
  });

  it('hoyClinica devuelve el día local de la clínica para un instante dado', () => {
    expect(hoyClinica(new Date('2026-11-17T02:30:00Z'))).toBe('2026-11-16');
    expect(hoyClinica(new Date('2026-11-17T12:00:00Z'))).toBe('2026-11-17');
  });

  it('sumarDias suma días calendario sin depender de la zona', () => {
    expect(sumarDias('2026-11-16', 14)).toBe('2026-11-30');
    expect(sumarDias('2026-12-30', 3)).toBe('2027-01-02');
    expect(sumarDias('2028-02-28', 1)).toBe('2028-02-29');
  });

  it('etiquetas de día en español', () => {
    expect(etiquetaDiaCorta('2026-11-16')).toBe('lun 16');
    expect(etiquetaDiaCorta('2026-11-21')).toBe('sáb 21');
    expect(etiquetaDiaLarga('2026-11-16')).toBe('lunes 16 de noviembre');
  });

  it('agruparPorDia agrupa por día de la clínica y ordena por inicio', () => {
    const slots = [
      { inicio: '2026-11-17T12:30:00Z', fin: '2026-11-17T13:00:00Z', profesional_id: 1, sillon_id: 1 },
      { inicio: '2026-11-16T12:00:00Z', fin: '2026-11-16T12:30:00Z', profesional_id: 1, sillon_id: 1 },
      { inicio: '2026-11-17T02:30:00Z', fin: '2026-11-17T03:00:00Z', profesional_id: 1, sillon_id: 1 },
    ];
    const grupos = agruparPorDia(slots);
    expect([...grupos.keys()]).toEqual(['2026-11-16', '2026-11-17']);
    expect(grupos.get('2026-11-16')?.map((s) => horaClinica(s.inicio))).toEqual(['09:00', '23:30']);
    expect(grupos.get('2026-11-17')?.map((s) => horaClinica(s.inicio))).toEqual(['09:30']);
  });

  it('agruparPorDia sin slots devuelve un mapa vacío', () => {
    expect(agruparPorDia([]).size).toBe(0);
  });
});
