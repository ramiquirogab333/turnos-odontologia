import { afterEach, describe, expect, it } from 'vitest';
import { irA, leerDetallePaciente, leerSeccion, pestanaDeCatalogo, pestanaDeDatos, resultadoDeGoogle, SECCIONES, SECCIONES_ODONTOLOGA } from './ruta';

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
    expect(leerSeccion('#/datos')).toBe('datos');
    expect(leerSeccion('#/catalogo')).toBe('catalogo');
    expect(leerSeccion('#/catalogo?pestana=horarios')).toBe('catalogo');
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
    expect(SECCIONES).toEqual(['agenda', 'pacientes', 'indicadores', 'caja', 'recordatorios', 'google-calendar', 'datos', 'catalogo']);
    expect(SECCIONES_ODONTOLOGA).toEqual(['agenda', 'google-calendar']);
    expect(SECCIONES_ODONTOLOGA).not.toContain('catalogo');
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

describe('pestanaDeDatos', () => {
  it('abre la auditoría solo con ?pestana=auditoria en #/datos', () => {
    expect(pestanaDeDatos('#/datos?pestana=auditoria')).toBe('auditoria');
    expect(pestanaDeDatos('#/datos?pestana=exportar')).toBe('exportar');
  });

  it('todo lo demás abre la exportación', () => {
    expect(pestanaDeDatos('#/datos')).toBe('exportar');
    expect(pestanaDeDatos('#/datos?pestana=otra')).toBe('exportar');
    expect(pestanaDeDatos('#/caja?pestana=auditoria')).toBe('exportar');
    expect(pestanaDeDatos('')).toBe('exportar');
  });
});

describe('pestanaDeCatalogo', () => {
  it.each(['tratamientos', 'profesionales', 'sillones', 'horarios'])('abre la pestaña válida "%s"', (pestana) => {
    expect(pestanaDeCatalogo(`#/catalogo?pestana=${pestana}`)).toBe(pestana);
  });

  it.each(['#/catalogo', '#/catalogo?pestana=precios', '#/catalogo?otro=1', '#/datos?pestana=horarios', ''])(
    'un valor inválido o de otra sección ("%s") abre Tratamientos',
    (hash) => {
      expect(pestanaDeCatalogo(hash)).toBe('tratamientos');
    },
  );
});

describe('leerDetallePaciente', () => {
  it('lee el id y abre la ficha por defecto', () => {
    expect(leerDetallePaciente('#/pacientes/7')).toEqual({ pacienteId: 7, pestana: 'ficha' });
    expect(leerDetallePaciente('#/pacientes/120?x=1')).toEqual({ pacienteId: 120, pestana: 'ficha' });
  });

  it('reconoce las pestañas válidas y manda las inválidas a la ficha', () => {
    expect(leerDetallePaciente('#/pacientes/7?pestana=odontograma')?.pestana).toBe('odontograma');
    expect(leerDetallePaciente('#/pacientes/7?pestana=presupuestos')?.pestana).toBe('presupuestos');
    expect(leerDetallePaciente('#/pacientes/7?pestana=datos')?.pestana).toBe('datos');
    expect(leerDetallePaciente('#/pacientes/7?pestana=radiografias')?.pestana).toBe('ficha');
  });

  it('un id que no es un entero positivo, o una ruta más larga, no es un detalle', () => {
    expect(leerDetallePaciente('#/pacientes/0')).toBeNull();
    expect(leerDetallePaciente('#/pacientes/abc')).toBeNull();
    expect(leerDetallePaciente('#/pacientes/-3')).toBeNull();
    expect(leerDetallePaciente('#/pacientes/7/x')).toBeNull();
    expect(leerDetallePaciente('#/pacientes')).toBeNull();
    expect(leerDetallePaciente('#/caja/7')).toBeNull();
  });

  it('la sección sigue siendo pacientes para la ruta del detalle', () => {
    expect(leerSeccion('#/pacientes/7')).toBe('pacientes');
  });
});
