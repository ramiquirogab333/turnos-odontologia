import { describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorDeRespuesta } from './api';
import { Sesion } from './sesion';

/** Contratos de C-16 (odontograma, presupuestos y cobros). Datos 100 % sintéticos (R19). */

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function montar(fetchFn: typeof fetch) {
  const sesion = new Sesion({ fetchFn, candados: null, canal: null });
  sesion.fijarToken('ACCESS-1');
  return crearApi(sesion, fetchFn);
}

const urlDe = (llamada: Parameters<typeof fetch> | undefined): string => {
  const u = llamada?.[0];
  if (u === undefined) return '';
  return typeof u === 'string' ? u : u instanceof URL ? u.href : u.url;
};
const metodoDe = (llamada: Parameters<typeof fetch> | undefined): string => llamada?.[1]?.method ?? 'GET';
const cuerpoDe = (llamada: Parameters<typeof fetch> | undefined): unknown => {
  const c = llamada?.[1]?.body;
  return typeof c === 'string' ? (JSON.parse(c) as unknown) : undefined;
};

const LINEA = {
  id: 1,
  orden: 1,
  tratamiento: { id: 3, nombre: 'Limpieza dental' },
  pieza: null,
  cara: null,
  cantidad: 1,
  precio_unitario: '25000.00',
  cobertura_porcentaje: '90.00',
  arancel_diferencial: '0.00',
  codigo_prestacion: null,
  importe_bruto: '25000.00',
  importe_cobertura: '22500.00',
  importe_diferencial: '0.00',
  importe_paciente: '2500.00',
  sin_cobertura: false,
};
const PAGO = {
  id: 5,
  presupuesto_id: 9,
  medio: 'transferencia',
  monto: '1000.00',
  estado: 'registrado',
  fecha_cobro: '2031-11-18T12:00:00-03:00',
  referencia: 'TRF-0001',
  registrado_por: 3,
  anulado_en: null,
  anulado_motivo: null,
};
const BASE = {
  id: 9,
  paciente_id: 7,
  obra_social: { id: 2, nombre: 'Swiss Medical' },
  estado: 'aceptado',
  subtotal: '25000.00',
  cobertura_total: '22500.00',
  diferencial_total: '0.00',
  total_paciente: '2500.00',
  notas: '',
  presentado_en: null,
  resuelto_en: null,
  anulado_en: null,
  anulado_motivo: null,
  created_at: '2031-11-18T09:00:00-03:00',
  lineas: [LINEA],
};
const COMPLETO = { ...BASE, pagos: [PAGO], total_pagado: '1000.00', saldo: '1500.00' };
const REGISTRO = {
  id: 4,
  pieza: 16,
  cara: 'O',
  estado: 'caries',
  nota: null,
  registrado_por: 3,
  registrado_en: '2031-11-18T09:00:00-03:00',
};

describe('odontograma', () => {
  it('odontograma() devuelve el vigente y valida las piezas', async () => {
    const vigente = { paciente_id: 7, piezas: [{ pieza: 16, estado_pieza: null, caras: { O: 'caries' } }] };
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(vigente))
      .mockResolvedValueOnce(json({ paciente_id: 7, piezas: [{ pieza: 'x' }] }));
    const api = montar(fetchFn);
    expect((await api.odontograma(7)).piezas[0]?.caras['O']).toBe('caries');
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/odontograma');
    await expect(api.odontograma(7)).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('historialOdontograma pasa el cursor y el límite', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockImplementation(() => Promise.resolve(json({ registros: [REGISTRO], siguiente_antes_de_id: 4 })));
    const api = montar(fetchFn);
    expect((await api.historialOdontograma(7, null)).siguiente_antes_de_id).toBe(4);
    await api.historialOdontograma(7, 4);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/odontograma/historial?limite=50');
    expect(urlDe(fetchFn.mock.calls[1])).toBe('/api/panel/pacientes/7/odontograma/historial?limite=50&antes_de_id=4');
  });

  it('registrarOdontograma envía el lote en un solo pedido y traduce el 403 y el 422', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ registros: [REGISTRO] }, 201))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'acceso_clinico_vencido' }, 403))
      .mockResolvedValueOnce(json({ detail: [{ msg: 'Value error, pieza FDI, cara o estado inválidos' }] }, 422));
    const api = montar(fetchFn);
    const lote = [{ pieza: 16, cara: 'O', estado: 'caries', nota: null }] as const;
    const ok = await api.registrarOdontograma(7, lote);
    expect(ok).toMatchObject({ ok: true, valor: [{ id: 4 }] });
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('POST');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ registros: lote });
    expect(await api.registrarOdontograma(7, lote)).toEqual({ ok: false, error: { tipo: 'acceso_vencido' } });
    expect(await api.registrarOdontograma(7, lote)).toEqual({
      ok: false,
      error: { tipo: 'validacion', mensaje: 'pieza FDI, cara o estado inválidos' },
    });
  });
});

