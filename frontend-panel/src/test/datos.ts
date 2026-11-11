/** Datos 100 % sintéticos (R19) y un `Api` falso para las pruebas de componentes. */
import { vi } from 'vitest';
import type { Api } from '../lib/api';
import type {
  Agenda,
  Ausentismo,
  CajaDia,
  CambioEstado,
  CierreDetalle,
  Devolucion,
  ListadoPacientes,
  Ocupacion,
  Opciones,
  PacienteListado,
  Pendiente,
  Rechazo,
  Acreditacion,
  TurnoAgenda,
  TurnoCreado,
} from '../lib/tipos';

export function turno(sobre: Partial<TurnoAgenda> = {}): TurnoAgenda {
  return {
    id: 11,
    inicio: '2031-11-18T09:00:00-03:00',
    fin: '2031-11-18T09:30:00-03:00',
    estado: 'reservado',
    bloquea_agenda: true,
    origen: 'web',
    profesional: { id: 1, nombre: 'Dra. Ana Ficticia' },
    sillon: { id: 2, nombre: 'Sillón 1' },
    tratamiento: { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 },
    paciente_nombre: 'Carlos Sintético',
    paciente_telefono: '+5491144445555',
    sena: { estado: 'acreditado', monto: '3000.00' },
    vence_en: null,
    acciones: [],
    ...sobre,
  };
}

export function agenda(turnos: readonly TurnoAgenda[], vista: 'dia' | 'semana' = 'dia', fecha = '2031-11-18'): Agenda {
  return vista === 'dia'
    ? { vista, desde: fecha, hasta: fecha, turnos }
    : { vista, desde: '2031-11-17', hasta: '2031-11-23', turnos };
}

export const OPCIONES: Opciones = {
  profesionales: [
    { id: 1, nombre: 'Dra. Ana Ficticia' },
    { id: 4, nombre: 'Dr. Bruno Ejemplo' },
  ],
  sillones: [
    { id: 2, nombre: 'Sillón 1' },
    { id: 5, nombre: 'Sillón 2' },
  ],
  tratamientos: [
    { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 },
    { id: 6, nombre: 'Empaste', duracion_minutos: 45 },
  ],
  puede_escribir: true,
};

export const SOLO_LECTURA: Opciones = {
  ...OPCIONES,
  profesionales: [{ id: 1, nombre: 'Dra. Ana Ficticia' }],
  puede_escribir: false,
};

export const CREADO: TurnoCreado = {
  id: 99,
  inicio: '2031-11-18T11:00:00-03:00',
  fin: '2031-11-18T11:30:00-03:00',
  estado: 'reservado',
  origen: 'manual',
  profesional_id: 1,
  sillon_id: 2,
  tratamiento_id: 3,
  codigo_gestion: 'CODIGO-SINTETICO-0001',
};

export const CAMBIO: CambioEstado = { turno_id: 11, estado: 'ausente', estado_sena: 'no_reembolsado' };

export const SLOTS = [
  { inicio: '2031-11-18T11:00:00-03:00', fin: '2031-11-18T11:30:00-03:00', profesional_id: 1, sillon_id: 2 },
  { inicio: '2031-11-18T11:30:00-03:00', fin: '2031-11-18T12:00:00-03:00', profesional_id: 1, sillon_id: 2 },
];

// --- C-12 --------------------------------------------------------------------------------------------------------

export function caja(sobre: Partial<CajaDia> = {}): CajaDia {
  return {
    dia: '2031-11-18',
    estado: 'abierto',
    cierre_id: null,
    lineas: [{ concepto: 'sena', medio: 'mercadopago', cantidad: 1, total: '3000.00' }],
    total_ingresos: '3000.00',
    total_egresos: '0.00',
    total_neto: '3000.00',
    senas_retenidas: { cantidad: 0, total: '0.00' },
    movimientos: [
      { concepto: 'sena', medio: 'mercadopago', importe: '3000.00', hora: '2031-11-18T10:00:00-03:00', referencia: null, turno_id: 4, presupuesto_id: null },
    ],
    ...sobre,
  };
}

export const CAJA_VACIA: CajaDia = caja({
  lineas: [],
  total_ingresos: '0.00',
  total_neto: '0.00',
  movimientos: [],
});

export function pendiente(sobre: Partial<Pendiente> = {}): Pendiente {
  return {
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
    ...sobre,
  };
}

export const DEVOLUCION: Devolucion = {
  id: 5,
  tipo: 'sena',
  pago_id: 5,
  turno_id: 9,
  importe: '3000.00',
  reembolsado_en: '2031-11-18T10:00:00-03:00',
  referencia: 'DEV-SINT-0001',
};
export const RECHAZO: Rechazo = { pago_id: 5, turno_id: 9, estado_pago: 'a_reembolsar', estado_turno: 'en_espera', importe: '2000.00' };
export const ACREDITACION: Acreditacion = { pago_id: 5, turno_id: 9, efecto: 'acreditado', estado_pago: 'acreditado', estado_turno: 'reservado' };

