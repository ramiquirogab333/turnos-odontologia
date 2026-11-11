import { describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorApiPanel, ErrorDeRespuesta } from './api';
import { Sesion } from './sesion';
import type { Consulta } from './tipos';

/** Contratos de C-12 (caja, pendientes, cierres, indicadores, pacientes y deshacer atendido). */

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function servidor(responder: () => Response) {
  return vi.fn<typeof fetch>(() => Promise.resolve(responder()));
}

type ApiPanel = ReturnType<typeof crearApi>;

function api(fetchFn: typeof fetch): ApiPanel {
  const sesion = new Sesion({ fetchFn, candados: null, canal: null });
  sesion.fijarToken('ACCESS-1');
  return crearApi(sesion, fetchFn);
}

const urlDe = (llamada: Parameters<typeof fetch> | undefined): string => {
  const u = llamada?.[0];
  if (u === undefined) return '';
  return typeof u === 'string' ? u : u instanceof URL ? u.href : u.url;
};

const bearer = (init?: RequestInit): string | null => new Headers(init?.headers).get('Authorization');

const cuerpoDe = (llamada: Parameters<typeof fetch> | undefined): unknown => {
  const cuerpo = llamada?.[1]?.body;
  return typeof cuerpo === 'string' ? (JSON.parse(cuerpo) as unknown) : undefined;
};

const CAJA = {
  dia: '2031-11-18',
  estado: 'abierto',
  cierre_id: null,
  lineas: [{ concepto: 'sena', medio: 'mercadopago', cantidad: 1, total: '3000.00' }],
  total_ingresos: '3000.00',
  total_egresos: '0.00',
  total_neto: '3000.00',
  senas_retenidas: { cantidad: 0, total: '0.00' },
  movimientos: [
    {
      concepto: 'sena',
      medio: 'mercadopago',
      importe: '3000.00',
      hora: '2031-11-18T10:00:00-03:00',
      referencia: null,
      turno_id: 4,
      presupuesto_id: null,
    },
  ],
};
const PENDIENTE = {
  tipo: 'revision',
  id: 5,
  pago_id: 5,
  turno_id: 9,
  estado_turno: 'en_espera',
  medio: 'mercadopago',
  importe: '2000.00',
  importe_a_verificar: false,
  mp_payment_id: 'MP-SINT-1',
  pendiente_desde: '2031-11-18T10:00:00-03:00',
};
const DEVOLUCION = {
  id: 5,
  tipo: 'sena',
  pago_id: 5,
  turno_id: 9,
  importe: '3000.00',
  reembolsado_en: '2031-11-18T10:00:00-03:00',
  referencia: 'DEV-SINT-0001',
};
const RECHAZO = { pago_id: 5, turno_id: 9, estado_pago: 'a_reembolsar', estado_turno: 'en_espera', importe: '2000.00' };
const ACREDITACION = { pago_id: 5, turno_id: 9, efecto: 'acreditado', estado_pago: 'acreditado', estado_turno: 'reservado' };
const CIERRE = {
  id: 3,
  dia: '2031-11-17',
  estado: 'vigente',
  total_ingresos: '3000.00',
  total_egresos: '0.00',
  total_neto: '3000.00',
  observaciones: null,
  cerrado_por_nombre: 'Rita Recepción',
  cerrado_en: '2031-11-18T00:20:00-03:00',
  anulado_en: null,
  anulado_motivo: null,
  lineas: CAJA.lineas,
  cuadra: true,
  diferencias: [],
};
const OCUPACION = {
  desde: '2031-11-18',
  hasta: '2031-11-18',
  sillones: [
    {
      sillon_id: 2,
      nombre: 'Sillón 1',
      estado: 'activo',
      dias: [{ dia: '2031-11-18', minutos_ocupados: 90, minutos_atencion: 240, porcentaje: '37.50', turnos: 3, minutos_perdidos: 0 }],
    },
  ],
};
const AUSENTISMO = {
  desde: '2031-11-18',
  hasta: '2031-11-18',
  atendidos: 3,
  ausentes: 1,
  tasa: '25.00',
  sin_marcar: 0,
  por_profesional: [{ profesional_id: 1, nombre: 'Dra. Ana Ficticia', atendidos: 3, ausentes: 1, tasa: '25.00', sin_marcar: 0 }],
  recupero: { senas_retenidas: 1, importe_retenido: '3000.00', porcentaje: '100.00' },
};
const LISTADO = {
  total: 1,
  pagina: 1,
  por_pagina: 20,
  pacientes: [
    {
      id: 8,
      nombre: 'Lucía',
      apellido: 'Ejemplo',
      dni: '30111222',
      telefono: '+5491144445555',
      obra_social: null,
      atendidos: 2,
      ausentes: 1,
      ultimo_turno: '2031-11-10T09:00:00-03:00',
    },
  ],
};
const TURNO = {
  id: 11,
  inicio: '2031-11-18T09:00:00-03:00',
  fin: '2031-11-18T09:30:00-03:00',
  estado: 'atendido',
  bloquea_agenda: true,
  origen: 'web',
  profesional: { id: 1, nombre: 'Dra. Ana Ficticia' },
  sillon: { id: 2, nombre: 'Sillón 1' },
  tratamiento: { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 },
  paciente_nombre: 'Carlos Sintético',
  paciente_telefono: null,
  sena: null,
  vence_en: null,
  acciones: ['deshacer_atendido'],
};
const CONSULTA: Consulta = { vista: 'dia', fecha: '2031-11-18', profesionalId: null, sillonId: null };