describe('presupuestos', () => {
  it('presupuestos() distingue la vista completa de la clínica por `pagos`', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockResolvedValueOnce(json([COMPLETO])).mockResolvedValueOnce(json([BASE]));
    const api = montar(fetchFn);
    const [completo] = await api.presupuestos(7);
    expect(completo !== undefined && 'pagos' in completo && completo.saldo).toBe('1500.00');
    const [clinico] = await api.presupuestos(7);
    expect(clinico !== undefined && 'pagos' in clinico).toBe(false);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/presupuestos');
  });

  it('un presupuesto con importe malformado es una respuesta inválida', async () => {
    const api = montar(vi.fn<typeof fetch>().mockImplementation(() => Promise.resolve(json([{ ...BASE, total_paciente: 2500 }]))));
    await expect(api.presupuestos(7)).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('crearPresupuesto omite obra_social_id para usar la del paciente y lo envía cuando se elige', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockImplementation(() => Promise.resolve(json({ ...COMPLETO, estado: 'borrador' }, 201)));
    const api = montar(fetchFn);
    const linea = { tratamiento_id: 3, cantidad: 1, pieza: null, cara: null } as const;
    await api.crearPresupuesto(7, { lineas: [linea], notas: '' });
    await api.crearPresupuesto(7, { lineas: [linea], notas: 'n', obra_social_id: null });
    await api.crearPresupuesto(7, { lineas: [linea], notas: '', obra_social_id: 2 });
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ lineas: [linea], notas: '' });
    expect(cuerpoDe(fetchFn.mock.calls[1])).toEqual({ lineas: [linea], notas: 'n', obra_social_id: null });
    expect(cuerpoDe(fetchFn.mock.calls[2])).toEqual({ lineas: [linea], notas: '', obra_social_id: 2 });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/presupuestos');
  });

  it('editarPresupuesto usa PUT y traduce obra_social_inactiva y presupuesto_no_editable', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'obra_social_inactiva' }, 422))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'presupuesto_no_editable' }, 409));
    const api = montar(fetchFn);
    const datos = { lineas: [{ tratamiento_id: 3, cantidad: 1, pieza: null, cara: null }], notas: '' } as const;
    expect(await api.editarPresupuesto(7, 9, datos)).toEqual({ ok: false, error: { tipo: 'obra_social_inactiva' } });
    expect(await api.editarPresupuesto(7, 9, datos)).toEqual({ ok: false, error: { tipo: 'presupuesto_no_editable' } });
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('PUT');
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/presupuestos/9');
  });

  it('las transiciones no llevan cuerpo y anular lleva el motivo', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ ...COMPLETO, estado: 'presentado' }))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'transicion_invalida' }, 409))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'presupuesto_con_pagos' }, 409));
    const api = montar(fetchFn);
    expect(await api.transicionarPresupuesto(7, 9, 'presentar')).toMatchObject({ ok: true, valor: { estado: 'presentado' } });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/presupuestos/9/presentar');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toBeUndefined();
    expect(await api.transicionarPresupuesto(7, 9, 'aceptar')).toEqual({ ok: false, error: { tipo: 'transicion_invalida' } });
    expect(await api.anularPresupuesto(7, 9, 'Error de carga (sintético)')).toEqual({ ok: false, error: { tipo: 'presupuesto_con_pagos' } });
    expect(urlDe(fetchFn.mock.calls[2])).toBe('/api/panel/pacientes/7/presupuestos/9/anular');
    expect(cuerpoDe(fetchFn.mock.calls[2])).toEqual({ motivo: 'Error de carga (sintético)' });
  });
});