export function cierre(sobre: Partial<CierreDetalle> = {}): CierreDetalle {
  return {
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
    lineas: [{ concepto: 'sena', medio: 'mercadopago', cantidad: 1, total: '3000.00' }],
    cuadra: true,
    diferencias: [],
    ...sobre,
  };
}

export function pacienteListado(sobre: Partial<PacienteListado> = {}): PacienteListado {
  return {
    id: 8,
    nombre: 'Lucía',
    apellido: 'Ejemplo',
    dni: '30111222',
    telefono: '+5491144445555',
    obra_social: null,
    atendidos: 2,
    ausentes: 1,
    ultimo_turno: '2031-11-10T09:00:00-03:00',
    ...sobre,
  };
}

export function listado(pacientes: readonly PacienteListado[], sobre: Partial<ListadoPacientes> = {}): ListadoPacientes {
  return { total: pacientes.length, pagina: 1, por_pagina: 20, pacientes, ...sobre };
}

export const OCUPACION: Ocupacion = {
  desde: '2031-11-18',
  hasta: '2031-11-18',
  sillones: [
    {
      sillon_id: 2,
      nombre: 'Sillón 1',
      estado: 'activo',
      dias: [{ dia: '2031-11-18', minutos_ocupados: 90, minutos_atencion: 240, porcentaje: '37.50', turnos: 3, minutos_perdidos: 0 }],
    },
    {
      sillon_id: 5,
      nombre: 'Sillón 2',
      estado: 'activo',
      dias: [{ dia: '2031-11-18', minutos_ocupados: 0, minutos_atencion: 0, porcentaje: null, turnos: 0, minutos_perdidos: 0 }],
    },
  ],
};

export const AUSENTISMO: Ausentismo = {
  desde: '2031-11-18',
  hasta: '2031-11-18',
  atendidos: 3,
  ausentes: 1,
  tasa: '25.00',
  sin_marcar: 2,
  por_profesional: [{ profesional_id: 1, nombre: 'Dra. Ana Ficticia', atendidos: 3, ausentes: 1, tasa: '25.00', sin_marcar: 2 }],
  recupero: { senas_retenidas: 1, importe_retenido: '3000.00', porcentaje: '100.00' },
};

/** Un `Api` con todos los métodos espías; cada prueba sobreescribe los que le importan. */
export function apiFalsa(sobre: Partial<Api> = {}) {
  const api = {
    me: vi.fn<Api['me']>(),
    agenda: vi.fn<Api['agenda']>().mockResolvedValue(agenda([])),
    opciones: vi.fn<Api['opciones']>().mockResolvedValue(OPCIONES),
    disponibilidad: vi.fn<Api['disponibilidad']>().mockResolvedValue(SLOTS),
    crearTurno: vi.fn<Api['crearTurno']>().mockResolvedValue({ ok: true, valor: CREADO }),
    marcar: vi.fn<Api['marcar']>().mockResolvedValue({ ok: true, valor: CAMBIO }),
    deshacerAtendido: vi
      .fn<Api['deshacerAtendido']>()
      .mockResolvedValue({ ok: true, valor: { turno_id: 11, estado: 'reservado', estado_sena: 'acreditado' } }),
    caja: vi.fn<Api['caja']>().mockResolvedValue(caja()),
    pendientes: vi.fn<Api['pendientes']>().mockResolvedValue([]),
    rechazarRevision: vi.fn<Api['rechazarRevision']>().mockResolvedValue({ ok: true, valor: RECHAZO }),
    acreditarRevision: vi.fn<Api['acreditarRevision']>().mockResolvedValue({ ok: true, valor: ACREDITACION }),
    registrarDevolucion: vi.fn<Api['registrarDevolucion']>().mockResolvedValue({ ok: true, valor: DEVOLUCION }),
    registrarDevolucionExcedente: vi
      .fn<Api['registrarDevolucionExcedente']>()
      .mockResolvedValue({ ok: true, valor: { ...DEVOLUCION, tipo: 'excedente_mp' } }),
    cerrarCaja: vi.fn<Api['cerrarCaja']>().mockResolvedValue({ ok: true, valor: cierre() }),
    cierre: vi.fn<Api['cierre']>().mockResolvedValue(cierre()),
    anularCierre: vi.fn<Api['anularCierre']>().mockResolvedValue({ ok: true, valor: cierre({ estado: 'anulado' }) }),
    ocupacion: vi.fn<Api['ocupacion']>().mockResolvedValue(OCUPACION),
    ausentismo: vi.fn<Api['ausentismo']>().mockResolvedValue(AUSENTISMO),
    listarPacientes: vi.fn<Api['listarPacientes']>().mockResolvedValue(listado([])),
    ...sobre,
  };
  return api;
}
