import type { Cara, HallazgoNuevo, PiezaVigente } from './tipos';

/** Catálogo FDI espejo del backend (`app/clinica/odontograma.py`); el servidor sigue siendo la barrera (422). */
export const CUADRANTES_PERMANENTES: readonly number[] = [1, 2, 3, 4];
export const CUADRANTES_TEMPORALES: readonly number[] = [5, 6, 7, 8];

export function piezasDeCuadrante(cuadrante: number): readonly number[] {
  const ultima = cuadrante <= 4 ? 8 : 5;
  return Array.from({ length: ultima }, (_, i) => cuadrante * 10 + i + 1);
}

export const PIEZAS_PERMANENTES: readonly number[] = CUADRANTES_PERMANENTES.flatMap(piezasDeCuadrante);
export const PIEZAS_TEMPORALES: readonly number[] = CUADRANTES_TEMPORALES.flatMap(piezasDeCuadrante);
const PIEZAS_FDI: readonly number[] = [...PIEZAS_PERMANENTES, ...PIEZAS_TEMPORALES];

export const MAX_LOTE = 64;

export const CARAS: readonly { readonly clave: Cara; readonly etiqueta: string }[] = [
  { clave: 'O', etiqueta: 'oclusal' },
  { clave: 'M', etiqueta: 'mesial' },
  { clave: 'D', etiqueta: 'distal' },
  { clave: 'V', etiqueta: 'vestibular' },
  { clave: 'L', etiqueta: 'lingual/palatina' },
];

export type RequisitoCara = 'exige' | 'opcional' | 'no';

interface EstadoHallazgo {
  readonly clave: string;
  readonly etiqueta: string;
  readonly cara: RequisitoCara;
}

export const ESTADOS_HALLAZGO: readonly EstadoHallazgo[] = [
  { clave: 'sano', etiqueta: 'Sano', cara: 'opcional' },
  { clave: 'caries', etiqueta: 'Caries', cara: 'exige' },
  { clave: 'obturado', etiqueta: 'Obturado', cara: 'exige' },
  { clave: 'ausente', etiqueta: 'Ausente', cara: 'no' },
  { clave: 'extraccion_indicada', etiqueta: 'Extracción indicada', cara: 'no' },
  { clave: 'corona', etiqueta: 'Corona', cara: 'no' },
  { clave: 'endodoncia', etiqueta: 'Endodoncia', cara: 'no' },
  { clave: 'implante', etiqueta: 'Implante', cara: 'no' },
];

const ESTADO_POR_CLAVE = new Map(ESTADOS_HALLAZGO.map((e) => [e.clave, e]));

export const etiquetaEstado = (clave: string): string => ESTADO_POR_CLAVE.get(clave)?.etiqueta ?? clave;

export function requisitoDeCara(estado: string): RequisitoCara {
  return ESTADO_POR_CLAVE.get(estado)?.cara ?? 'no';
}

/** Pieza FDI válida y coherencia cara/estado: la misma regla que `registro_valido` del servidor. */
export function combinacionValida(pieza: number, cara: Cara | null, estado: string): boolean {
  if (!PIEZAS_FDI.includes(pieza) || !ESTADO_POR_CLAVE.has(estado)) return false;
  const requisito = requisitoDeCara(estado);
  if (requisito === 'exige') return cara !== null;
  if (requisito === 'no') return cara === null;
  return true;
}

const nombreDeCara = (clave: string): string => CARAS.find((c) => c.clave === clave)?.etiqueta ?? clave;

/** Estado vigente de una pieza como texto: «Caries: oclusal», «Endodoncia» o «Sin hallazgos». */
export function textoVigente(pieza: PiezaVigente | undefined): string {
  if (pieza === undefined) return 'Sin hallazgos';
  const partes: string[] = [];
  if (pieza.estado_pieza !== null) partes.push(etiquetaEstado(pieza.estado_pieza));
  const porEstado = new Map<string, string[]>();
  for (const { clave } of CARAS) {
    const estado = pieza.caras[clave];
    if (estado === undefined) continue;
    porEstado.set(estado, [...(porEstado.get(estado) ?? []), nombreDeCara(clave)]);
  }
  for (const [estado, caras] of porEstado) partes.push(`${etiquetaEstado(estado)}: ${caras.join(', ')}`);
  return partes.length === 0 ? 'Sin hallazgos' : partes.join(' · ');
}

export function etiquetaHallazgo(h: HallazgoNuevo): string {
  return [String(h.pieza), h.cara, etiquetaEstado(h.estado)].filter((x): x is string => x !== null).join(' · ');
}

const iguales = (a: HallazgoNuevo, b: HallazgoNuevo): boolean =>
  a.pieza === b.pieza && a.cara === b.cara && a.estado === b.estado && a.nota === b.nota;

/** Suma un hallazgo al lote respetando el tope de 64 y sin duplicados exactos; si no entra, devuelve el mismo lote y el porqué. */
export function agregarAlLote(
  lote: readonly HallazgoNuevo[],
  nuevo: HallazgoNuevo,
): { readonly lote: readonly HallazgoNuevo[]; readonly error: string | null } {
  if (lote.length >= MAX_LOTE) return { lote, error: 'Un lote admite hasta 64 hallazgos: registrá estos primero' };
  if (lote.some((h) => iguales(h, nuevo))) return { lote, error: 'Ese hallazgo ya está en el lote' };
  return { lote: [...lote, nuevo], error: null };
}