describe('cobros', () => {
  const REGISTRADO = { pago: PAGO, total_pagado: '1000.00', saldo: '1500.00' };

  it('registrarCobro envía el monto como texto y omite la fecha de hoy', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockImplementation(() => Promise.resolve(json(REGISTRADO, 201)));
    const api = montar(fetchFn);
    await api.registrarCobro(7, 9, { medio: 'transferencia', monto: '1000.00', referencia: 'TRF-0001' });
    await api.registrarCobro(7, 9, { medio: 'mercadopago', monto: '500.00', fecha_cobro: '2031-11-17T12:00:00-03:00', referencia: null });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/presupuestos/9/pagos');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ medio: 'transferencia', monto: '1000.00', referencia: 'TRF-0001' });
    expect(cuerpoDe(fetchFn.mock.calls[1])).toEqual({ medio: 'mercadopago', monto: '500.00', fecha_cobro: '2031-11-17T12:00:00-03:00' });
  });

  it('monto_excede_saldo conserva el saldo; caja_cerrada y referencia_duplicada son tipados', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'monto_excede_saldo', saldo: '500.00' }, 409))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'caja_cerrada' }, 409))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'referencia_duplicada' }, 409))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'presupuesto_no_aceptado' }, 409));
    const api = montar(fetchFn);
    const datos = { medio: 'transferencia', monto: '1500.00', referencia: null } as const;
    expect(await api.registrarCobro(7, 9, datos)).toEqual({ ok: false, error: { tipo: 'monto_excede_saldo', saldo: '500.00' } });
    expect(await api.registrarCobro(7, 9, datos)).toEqual({ ok: false, error: { tipo: 'caja_cerrada' } });
    expect(await api.registrarCobro(7, 9, datos)).toEqual({ ok: false, error: { tipo: 'referencia_duplicada' } });
    expect(await api.registrarCobro(7, 9, datos)).toEqual({ ok: false, error: { tipo: 'presupuesto_no_aceptado' } });
  });

  it('anularCobro envía el motivo y devuelve el saldo nuevo', async () => {
    const anulado = { ...PAGO, estado: 'anulado', anulado_en: '2031-11-18T13:00:00-03:00', anulado_motivo: 'Monto equivocado (sintético)' };
    const fetchFn = vi.fn<typeof fetch>().mockResolvedValue(json({ pago: anulado, total_pagado: '0.00', saldo: '2500.00' }));
    const r = await montar(fetchFn).anularCobro(7, 9, 5, 'Monto equivocado (sintético)');
    expect(r).toMatchObject({ ok: true, valor: { saldo: '2500.00' } });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/presupuestos/9/pagos/5/anular');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ motivo: 'Monto equivocado (sintético)' });
  });
});

describe('agenda', () => {
  it('cada turno trae paciente_id (número o null) y se rechaza otro tipo', async () => {
    const turno = {
      id: 11,
      inicio: '2031-11-18T09:00:00-03:00',
      fin: '2031-11-18T09:30:00-03:00',
      estado: 'reservado',
      bloquea_agenda: true,
      origen: 'web',
      profesional: { id: 1, nombre: 'Dra. Ana Ficticia' },
      sillon: { id: 2, nombre: 'Sillón 1' },
      tratamiento: { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 },
      paciente_id: 7,
      paciente_nombre: 'Lucía Ejemplo',
      paciente_telefono: null,
      sena: null,
      vence_en: null,
      acciones: [],
      calendario: { estado: 'sin_evento', conflicto_abierto: false },
    };
    const cuerpo = (t: unknown) => ({ vista: 'dia', desde: '2031-11-18', hasta: '2031-11-18', turnos: [t], ocupados_google: [] });
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(cuerpo(turno)))
      .mockResolvedValueOnce(json(cuerpo({ ...turno, paciente_id: null })))
      .mockResolvedValueOnce(json(cuerpo({ ...turno, paciente_id: 'siete' })));
    const api = montar(fetchFn);
    const consulta = { vista: 'dia', fecha: '2031-11-18', profesionalId: null, sillonId: null } as const;
    expect((await api.agenda(consulta)).turnos[0]?.paciente_id).toBe(7);
    expect((await api.agenda(consulta)).turnos[0]?.paciente_id).toBeNull();
    await expect(api.agenda(consulta)).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });
});
