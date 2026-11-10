import { describe, expect, it } from 'vitest';
import { normalizarTelefono, validarNombre, validarTelefono } from './validacion';

describe('validarTelefono', () => {
  it.each(['+5491144445555', '+54 9 11 4444-5555', '+54 (9) 11.4444.5555'])('acepta %s', (valor) => {
    expect(validarTelefono(valor)).toBeNull();
  });

  it.each(['11 5555 6666', '5491144445555', '+0123', '+', '', '+54abc'])('rechaza "%s" explicando cómo corregirlo', (valor) => {
    expect(validarTelefono(valor)).toContain('+5491144445555');
  });

  it('normaliza separadores sin agregar prefijo', () => {
    expect(normalizarTelefono('+54 9 11-4444 5555')).toBe('+5491144445555');
    expect(normalizarTelefono('11 5555')).toBe('115555');
  });
});

describe('validarNombre', () => {
  it('acepta un nombre normal y el máximo exacto', () => {
    expect(validarNombre('Carlos Sintético')).toBeNull();
    expect(validarNombre('x'.repeat(200))).toBeNull();
  });

  it.each(['', '   '])('rechaza vacío o solo espacios (%j)', (valor) => {
    expect(validarNombre(valor)).toMatch(/nombre/i);
  });

  it('rechaza más de 200 caracteres', () => {
    expect(validarNombre('x'.repeat(201))).toContain('200');
  });
});