describe('crearApi: lecturas de la caja, los indicadores y los pacientes', () => {
  it.each([
    ['caja', (a: ApiPanel) => a.caja('2031-11-18'), '/api/panel/caja?dia=2031-11-18', CAJA],
    ['pendientes', (a: ApiPanel) => a.pendientes(), '/api/panel/caja/pendientes', [PENDIENTE]],
    ['cierre', (a: ApiPanel) => a.cierre(3), '/api/panel/caja/cierres/3', CIERRE],
    ['ocupacion', (a: ApiPanel) => a.ocupacion('2031-11-18', '2031-11-18'), '/api/panel/ocupacion?desde=2031-11-18&hasta=2031-11-18', OCUPACION],
    ['ausentismo', (a: ApiPanel) => a.ausentismo('2031-11-12', '2031-11-18'), '/api/panel/ausentismo?desde=2031-11-12&hasta=2031-11-18', AUSENTISMO],
  ])('%s: arma la URL y devuelve el contrato validado', async (_nombre, llamar, url, cuerpo) => {
    const fetchFn = servidor(() => json(cuerpo));
    expect(await llamar(api(fetchFn))).toEqual(cuerpo);
    expect(urlDe(fetchFn.mock.calls[0])).toBe(url);
    expect(bearer(fetchFn.mock.calls[0]?.[1])).toBe('Bearer ACCESS-1');
  });

  it('listarPacientes manda solo los filtros elegidos', async () => {
    const fetchFn = servidor(() => json(LISTADO));
    const a = api(fetchFn);
    await a.listarPacientes({ q: null, pagina: 1, porPagina: 20, conAusencias: false });
    await a.listarPacientes({ q: 'lucia', pagina: 2, porPagina: 20, conAusencias: true });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/listado?pagina=1&por_pagina=20');
    expect(urlDe(fetchFn.mock.calls[1])).toBe('/api/panel/pacientes/listado?q=lucia&pagina=2&por_pagina=20&con_ausencias=true');
  });

  it('listarPacientes devuelve el listado validado', async () => {
    const r = await api(servidor(() => json(LISTADO))).listarPacientes({ q: null, pagina: 1, porPagina: 20, conAusencias: false });
    expect(r.pacientes[0]?.apellido).toBe('Ejemplo');
    expect(r.total).toBe(1);
  });

  it.each([
    ['caja', { ...CAJA, estado: 'quizas' }],
    ['caja', { ...CAJA, total_ingresos: 3000 }],
    ['pendientes', [{ ...PENDIENTE, tipo: 'otro' }]],
    ['cierre', { ...CIERRE, cuadra: 'si' }],
    ['ocupacion', { ...OCUPACION, sillones: [{ nombre: 'sin id' }] }],
    ['ausentismo', { ...AUSENTISMO, recupero: null }],
    ['listarPacientes', { ...LISTADO, pacientes: [{ id: 1 }] }],
  ] as const)('%s: una respuesta fuera de contrato se descarta', async (metodo, cuerpo) => {
    const a = api(servidor(() => json(cuerpo)));
    const llamada =
      metodo === 'caja'
        ? a.caja('2031-11-18')
        : metodo === 'pendientes'
          ? a.pendientes()
          : metodo === 'cierre'
            ? a.cierre(3)
            : metodo === 'ocupacion'
              ? a.ocupacion('2031-11-18', '2031-11-18')
              : metodo === 'ausentismo'
                ? a.ausentismo('2031-11-18', '2031-11-18')
                : a.listarPacientes({ q: null, pagina: 1, porPagina: 20, conAusencias: false });
    await expect(llamada).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('un rechazo con motivo en una lectura llega como ErrorApiPanel con su motivo', async () => {
    const fetchFn = servidor(() => json({ detail: 'No encontramos ese cierre', motivo: 'cierre_inexistente' }, 404));
    await expect(api(fetchFn).cierre(99)).rejects.toMatchObject({ status: 404, motivo: 'cierre_inexistente' });
    await expect(api(fetchFn).cierre(99)).rejects.toBeInstanceOf(ErrorApiPanel);
  });
});

describe('crearApi: escrituras de la caja', () => {
  it.each([
    ['rechazarRevision', (a: ApiPanel) => a.rechazarRevision(5), '/api/panel/caja/revisiones/5/rechazar', undefined, RECHAZO],
    ['acreditarRevision', (a: ApiPanel) => a.acreditarRevision(5), '/api/admin/pagos-sena/5/acreditar', undefined, ACREDITACION],
    [
      'registrarDevolucion',
      (a: ApiPanel) => a.registrarDevolucion(5, 'DEV-SINT-0001'),
      '/api/panel/caja/devoluciones/senas/5',
      { referencia: 'DEV-SINT-0001' },
      DEVOLUCION,
    ],
    [
      'registrarDevolucionExcedente',
      (a: ApiPanel) => a.registrarDevolucionExcedente(6, 'DEV-SINT-0002'),
      '/api/panel/caja/devoluciones/excedentes/6',
      { referencia: 'DEV-SINT-0002' },
      { ...DEVOLUCION, tipo: 'excedente_mp' },
    ],
    ['cerrarCaja', (a: ApiPanel) => a.cerrarCaja('2031-11-17'), '/api/panel/caja/cierres', { dia: '2031-11-17' }, CIERRE],
    [
      'anularCierre',
      (a: ApiPanel) => a.anularCierre(3, 'Cargamos mal un cobro'),
      '/api/panel/caja/cierres/3/anular',
      { motivo: 'Cargamos mal un cobro' },
      CIERRE,
    ],
  ])('%s: POST con la URL y el cuerpo correctos', async (_nombre, llamar, url, cuerpo, respuesta) => {
    const fetchFn = servidor(() => json(respuesta));
    expect(await llamar(api(fetchFn))).toEqual({ ok: true, valor: respuesta });
    expect(urlDe(fetchFn.mock.calls[0])).toBe(url);
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual(cuerpo);
  });

  it.each([
    [409, { detail: 'x', motivo: 'caja_cerrada', dia: '2031-11-17' }, { tipo: 'caja_cerrada', dia: '2031-11-17' }],
    [
      409,
      { detail: 'x', motivo: 'dia_no_terminado', cerrable_desde: '2031-11-19T00:15:00-03:00' },
      { tipo: 'dia_no_terminado', cerrableDesde: '2031-11-19T00:15:00-03:00' },
    ],
    [409, { detail: 'x', motivo: 'dia_ya_cerrado', cierre_id: 3 }, { tipo: 'dia_ya_cerrado' }],
    [409, { detail: 'x', motivo: 'no_esta_en_revision' }, { tipo: 'estado_cambiado' }],
    [409, { detail: 'x', motivo: 'no_es_devolucion_pendiente' }, { tipo: 'estado_cambiado' }],
    [404, { detail: 'x', motivo: 'pago_inexistente' }, { tipo: 'no_encontrado' }],
    [403, { detail: 'x' }, { tipo: 'sin_permiso' }],
    [503, { detail: 'reintentar' }, { tipo: 'reintentar' }],
    [422, { detail: 'La fecha no puede ser futura', motivo: 'fecha_futura' }, { tipo: 'validacion', mensaje: 'La fecha no puede ser futura' }],
    [422, { detail: [{ msg: 'Value error, motivo muy corto' }] }, { tipo: 'validacion', mensaje: 'motivo muy corto' }],
    [500, { detail: 'x' }, { tipo: 'desconocido' }],
  ])('un %i se traduce a un rechazo de negocio', async (status, cuerpo, error) => {
    expect(await api(servidor(() => json(cuerpo, status))).registrarDevolucion(5, 'DEV-1')).toEqual({ ok: false, error });
  });

  it('una falla de red es "desconocido", no una excepción', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'));
    expect(await api(fetchFn).cerrarCaja('2031-11-17')).toEqual({ ok: false, error: { tipo: 'desconocido' } });
  });
});

describe('crearApi: deshacer un atendido', () => {
  it('POST /deshacer-atendido con el motivo', async () => {
    const cambio = { turno_id: 7, estado: 'reservado', estado_sena: 'acreditado' };
    const fetchFn = servidor(() => json(cambio));
    expect(await api(fetchFn).deshacerAtendido(7, 'turno_equivocado')).toEqual({ ok: true, valor: cambio });
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/turnos/7/deshacer-atendido');
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe('POST');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ motivo: 'turno_equivocado' });
  });

  it.each([
    [
      409,
      { detail: 'x', motivo: 'plazo_vencido', limite_correccion: '2031-11-25T09:00:00-03:00' },
      { tipo: 'plazo_vencido', limiteCorreccion: '2031-11-25T09:00:00-03:00' },
    ],
    [409, { detail: 'x', motivo: 'transicion_invalida' }, { tipo: 'transicion_invalida' }],
    [403, { detail: 'x' }, { tipo: 'sin_permiso' }],
    [404, { detail: 'x' }, { tipo: 'no_encontrado' }],
  ])('un %i se traduce a un rechazo de negocio', async (status, cuerpo, error) => {
    expect(await api(servidor(() => json(cuerpo, status))).deshacerAtendido(7, 'otro')).toEqual({ ok: false, error });
  });

  it('la agenda acepta la acción deshacer_atendido que informa el servidor', async () => {
    const agenda = { vista: 'dia', desde: '2031-11-18', hasta: '2031-11-18', turnos: [TURNO] };
    const r = await api(servidor(() => json(agenda))).agenda(CONSULTA);
    expect(r.turnos[0]?.acciones).toEqual(['deshacer_atendido']);
  });
});
