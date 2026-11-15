import { describe, expect, it } from 'vitest';
import {
  accionesDe,
  aplicarCobro,
  ETIQUETA_PRESUPUESTO,
  fechaCobroParaEnviar,
  mensajeDeErrorPresupuesto,
  normalizarMonto,
  pesosCompactos,
  restarMontos,
  validarCobro,
  validarLineas,
  validarMotivo,
} from './presupuestos';
import type { LineaNueva, Presupuesto } from './tipos';
import { presupuesto, pagoPresupuesto } from '../test/datos';

describe('accionesDe (RN-PG-05)', () => {
  it('cada estado ofrece solo las acciones válidas', () => {
    expect(accionesDe('borrador')).toEqual(['editar', 'presentar', 'anular']);
    expect(accionesDe('presentado')).toEqual(['aceptar', 'rechazar', 'anular']);
    expect(accionesDe('aceptado')).toEqual(['registrar_cobro', 'anular']);
    expect(accionesDe('rechazado')).toEqual([]);
    expect(accionesDe('anulado')).toEqual([]);
  });

  it('el estado se lee como texto', () => {
    expect(ETIQUETA_PRESUPUESTO).toEqual({ borrador: 'Borrador', presentado: 'Presentado', aceptado: 'Aceptado', rechazado: 'Rechazado', anulado: 'Anulado' });
  });
});

describe('validarLineas', () => {
  const linea = (sobre: Partial<LineaNueva> = {}): LineaNueva => ({ tratamiento_id: 3, cantidad: 1, pieza: null, cara: null, ...sobre });

  it('una línea válida y 50 líneas pasan', () => {
    expect(validarLineas([linea()])).toEqual({ general: null, porLinea: [null] });
    expect(validarLineas(Array.from({ length: 50 }, () => linea())).general).toBeNull();
  });

  it('0 líneas y 51 líneas son un error general', () => {
    expect(validarLineas([]).general).toBe('Agregá al menos una línea');
    expect(validarLineas(Array.from({ length: 51 }, () => linea())).general).toBe('Un presupuesto admite hasta 50 líneas');
  });

  it('la cantidad va de 1 a 99', () => {
    expect(validarLineas([linea({ cantidad: 0 })]).porLinea[0]).toBe('La cantidad va de 1 a 99');
    expect(validarLineas([linea({ cantidad: 100 })]).porLinea[0]).toBe('La cantidad va de 1 a 99');
    expect(validarLineas([linea({ cantidad: 99 })]).porLinea[0]).toBeNull();
    expect(validarLineas([linea({ cantidad: 1.5 })]).porLinea[0]).toBe('La cantidad va de 1 a 99');
  });

  it('la cara exige la pieza y la pieza tiene que ser FDI', () => {
    expect(validarLineas([linea({ cara: 'O' })]).porLinea[0]).toBe('La cara exige indicar la pieza');
    expect(validarLineas([linea({ pieza: 16, cara: 'O' })]).porLinea[0]).toBeNull();
    expect(validarLineas([linea({ pieza: 19 })]).porLinea[0]).toBe('La pieza no es válida (11 a 48 o 51 a 85)');
  });
});

describe('normalizarMonto', () => {
  it('acepta enteros, punto o coma y deja dos decimales', () => {
    expect(normalizarMonto('1000')).toBe('1000.00');
    expect(normalizarMonto('1000,5')).toBe('1000.50');
    expect(normalizarMonto(' 2500.25 ')).toBe('2500.25');
  });

  it('rechaza texto, negativos y más de dos decimales', () => {
    expect(normalizarMonto('')).toBeNull();
    expect(normalizarMonto('abc')).toBeNull();
    expect(normalizarMonto('-5')).toBeNull();
    expect(normalizarMonto('10.123')).toBeNull();
    expect(normalizarMonto('1.000,00')).toBeNull();
  });
});

describe('validarCobro', () => {
  it('un monto entre 0 y el saldo es válido', () => {
    expect(validarCobro({ monto: '1000', saldo: '1500.00', referencia: '' })).toEqual({ monto: null, referencia: null });
    expect(validarCobro({ monto: '1500.00', saldo: '1500.00', referencia: 'TRF-0001' }).monto).toBeNull();
  });

  it('0 y un monto mayor que el saldo son errores', () => {
    expect(validarCobro({ monto: '0', saldo: '1500.00', referencia: '' }).monto).toBe('El monto tiene que ser mayor que 0');
    expect(validarCobro({ monto: '1500.01', saldo: '1500.00', referencia: '' }).monto).toBe('El monto supera el saldo. El saldo actual es $ 1.500');
    expect(validarCobro({ monto: 'abc', saldo: '1500.00', referencia: '' }).monto).toBe('Escribí el monto con números, por ejemplo 1500 o 1500,50');
  });

  it('la referencia admite hasta 64 caracteres', () => {
    expect(validarCobro({ monto: '10', saldo: '1500.00', referencia: 'x'.repeat(64) }).referencia).toBeNull();
    expect(validarCobro({ monto: '10', saldo: '1500.00', referencia: 'x'.repeat(65) }).referencia).toBe('La referencia admite hasta 64 caracteres');
  });
});

describe('validarMotivo', () => {
  it('va de 3 a 300 caracteres sin contar espacios de los bordes', () => {
    expect(validarMotivo('ok')).toBe('Escribí al menos 3 caracteres');
    expect(validarMotivo('  ok  ')).toBe('Escribí al menos 3 caracteres');
    expect(validarMotivo('Error de carga (sintético)')).toBeNull();
    expect(validarMotivo('x'.repeat(300))).toBeNull();
    expect(validarMotivo('x'.repeat(301))).toBe('El motivo admite hasta 300 caracteres');
  });
});

