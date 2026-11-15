import { describe, expect, it } from 'vitest';
import { CAMPOS_FICHA, camposCambiados, contador, cuerpoDeFicha, MAX_ANTECEDENTE, mensajeDeFicha } from './ficha';
import type { Antecedentes } from './tipos';

const BASE: Antecedentes = { alergias: 'Penicilina (sintético)', medicacion: '', antecedentes_medicos: '', observaciones: '' };

describe('camposCambiados', () => {
  it('sin cambios no informa ningún campo', () => {
    expect(camposCambiados(BASE, { ...BASE })).toEqual([]);
  });

  it('informa cada campo distinto, en el orden de la ficha', () => {
    expect(camposCambiados(BASE, { ...BASE, observaciones: 'Nota (sintético)', medicacion: 'Ibuprofeno 400 mg (sintético)' })).toEqual(['medicacion', 'observaciones']);
  });

  it('un espacio de más cuenta como cambio (se guarda tal cual)', () => {
    expect(camposCambiados(BASE, { ...BASE, alergias: 'Penicilina (sintético) ' })).toEqual(['alergias']);
  });
});

describe('cuerpoDeFicha', () => {
  it('arma los cuatro campos con la versión leída', () => {
    expect(cuerpoDeFicha({ ...BASE, medicacion: 'x' }, 2)).toEqual({
      alergias: 'Penicilina (sintético)',
      medicacion: 'x',
      antecedentes_medicos: '',
      observaciones: '',
      version: 2,
    });
  });

  it('una ficha nunca editada se guarda con versión 0', () => {
    expect(cuerpoDeFicha({ alergias: '', medicacion: '', antecedentes_medicos: '', observaciones: '' }, 0).version).toBe(0);
  });
});

describe('contador', () => {
  it('muestra caracteres sobre el máximo de 2000', () => {
    expect(MAX_ANTECEDENTE).toBe(2000);
    expect(contador('')).toBe('0/2000');
    expect(contador('a'.repeat(2000))).toBe('2000/2000');
  });
});

describe('CAMPOS_FICHA', () => {
  it('son los cuatro antecedentes con su etiqueta', () => {
    expect(CAMPOS_FICHA.map((c) => c.etiqueta)).toEqual(['Alergias', 'Medicación', 'Antecedentes médicos', 'Observaciones']);
  });
});

describe('mensajeDeFicha', () => {
  it('traduce cada rechazo a una frase que dice cómo seguir', () => {
    expect(mensajeDeFicha({ tipo: 'version_desactualizada' })).toBe('Alguien guardó la ficha mientras la editabas');
    expect(mensajeDeFicha({ tipo: 'acceso_vencido' })).toBe('Tu acceso para editar venció. Para editar, pedí un turno a recepción');
    expect(mensajeDeFicha({ tipo: 'desconocido' })).toBe('No pudimos guardar la ficha. Revisá tu conexión e intentá de nuevo');
    expect(mensajeDeFicha({ tipo: 'sin_permiso' })).toContain('no puede');
    expect(mensajeDeFicha({ tipo: 'validacion', mensaje: 'texto demasiado largo' })).toBe('texto demasiado largo');
  });
});
