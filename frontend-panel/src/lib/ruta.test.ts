import { afterEach, describe, expect, it } from 'vitest';
import { irA, leerSeccion, resultadoDeGoogle, SECCIONES, SECCIONES_ODONTOLOGA } from './ruta';

afterEach(() => {
  window.location.hash = '';
});

describe('leerSeccion', () => {
  it('reconoce cada sección del hash', () => {
    expect(leerSeccion('#/caja')).toBe('caja');
    expect(leerSeccion('#/pacientes')).toBe('pacientes');
    expect(leerSeccion('#/indicadores')).toBe('indicadores');
    expect(leerSeccion('#/agenda')).toBe('agenda');
    expect(leerSeccion('#/recordatorios')).toBe('recordatorios');
    expect(leerSeccion('#/google-calendar')).toBe('google-calendar');
  });

  it('ignora la query del hash (la vuelta de Google trae ?resultado=)', () => {
    expect(leerSeccion('#/google-calendar?resultado=conectado')).toBe('google-calendar');
    expect(leerSeccion('#/caja?x=1')).toBe('caja');
  });

  it('un hash vacío o desconocido cae en la agenda', () => {
    expect(leerSeccion('')).toBe('agenda');
    expect(leerSeccion('#')).toBe('agenda');
    expect(leerSeccion('#/cualquier-cosa')).toBe('agenda');
    expect(leerSeccion('#/caja/extra')).toBe('agenda');
  });

  it('todas las secciones tienen su ruta', () => {
    expect(SECCIONES).toEqual(['agenda', 'pacientes', 'indicadores', 'caja', 'recordatorios', 'google-calendar']);
    expect(SECCIONES_ODONTOLOGA).toEqual(['agenda', 'google-calendar']);
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

describe('resultadoDeGoogle', () => {
  it.each(['conectado', 'error_autorizacion', 'permiso_denegado'])('lee el resultado "%s"', (resultado) => {
    expect(resultadoDeGoogle(`#/google-calendar?resultado=${resultado}`)).toBe(resultado);
  });

  it.each(['#/google-calendar', '#/google-calendar?resultado=raro', '#/caja?resultado=conectado', '', '#/google-calendar?otro=1'])(
    'sin resultado válido en "%s" devuelve null',
    (hash) => {
      expect(resultadoDeGoogle(hash)).toBeNull();
    },
  );
});