describe('mensajeDeErrorPresupuesto', () => {
  it('traduce cada rechazo de RN-PG-05 y RN-PG-06 a qué pasó y cómo seguir', () => {
    expect(mensajeDeErrorPresupuesto({ tipo: 'obra_social_inactiva' })).toBe('Esa obra social ya no está activa. Elegí otra o «Sin obra social»');
    expect(mensajeDeErrorPresupuesto({ tipo: 'presupuesto_no_editable' })).toBe('Este presupuesto ya fue presentado y no se puede editar');
    expect(mensajeDeErrorPresupuesto({ tipo: 'transicion_invalida' })).toBe('El presupuesto cambió de estado mientras lo mirabas');
    expect(mensajeDeErrorPresupuesto({ tipo: 'presupuesto_con_pagos' })).toBe('No se puede anular un presupuesto con cobros registrados. Anulá antes los cobros');
    expect(mensajeDeErrorPresupuesto({ tipo: 'presupuesto_no_aceptado' })).toBe('Solo se pueden registrar cobros en un presupuesto aceptado');
    expect(mensajeDeErrorPresupuesto({ tipo: 'monto_excede_saldo', saldo: '500.00' })).toBe('El monto supera el saldo. El saldo actual es $ 500');
    expect(mensajeDeErrorPresupuesto({ tipo: 'referencia_duplicada' })).toBe('Ya hay un cobro registrado con esa referencia');
    expect(mensajeDeErrorPresupuesto({ tipo: 'caja_cerrada' })).toBe('La caja de ese día está cerrada. Un admin tiene que anular el cierre para registrar este cobro');
  });

  it('el saldo ausente, la validación y la falla de red tienen su frase', () => {
    expect(mensajeDeErrorPresupuesto({ tipo: 'monto_excede_saldo', saldo: null })).toBe('El monto supera el saldo.');
    expect(mensajeDeErrorPresupuesto({ tipo: 'validacion', mensaje: 'monto inválido' })).toBe('monto inválido');
    expect(mensajeDeErrorPresupuesto({ tipo: 'desconocido' })).toContain('Revisá tu conexión');
    expect(mensajeDeErrorPresupuesto({ tipo: 'sin_permiso' })).toContain('no puede');
  });
});

describe('fechaCobroParaEnviar', () => {
  it('hoy se omite (el servidor usa su reloj)', () => {
    expect(fechaCobroParaEnviar('2031-11-18', '2031-11-18')).toBeUndefined();
  });

  it('un día pasado va como las 12:00 de la clínica con el offset explícito', () => {
    expect(fechaCobroParaEnviar('2031-11-18', '2031-11-17')).toBe('2031-11-17T12:00:00-03:00');
    expect(fechaCobroParaEnviar('2031-11-18', '2031-01-02')).toBe('2031-01-02T12:00:00-03:00');
  });

  it('un día futuro es un error de programación: no se puede elegir', () => {
    expect(() => fechaCobroParaEnviar('2031-11-18', '2031-11-19')).toThrow(RangeError);
  });
});

describe('pesosCompactos', () => {
  it('sin decimales cuando son cero y con separador de miles', () => {
    expect(pesosCompactos('2500.00')).toBe('$ 2.500');
    expect(pesosCompactos('0.00')).toBe('$ 0');
    expect(pesosCompactos('500.00')).toBe('$ 500');
  });

  it('con decimales cuando los hay y el importe máximo completo', () => {
    expect(pesosCompactos('1500.50')).toBe('$ 1.500,50');
    expect(pesosCompactos('9999999999.99')).toBe('$ 9.999.999.999,99');
  });
});

describe('restarMontos y aplicarCobro', () => {
  it('resta importes en centavos sin errores de punto flotante', () => {
    expect(restarMontos('2500.00', '1000.00')).toBe('1500.00');
    expect(restarMontos('0.30', '0.10')).toBe('0.20');
  });

  it('un cobro registrado se suma a la lista y actualiza el total pagado y el saldo', () => {
    const base: Presupuesto = presupuesto({ pagos: [], total_pagado: '0.00', saldo: '2500.00' });
    const cobro = pagoPresupuesto({ id: 5, monto: '1000.00' });
    const nuevo = aplicarCobro(base, { pago: cobro, total_pagado: '1000.00', saldo: '1500.00' });
    expect(nuevo.pagos).toEqual([cobro]);
    expect(nuevo.total_pagado).toBe('1000.00');
    expect(nuevo.saldo).toBe('1500.00');
  });

  it('un cobro anulado reemplaza al registrado con el mismo id y no se duplica', () => {
    const base = presupuesto({ pagos: [pagoPresupuesto({ id: 5 }), pagoPresupuesto({ id: 6, monto: '500.00' })], total_pagado: '1500.00', saldo: '1000.00' });
    const anulado = pagoPresupuesto({ id: 5, estado: 'anulado', anulado_motivo: 'Monto equivocado (sintético)' });
    const nuevo = aplicarCobro(base, { pago: anulado, total_pagado: '500.00', saldo: '2000.00' });
    expect(nuevo.pagos.map((p) => [p.id, p.estado])).toEqual([[5, 'anulado'], [6, 'registrado']]);
    expect(nuevo.saldo).toBe('2000.00');
  });
});
