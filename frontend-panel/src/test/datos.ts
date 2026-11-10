/** Datos 100 % sintéticos (R19) y un `Api` falso para las pruebas de componentes. */
import { vi } from 'vitest';
import type { Api } from '../lib/api';
import type { Agenda, CambioEstado, Opciones, TurnoAgenda, TurnoCreado } from '../lib/tipos';

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

/** Un `Api` con todos los métodos espías; cada prueba sobreescribe los que le importan. */
export function apiFalsa(sobre: Partial<Api> = {}) {
  const api = {
    me: vi.fn<Api['me']>(),
    agenda: vi.fn<Api['agenda']>().mockResolvedValue(agenda([])),
    opciones: vi.fn<Api['opciones']>().mockResolvedValue(OPCIONES),
    disponibilidad: vi.fn<Api['disponibilidad']>().mockResolvedValue(SLOTS),
    crearTurno: vi.fn<Api['crearTurno']>().mockResolvedValue({ ok: true, valor: CREADO }),
    marcar: vi.fn<Api['marcar']>().mockResolvedValue({ ok: true, valor: CAMBIO }),
    ...sobre,
  };
  return api;
}
