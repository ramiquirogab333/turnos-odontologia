import { describe, expect, it } from 'vitest';
import {
  agregarAlLote,
  CARAS,
  combinacionValida,
  CUADRANTES_PERMANENTES,
  CUADRANTES_TEMPORALES,
  ESTADOS_HALLAZGO,
  etiquetaHallazgo,
  MAX_LOTE,
  PIEZAS_PERMANENTES,
  PIEZAS_TEMPORALES,
  piezasDeCuadrante,
  requisitoDeCara,
  textoVigente,
} from './odontograma';
import type { HallazgoNuevo, PiezaVigente } from './tipos';

describe('catálogo FDI', () => {
  it('son 52 piezas: 32 permanentes (8 por cuadrante) y 20 temporales (5 por cuadrante)', () => {
    expect(PIEZAS_PERMANENTES).toHaveLength(32);
    expect(PIEZAS_TEMPORALES).toHaveLength(20);
    expect(PIEZAS_PERMANENTES[0]).toBe(11);
    expect(PIEZAS_PERMANENTES[31]).toBe(48);
    expect(PIEZAS_TEMPORALES[0]).toBe(51);
    expect(PIEZAS_TEMPORALES[19]).toBe(85);
  });

  it('cada cuadrante lista sus piezas en orden', () => {
    expect(piezasDeCuadrante(1)).toEqual([11, 12, 13, 14, 15, 16, 17, 18]);
    expect(piezasDeCuadrante(5)).toEqual([51, 52, 53, 54, 55]);
    expect(CUADRANTES_PERMANENTES).toEqual([1, 2, 3, 4]);
    expect(CUADRANTES_TEMPORALES).toEqual([5, 6, 7, 8]);
  });
});

describe('combinacionValida (la misma regla que el servidor)', () => {
  it('caries y obturado exigen cara', () => {
    expect(combinacionValida(16, 'O', 'caries')).toBe(true);
    expect(combinacionValida(16, null, 'caries')).toBe(false);
    expect(combinacionValida(11, 'V', 'obturado')).toBe(true);
    expect(combinacionValida(11, null, 'obturado')).toBe(false);
  });

  it('ausente, extracción indicada, corona, endodoncia e implante no llevan cara', () => {
    for (const estado of ['ausente', 'extraccion_indicada', 'corona', 'endodoncia', 'implante']) {
      expect(combinacionValida(36, null, estado)).toBe(true);
      expect(combinacionValida(36, 'O', estado)).toBe(false);
    }
  });

  it('sano admite ambas', () => {
    expect(combinacionValida(16, null, 'sano')).toBe(true);
    expect(combinacionValida(16, 'M', 'sano')).toBe(true);
  });

  it('una pieza fuera del catálogo o un estado desconocido es inválido', () => {
    expect(combinacionValida(19, null, 'sano')).toBe(false);
    expect(combinacionValida(86, null, 'sano')).toBe(false);
    expect(combinacionValida(56, null, 'sano')).toBe(false);
    expect(combinacionValida(85, null, 'sano')).toBe(true);
    expect(combinacionValida(16, null, 'fracturado')).toBe(false);
  });
});

describe('requisitoDeCara', () => {
  it('dice si la cara es obligatoria, opcional o no se ofrece', () => {
    expect(requisitoDeCara('caries')).toBe('exige');
    expect(requisitoDeCara('obturado')).toBe('exige');
    expect(requisitoDeCara('sano')).toBe('opcional');
    expect(requisitoDeCara('corona')).toBe('no');
    expect(ESTADOS_HALLAZGO.map((e) => e.clave)).toEqual(['sano', 'caries', 'obturado', 'ausente', 'extraccion_indicada', 'corona', 'endodoncia', 'implante']);
    expect(CARAS.map((c) => c.clave)).toEqual(['O', 'M', 'D', 'V', 'L']);
  });
});

describe('textoVigente', () => {
  const pieza = (sobre: Partial<PiezaVigente>): PiezaVigente => ({ pieza: 16, estado_pieza: null, caras: {}, ...sobre });

  it('una pieza sin hallazgos o ausente de la respuesta dice «Sin hallazgos»', () => {
    expect(textoVigente(undefined)).toBe('Sin hallazgos');
    expect(textoVigente(pieza({}))).toBe('Sin hallazgos');
  });

  it('el estado de la pieza y las caras con hallazgo se leen como texto', () => {
    expect(textoVigente(pieza({ caras: { O: 'caries' } }))).toBe('Caries: oclusal');
    expect(textoVigente(pieza({ estado_pieza: 'endodoncia' }))).toBe('Endodoncia');
    expect(textoVigente(pieza({ estado_pieza: 'extraccion_indicada' }))).toBe('Extracción indicada');
  });

  it('agrupa las caras por estado en el orden O M D V L y suma el estado de la pieza', () => {
    expect(textoVigente(pieza({ caras: { L: 'caries', O: 'caries', V: 'obturado' } }))).toBe('Caries: oclusal, lingual/palatina · Obturado: vestibular');
    expect(textoVigente(pieza({ estado_pieza: 'corona', caras: { M: 'obturado' } }))).toBe('Corona · Obturado: mesial');
  });
});

describe('lote de hallazgos', () => {
  const h = (sobre: Partial<HallazgoNuevo> = {}): HallazgoNuevo => ({ pieza: 16, cara: 'O', estado: 'caries', nota: null, ...sobre });

  it('agrega hallazgos distintos en orden', () => {
    const r1 = agregarAlLote([], h());
    expect(r1.error).toBeNull();
    const r2 = agregarAlLote(r1.lote, h({ pieza: 36, cara: null, estado: 'endodoncia' }));
    expect(r2.lote.map(etiquetaHallazgo)).toEqual(['16 · O · Caries', '36 · Endodoncia']);
  });

  it('rechaza un duplicado exacto pero acepta el mismo hallazgo con otra nota', () => {
    const lote = agregarAlLote([], h()).lote;
    const repetido = agregarAlLote(lote, h());
    expect(repetido.error).toBe('Ese hallazgo ya está en el lote');
    expect(repetido.lote).toBe(lote);
    expect(agregarAlLote(lote, h({ nota: 'otra' })).lote).toHaveLength(2);
  });

  it('el tope es de 64 hallazgos y el siguiente no entra', () => {
    let lote: readonly HallazgoNuevo[] = [];
    for (let i = 0; i < MAX_LOTE; i += 1) lote = agregarAlLote(lote, h({ nota: `n${String(i)}` })).lote;
    expect(lote).toHaveLength(64);
    const mas = agregarAlLote(lote, h({ nota: 'otra' }));
    expect(mas.error).toBe('Un lote admite hasta 64 hallazgos: registrá estos primero');
    expect(mas.lote).toHaveLength(64);
  });

  it('el rótulo incluye la cara solo si la hay', () => {
    expect(etiquetaHallazgo(h({ pieza: 11, cara: 'V', estado: 'obturado' }))).toBe('11 · V · Obturado');
    expect(etiquetaHallazgo(h({ pieza: 48, cara: null, estado: 'implante' }))).toBe('48 · Implante');
  });
});
