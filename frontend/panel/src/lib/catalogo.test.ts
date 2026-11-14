import { describe, expect, it } from 'vitest';
import {
  agruparPorDia,
  formatoDuracion,
  formatoPrecio,
  horaCorta,
  mensajeDeCatalogo,
  textoDeImpacto,
  validarFranja,
  validarProfesional,
  validarSillon,
  validarTratamiento,
} from './catalogo';
import type { FranjaAdmin } from './tipos';

function franja(id: number, dia: number, inicio: string, fin: string, activo = true): FranjaAdmin {
  return { id, profesional_id: 1, dia_semana: dia, hora_inicio: inicio, hora_fin: fin, sillon_defecto_id: null, activo };
}

describe('agruparPorDia', () => {
  it('devuelve los siete días de lunes a domingo, con los vacíos presentes', () => {
    const dias = agruparPorDia([franja(1, 2, '09:00:00', '13:00:00')]);
    expect(dias.map((d) => d.nombre)).toEqual(['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']);
    expect(dias[2]?.franjas.map((f) => f.id)).toEqual([1]);
    expect(dias.filter((d) => d.franjas.length === 0)).toHaveLength(6);
  });

  it('ordena las franjas de un día por hora de inicio y no mezcla días', () => {
    const dias = agruparPorDia([franja(1, 0, '14:00:00', '18:00:00'), franja(2, 0, '09:00:00', '13:00:00'), franja(3, 4, '08:00:00', '12:00:00')]);
    expect(dias[0]?.franjas.map((f) => f.id)).toEqual([2, 1]);
    expect(dias[4]?.franjas.map((f) => f.id)).toEqual([3]);
  });

  it('sin franjas devuelve los siete días vacíos', () => {
    expect(agruparPorDia([]).every((d) => d.franjas.length === 0)).toBe(true);
  });
});

describe('formatos', () => {
  it('el precio se muestra en pesos con separador de miles y sin centavos en cero', () => {
    expect(formatoPrecio('18500.00')).toBe('$ 18.500');
    expect(formatoPrecio('0.00')).toBe('$ 0');
    expect(formatoPrecio('1234567.50')).toBe('$ 1.234.567,50');
  });

  it('la duración se muestra en minutos', () => {
    expect(formatoDuracion(45)).toBe('45 min');
    expect(formatoDuracion(5)).toBe('5 min');
  });

  it('la hora se acorta a HH:MM', () => {
    expect(horaCorta('09:00:00')).toBe('09:00');
    expect(horaCorta('13:05')).toBe('13:05');
  });
});

describe('validarTratamiento', () => {
  const ok = { nombre: ' Limpieza dental ', duracion: '45', precio: '18500' };

  it('un formulario correcto devuelve el valor normalizado', () => {
    const r = validarTratamiento(ok);
    expect(r.campos).toEqual({});
    expect(r.valor).toEqual({ nombre: 'Limpieza dental', duracion_minutos: 45, precio_base: '18500.00' });
  });

  it('acepta los límites 5 y 480 minutos', () => {
    expect(validarTratamiento({ ...ok, duracion: '5' }).campos).toEqual({});
    expect(validarTratamiento({ ...ok, duracion: '480' }).campos).toEqual({});
  });

  it.each(['7', '0', '-5', '485', '', '4.5', 'abc'])('rechaza la duración %s con el mensaje del rango', (duracion) => {
    const r = validarTratamiento({ ...ok, duracion });
    expect(r.campos['duracion']).toBe('La duración va de 5 a 480 minutos, en múltiplos de 5');
    expect(r.valor).toBeNull();
  });

  it('valida el precio: máximo de la columna, sin negativos y con dos decimales como máximo', () => {
    expect(validarTratamiento({ ...ok, precio: '99999999.99' }).campos).toEqual({});
    expect(validarTratamiento({ ...ok, precio: '0' }).campos).toEqual({});
    expect(validarTratamiento({ ...ok, precio: '12,5' }).valor?.precio_base).toBe('12.50');
    for (const precio of ['100000000', '-1', '1.005', '', 'gratis']) {
      expect(validarTratamiento({ ...ok, precio }).campos['precio']).toBeDefined();
    }
  });

  it('el nombre es obligatorio y admite hasta 120 caracteres', () => {
    expect(validarTratamiento({ ...ok, nombre: '   ' }).campos['nombre']).toBeDefined();
    expect(validarTratamiento({ ...ok, nombre: 'x'.repeat(121) }).campos['nombre']).toBeDefined();
    expect(validarTratamiento({ ...ok, nombre: 'x'.repeat(120) }).campos).toEqual({});
  });
});

