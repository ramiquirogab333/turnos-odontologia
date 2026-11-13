import { describe, expect, it } from 'vitest';
import { normalizarTelefono, puedeAvanzar, validarNombre, validarTelefono } from './validacion';

describe('normalizarTelefono', () => {
  it('quita espacios, guiones y paréntesis y conserva el +', () => {
    expect(normalizarTelefono('+54 9 11 4444-5555')).toBe('+5491144445555');
    expect(normalizarTelefono(' +54 (9) 11 4444 5555 ')).toBe('+5491144445555');
  });
  it('no inventa el prefijo: un número sin + queda sin +', () => {
    expect(normalizarTelefono('11 4444-5555')).toBe('1144445555');
  });
});

describe('validarTelefono (E.164: + y 2 a 15 dígitos, primero 1-9)', () => {
  it('acepta números válidos', () => {
    expect(validarTelefono('+5491144445555')).toBeNull();
    expect(validarTelefono('+54 9 11 4444-5555')).toBeNull();
    expect(validarTelefono('+12')).toBeNull(); // límite inferior
    expect(validarTelefono('+123456789012345')).toBeNull(); // límite superior (15 dígitos)
  });
  it('rechaza vacío, corto, sin código de país y con letras, con un mensaje accionable', () => {
    for (const malo of ['', '1234', '5491144445555', '+0123456', '+54911abc5555', '+1234567890123456', '+']) {
      const msg = validarTelefono(malo);
      expect(msg, malo).not.toBeNull();
      expect(msg).toMatch(/\+/);
    }
  });
});

describe('validarNombre (1 a 200 caracteres tras recortar)', () => {
  it('acepta un nombre completo', () => {
    expect(validarNombre('Carlos Sintético')).toBeNull();
    expect(validarNombre('A')).toBeNull();
    expect(validarNombre('x'.repeat(200))).toBeNull();
  });
  it('rechaza vacío, solo espacios y más de 200', () => {
    expect(validarNombre('')).toMatch(/nombre/i);
    expect(validarNombre('   ')).toMatch(/nombre/i);
    expect(validarNombre('x'.repeat(201))).toMatch(/200/);
  });
});

describe('puedeAvanzar', () => {
  const base = { tratamientoId: null, profesionalId: null, slot: null, nombre: '', telefono: '' } as const;
  const slot = { inicio: '2026-11-16T10:00:00-03:00', fin: '2026-11-16T10:30:00-03:00', profesional_id: 1, sillon_id: 1 };

  it('paso 1 requiere tratamiento y profesional', () => {
    expect(puedeAvanzar(1, base)).toBe(false);
    expect(puedeAvanzar(1, { ...base, tratamientoId: 1 })).toBe(false);
    expect(puedeAvanzar(1, { ...base, tratamientoId: 1, profesionalId: 2 })).toBe(true);
  });
  it('paso 2 requiere un horario elegido', () => {
    expect(puedeAvanzar(2, base)).toBe(false);
    expect(puedeAvanzar(2, { ...base, slot })).toBe(true);
  });
  it('paso 3 requiere nombre y teléfono válidos', () => {
    const e = { ...base, slot };
    expect(puedeAvanzar(3, e)).toBe(false);
    expect(puedeAvanzar(3, { ...e, nombre: 'Carlos Sintético', telefono: '1234' })).toBe(false);
    expect(puedeAvanzar(3, { ...e, nombre: '  ', telefono: '+5491144445555' })).toBe(false);
    expect(puedeAvanzar(3, { ...e, nombre: 'Carlos Sintético', telefono: '+54 9 11 4444 5555' })).toBe(true);
  });
});
