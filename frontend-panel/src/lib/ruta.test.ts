import { afterEach, describe, expect, it } from 'vitest';
import { irA, leerSeccion, SECCIONES } from './ruta';

afterEach(() => {
  window.location.hash = '';
});

describe('leerSeccion', () => {
  it('reconoce cada sección del hash', () => {
    expect(leerSeccion('#/caja')).toBe('caja');
    expect(leerSeccion('#/pacientes')).toBe('pacientes');
    expect(leerSeccion('#/indicadores')).toBe('indicadores');
    expect(leerSeccion('#/agenda')).toBe('agenda');
  });

  it('un hash vacío o desconocido cae en la agenda', () => {
    expect(leerSeccion('')).toBe('agenda');
    expect(leerSeccion('#')).toBe('agenda');
    expect(leerSeccion('#/cualquier-cosa')).toBe('agenda');
    expect(leerSeccion('#/caja/extra')).toBe('agenda');
  });

  it('todas las secciones tienen su ruta', () => {
    expect(SECCIONES).toEqual(['agenda', 'pacientes', 'indicadores', 'caja']);
  });
});

describe('irA', () => {
  it('cambia el hash de la ventana', () => {
    irA('indicadores');
    expect(window.location.hash).toBe('#/indicadores');
    irA('caja');
    expect(window.location.hash).toBe('#/caja');
  });
});
