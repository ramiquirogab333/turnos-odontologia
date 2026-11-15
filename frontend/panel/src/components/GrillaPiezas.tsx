import { useRef, useState, type KeyboardEvent } from 'react';
import { CUADRANTES_PERMANENTES, CUADRANTES_TEMPORALES, piezasDeCuadrante, textoVigente } from '../lib/odontograma';
import type { PiezaVigente } from '../lib/tipos';

interface Props {
  readonly vigentes: readonly PiezaVigente[];
  /** `true` muestra los 4 cuadrantes de dientes temporales (51–85). */
  readonly temporales: boolean;
  readonly seleccionada: number | null;
  /** Con solo lectura las piezas se leen pero no se eligen. */
  readonly puedeElegir: boolean;
  readonly onElegir: (pieza: number) => void;
}

/** Piezas FDI por cuadrante: número y estado vigente en texto (nunca solo color), con flechas dentro de cada cuadrante. */
export function GrillaPiezas({ vigentes, temporales, seleccionada, puedeElegir, onElegir }: Props) {
  const porPieza = new Map(vigentes.map((p) => [p.pieza, p]));
  const cuadrantes = temporales ? CUADRANTES_TEMPORALES : CUADRANTES_PERMANENTES;
  return (
    <div className="grilla-piezas">
      {cuadrantes.map((c) => (
        <Cuadrante
          key={c}
          cuadrante={c}
          temporal={temporales}
          porPieza={porPieza}
          seleccionada={seleccionada}
          puedeElegir={puedeElegir}
          onElegir={onElegir}
        />
      ))}
    </div>
  );
}

interface PropsCuadrante {
  readonly cuadrante: number;
  readonly temporal: boolean;
  readonly porPieza: ReadonlyMap<number, PiezaVigente>;
  readonly seleccionada: number | null;
  readonly puedeElegir: boolean;
  readonly onElegir: (pieza: number) => void;
}

function Cuadrante({ cuadrante, temporal, porPieza, seleccionada, puedeElegir, onElegir }: PropsCuadrante) {
  const piezas = piezasDeCuadrante(cuadrante);
  const [activa, setActiva] = useState(piezas[0] ?? 0);
  const botones = useRef(new Map<number, HTMLButtonElement>());

  function moverCon(evento: KeyboardEvent<HTMLButtonElement>, pieza: number): void {
    const i = piezas.indexOf(pieza);
    const destino =
      evento.key === 'ArrowRight' || evento.key === 'ArrowDown'
        ? piezas[Math.min(i + 1, piezas.length - 1)]
        : evento.key === 'ArrowLeft' || evento.key === 'ArrowUp'
          ? piezas[Math.max(i - 1, 0)]
          : evento.key === 'Home'
            ? piezas[0]
            : evento.key === 'End'
              ? piezas[piezas.length - 1]
              : undefined;
    if (destino === undefined) return;
    evento.preventDefault();
    setActiva(destino);
    botones.current.get(destino)?.focus();
  }

  return (
    <div
      role="group"
      aria-label={`Cuadrante ${String(cuadrante)}`}
      className={`cuadrante ${temporal ? 'cuadrante-temporal' : 'cuadrante-permanente'}`}
    >
      <p className="cuadrante-titulo">Cuadrante {cuadrante}</p>
      <div className="piezas">
        {piezas.map((pieza) => {
          const texto = textoVigente(porPieza.get(pieza));
          const hay = texto !== 'Sin hallazgos';
          const contenido = (
            <>
              <span className="pieza-numero">{pieza}</span>{' '}
              <span className="pieza-estado">{texto}</span>
            </>
          );
          return puedeElegir ? (
            <button
              key={pieza}
              type="button"
              ref={(el) => {
                if (el === null) botones.current.delete(pieza);
                else botones.current.set(pieza, el);
              }}
              className={`pieza${hay ? ' pieza-con-hallazgo' : ''}${seleccionada === pieza ? ' pieza-elegida' : ''}`}
              aria-pressed={seleccionada === pieza}
              tabIndex={activa === pieza ? 0 : -1}
              onFocus={() => {
                setActiva(pieza);
              }}
              onKeyDown={(e) => {
                moverCon(e, pieza);
              }}
              onClick={() => {
                onElegir(pieza);
              }}
            >
              {contenido}
            </button>
          ) : (
            <div key={pieza} className={`pieza${hay ? ' pieza-con-hallazgo' : ''}`}>
              {contenido}
            </div>
          );
        })}
      </div>
    </div>
  );
}
