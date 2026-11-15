import { describe, expect, it } from 'vitest';
import { mensajeDeErrorPaciente, normalizarDni, separarContacto, validarPaciente, type FormularioPaciente } from './pacientes';

const VALIDO: FormularioPaciente = {
  nombre: 'Mateo',
  apellido: 'Prueba',
  dni: '99000002',
  telefono: '+5491100000002',
  email: '',
  obraSocialId: '',
  numeroAfiliado: '',
};

describe('normalizarDni', () => {
  it('quita puntos y espacios', () => {
    expect(normalizarDni('99.000.001')).toBe('99000001');
    expect(normalizarDni(' 99 000 001 ')).toBe('99000001');
  });
});

describe('validarPaciente', () => {
  it('un formulario válido arma los datos con null para lo opcional vacío', () => {
    const r = validarPaciente(VALIDO);
    expect(r.errores).toEqual({});
    expect(r.datos).toEqual({
      nombre: 'Mateo',
      apellido: 'Prueba',
      dni: '99000002',
      telefono: '+5491100000002',
      email: null,
      obra_social_id: null,
      numero_afiliado: null,
    });
  });

  it('normaliza el DNI con puntos, recorta espacios y manda la obra social elegida', () => {
    const r = validarPaciente({ ...VALIDO, nombre: '  Mateo ', dni: '99.000.002', email: 'mateo@ejemplo.test', obraSocialId: '2', numeroAfiliado: ' SM-0001 ' });
    expect(r.datos).toMatchObject({ nombre: 'Mateo', dni: '99000002', email: 'mateo@ejemplo.test', obra_social_id: 2, numero_afiliado: 'SM-0001' });
  });

  it('un DNI con letras o de largo incorrecto da el error del campo', () => {
    expect(validarPaciente({ ...VALIDO, dni: '9900001a' }).errores.dni).toBe('El DNI tiene 7 u 8 números, sin puntos');
    expect(validarPaciente({ ...VALIDO, dni: '123456' }).errores.dni).toBe('El DNI tiene 7 u 8 números, sin puntos');
    expect(validarPaciente({ ...VALIDO, dni: '123456789' }).datos).toBeNull();
  });

  it('un teléfono sin código de país da la ayuda con el ejemplo', () => {
    const r = validarPaciente({ ...VALIDO, telefono: '1100000002' });
    expect(r.errores.telefono).toBe('Escribí el teléfono con código de país, por ejemplo +5491100000002');
    expect(validarPaciente({ ...VALIDO, telefono: '+54 911 0000 0002' }).errores.telefono).toBeDefined();
    expect(validarPaciente({ ...VALIDO, telefono: '+5491100000002' }).errores.telefono).toBeUndefined();
  });

  it('nombre, apellido, email y afiliado respetan los límites', () => {
    expect(validarPaciente({ ...VALIDO, nombre: '   ' }).errores.nombre).toBeDefined();
    expect(validarPaciente({ ...VALIDO, apellido: 'a'.repeat(101) }).errores.apellido).toBeDefined();
    expect(validarPaciente({ ...VALIDO, apellido: 'a'.repeat(100) }).errores.apellido).toBeUndefined();
    expect(validarPaciente({ ...VALIDO, email: 'sin-arroba' }).errores.email).toBe('El email no parece válido');
    expect(validarPaciente({ ...VALIDO, email: `${'a'.repeat(115)}@x.test` }).errores.email).toBeDefined();
    expect(validarPaciente({ ...VALIDO, numeroAfiliado: 'x'.repeat(41) }).errores.numeroAfiliado).toBeDefined();
    expect(validarPaciente({ ...VALIDO, numeroAfiliado: 'x'.repeat(40) }).errores.numeroAfiliado).toBeUndefined();
  });

  it('con varios errores no arma datos y los informa todos', () => {
    const r = validarPaciente({ ...VALIDO, dni: '9900001a', telefono: '1100000002' });
    expect(Object.keys(r.errores).sort()).toEqual(['dni', 'telefono']);
    expect(r.datos).toBeNull();
  });
});

describe('separarContacto', () => {
  it('la última palabra es el apellido', () => {
    expect(separarContacto('Carlos Sintético')).toEqual({ nombre: 'Carlos', apellido: 'Sintético' });
    expect(separarContacto('Ana María Pérez')).toEqual({ nombre: 'Ana María', apellido: 'Pérez' });
  });

  it('una sola palabra queda como nombre y los espacios dobles se juntan', () => {
    expect(separarContacto('Carlos')).toEqual({ nombre: 'Carlos', apellido: '' });
    expect(separarContacto('  Carlos   Sintético ')).toEqual({ nombre: 'Carlos', apellido: 'Sintético' });
    expect(separarContacto(null)).toEqual({ nombre: '', apellido: '' });
  });
});

describe('mensajeDeErrorPaciente', () => {
  it('traduce el DNI repetido y la obra social inactiva', () => {
    expect(mensajeDeErrorPaciente({ tipo: 'dni_duplicado' })).toBe('Ya hay un paciente con ese DNI');
    expect(mensajeDeErrorPaciente({ tipo: 'obra_social_inactiva' })).toBe('Esa obra social ya no está activa. Elegí otra o «Sin obra social»');
  });

  it('el resto da una frase que dice cómo seguir', () => {
    expect(mensajeDeErrorPaciente({ tipo: 'sin_permiso' })).toContain('no puede');
    expect(mensajeDeErrorPaciente({ tipo: 'validacion', mensaje: 'email inválido' })).toBe('email inválido');
    expect(mensajeDeErrorPaciente({ tipo: 'desconocido' })).toContain('Revisá tu conexión');
  });
});