describe('validarProfesional y validarSillon', () => {
  it('profesional: nombre y matrícula obligatorios; la especialidad puede ir vacía', () => {
    const r = validarProfesional({ nombre: 'Dr. Juan Ejemplo', matricula: ' MP-99002 ', especialidad: '' });
    expect(r.valor).toEqual({ nombre: 'Dr. Juan Ejemplo', matricula: 'MP-99002', especialidad: '' });
    expect(validarProfesional({ nombre: '', matricula: '', especialidad: '' }).campos).toEqual({
      nombre: 'Ingresá el nombre.',
      matricula: 'Ingresá la matrícula.',
    });
    expect(validarProfesional({ nombre: 'A', matricula: 'x'.repeat(41), especialidad: '' }).campos['matricula']).toBeDefined();
  });

  it('sillón: nombre de hasta 60 caracteres', () => {
    expect(validarSillon({ nombre: 'Sillón 1', estado: 'activo' }).valor).toEqual({ nombre: 'Sillón 1', estado: 'activo' });
    expect(validarSillon({ nombre: 'x'.repeat(61), estado: 'activo' }).campos['nombre']).toBeDefined();
    expect(validarSillon({ nombre: ' ', estado: 'activo' }).valor).toBeNull();
  });
});

describe('validarFranja', () => {
  it('el fin debe ser posterior al inicio', () => {
    expect(validarFranja({ inicio: '09:00', fin: '13:00' }).campos).toEqual({});
    expect(validarFranja({ inicio: '13:00', fin: '13:00' }).campos['fin']).toBe('La hora de fin tiene que ser posterior a la de inicio');
    expect(validarFranja({ inicio: '13:00', fin: '09:00' }).campos['fin']).toBeDefined();
  });

  it('pide las dos horas', () => {
    const r = validarFranja({ inicio: '', fin: '' });
    expect(r.campos['inicio']).toBeDefined();
    expect(r.campos['fin']).toBeDefined();
  });
});

describe('mensajeDeCatalogo', () => {
  it('en_uso explica el motivo y sugiere desactivar', () => {
    expect(mensajeDeCatalogo({ tipo: 'en_uso' }, 'tratamientos').mensaje).toBe(
      'No se puede borrar porque tiene turnos registrados. Podés desactivarlo para que no se ofrezca más.',
    );
  });

  it('duplicado se asigna al campo y dice qué hacer', () => {
    expect(mensajeDeCatalogo({ tipo: 'duplicado', campo: 'matricula' }, 'profesionales')).toEqual({
      campo: 'matricula',
      mensaje: 'Ya hay una profesional con esa matrícula',
    });
    expect(mensajeDeCatalogo({ tipo: 'duplicado', campo: 'nombre' }, 'sillones').campo).toBe('nombre');
  });

  it('franja_superpuesta nombra la franja que choca', () => {
    const r = mensajeDeCatalogo(
      { tipo: 'franja_superpuesta', franja: { id: 7, dia_semana: 0, hora_inicio: '09:00:00', hora_fin: '13:00:00' } },
      'disponibilidad',
    );
    expect(r.mensaje).toBe('Se superpone con la franja de 09:00 a 13:00 del lunes');
    expect(mensajeDeCatalogo({ tipo: 'franja_superpuesta', franja: null }, 'disponibilidad').mensaje).toBe(
      'Se superpone con otra franja activa de este día',
    );
  });

  it('no_reservable, validación del servidor, permisos y desconocido', () => {
    expect(mensajeDeCatalogo({ tipo: 'no_reservable', campo: 'tratamiento_id' }, 'tratamientos').mensaje).toMatch(/no se ofrece/i);
    expect(
      mensajeDeCatalogo({ tipo: 'validacion', campo: 'duracion_minutos', mensaje: 'duracion_minutos debe ser múltiplo de 5' }, 'tratamientos'),
    ).toEqual({ campo: 'duracion_minutos', mensaje: 'duracion_minutos debe ser múltiplo de 5' });
    expect(mensajeDeCatalogo({ tipo: 'sin_permiso' }, 'sillones').mensaje).toMatch(/permiso/);
    expect(mensajeDeCatalogo({ tipo: 'no_encontrado' }, 'sillones').mensaje).toMatch(/ya no existe/);
    expect(mensajeDeCatalogo({ tipo: 'desconocido' }, 'sillones').mensaje).toMatch(/Intentá de nuevo/);
  });
});

describe('textoDeImpacto', () => {
  it('cero, uno y varios turnos, siempre aclarando que no se cancelan', () => {
    expect(textoDeImpacto({ turnos_futuros: 0, primero: null }, 'en esta franja')).toBe('No hay turnos tomados en esta franja.');
    expect(textoDeImpacto({ turnos_futuros: 1, primero: '2026-11-16T14:30:00-03:00' }, 'en esta franja')).toBe(
      'Hay 1 turno tomado en esta franja. No se cancela: sigue en la agenda.',
    );
    expect(textoDeImpacto({ turnos_futuros: 3, primero: '2026-11-16T14:30:00-03:00' }, 'en esta franja')).toBe(
      'Hay 3 turnos tomados en esta franja. No se cancelan: siguen en la agenda.',
    );
  });

  it('si no se pudo consultar lo dice y aclara que los turnos no se cancelan', () => {
    expect(textoDeImpacto(null, 'en esta franja')).toBe(
      'No pudimos revisar los turnos tomados; los turnos existentes no se cancelan igual.',
    );
  });
});
