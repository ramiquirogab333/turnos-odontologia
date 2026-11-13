import { afterEach, describe, expect, it, vi } from 'vitest';
import { borrarPendiente, guardarPendiente, leerPendiente } from './almacen';

const CLAVE = 'sena-pendiente-v2';
const AHORA = Date.parse('2026-11-16T12:00:00Z');
const HORA = 3_600_000;

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

describe('seña pendiente en localStorage (sobrevive a la pestaña nueva que abre el retorno de Mercado Pago)', () => {
  it('guarda lo mínimo (turno, código y vencimiento) con versión y lo lee de vuelta', () => {
    guardarPendiente({ turnoId: 5, codigoGestion: 'ABCD2345', venceEn: '2026-11-16T12:30:00Z' }, AHORA);
    expect(leerPendiente(AHORA)).toEqual({ turnoId: 5, codigoGestion: 'ABCD2345' });
    const crudo = JSON.parse(localStorage.getItem(CLAVE) ?? 'null') as Record<string, unknown>;
    expect(Object.keys(crudo).sort()).toEqual(['codigoGestion', 'expira', 'turnoId', 'v']);
    expect(sessionStorage.length).toBe(0); // ya no es por pestaña
  });

  it('vence con la pre-reserva más una gracia de 30 minutos y nunca más de 24 horas', () => {
    guardarPendiente({ turnoId: 5, codigoGestion: 'ABCD2345', venceEn: '2026-11-16T12:30:00Z' }, AHORA);
    expect(leerPendiente(AHORA + HORA - 1)).not.toBeNull(); // 13:00 = vence + 30 min
    expect(leerPendiente(AHORA + HORA + 1)).toBeNull();
    expect(localStorage.getItem(CLAVE)).toBeNull(); // el vencido se limpia solo

    guardarPendiente({ turnoId: 6, codigoGestion: 'ZZZZ2345', venceEn: '2027-01-01T00:00:00Z' }, AHORA);
    expect(leerPendiente(AHORA + 24 * HORA - 1)).not.toBeNull();
    expect(leerPendiente(AHORA + 24 * HORA + 1)).toBeNull();
  });

  it('un vencimiento ilegible cae al tope de 24 horas', () => {
    guardarPendiente({ turnoId: 5, codigoGestion: 'ABCD2345', venceEn: 'no es una fecha' }, AHORA);
    expect(leerPendiente(AHORA + 23 * HORA)).not.toBeNull();
    expect(leerPendiente(AHORA + 25 * HORA)).toBeNull();
  });

  it('sobrescribe el valor anterior y borrarPendiente lo elimina', () => {
    guardarPendiente({ turnoId: 5, codigoGestion: 'AAAA1111', venceEn: '2026-11-16T12:30:00Z' }, AHORA);
    guardarPendiente({ turnoId: 9, codigoGestion: 'BBBB2222', venceEn: '2026-11-16T12:30:00Z' }, AHORA);
    expect(leerPendiente(AHORA)).toEqual({ turnoId: 9, codigoGestion: 'BBBB2222' });
    borrarPendiente();
    expect(leerPendiente(AHORA)).toBeNull();
  });

  it.each([
    ['vacío', null],
    ['no es JSON', 'esto no es json'],
    ['otra versión', JSON.stringify({ v: 1, turnoId: 5, codigoGestion: 'X', expira: AHORA + HORA })],
    ['campos de otro tipo', JSON.stringify({ v: 2, turnoId: '5', codigoGestion: 7, expira: 'x' })],
    ['sin vencimiento', JSON.stringify({ v: 2, turnoId: 5, codigoGestion: 'X' })],
  ])('un valor inválido (%s) se trata como ausente', (_nombre, crudo) => {
    if (crudo !== null) localStorage.setItem(CLAVE, crudo);
    expect(leerPendiente(AHORA)).toBeNull();
  });

  it('el código de gestión nunca va en la URL', () => {
    const antes = window.location.href;
    guardarPendiente({ turnoId: 5, codigoGestion: 'ABCD2345', venceEn: '2026-11-16T12:30:00Z' }, AHORA);
    expect(window.location.href).toBe(antes);
    expect(window.location.href).not.toContain('ABCD2345');
  });

  it('si el almacenamiento está bloqueado no lanza (try/catch): guardar no hace nada y leer devuelve null', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('bloqueado', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('bloqueado', 'SecurityError');
    });
    expect(() => {
      guardarPendiente({ turnoId: 5, codigoGestion: 'ABCD2345', venceEn: '2026-11-16T12:30:00Z' }, AHORA);
    }).not.toThrow();
    expect(leerPendiente(AHORA)).toBeNull();
  });
});
