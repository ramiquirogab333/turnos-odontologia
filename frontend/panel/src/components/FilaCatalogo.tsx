import type { ReactNode } from 'react';

interface Props {
  readonly titulo: string;
  /** Datos de la fila, cada uno en su propio elemento para leerse por separado. */
  readonly detalle?: ReactNode;
  /** Estado como texto ("Activo", "Pausada"…): el color nunca es lo único que lo dice. */
  readonly estado: string;
  readonly atenuada?: boolean;
  /** Aclaraciones bajo los datos ("No se ofrece para reservar", "Sin seña"). */
  readonly notas?: readonly string[];
  /** Botones de la fila: van en una línea propia, de 48 px, para tocarse bien a 360 px. */
  readonly acciones: ReactNode;
}

export function FilaCatalogo({ titulo, detalle = null, estado, atenuada = false, notas = [], acciones }: Props) {
  return (
    <li className={`fila-catalogo${atenuada ? ' atenuada' : ''}`}>
      <div className="fila-catalogo-datos">
        <p className="fila-catalogo-titulo">{titulo}</p>
        {detalle !== null && <p className="fila-catalogo-detalle">{detalle}</p>}
        <p className="fila-catalogo-estado">{estado}</p>
        {notas.map((nota) => (
          <p key={nota} className="nota">
            {nota}
          </p>
        ))}
      </div>
      <div className="fila-catalogo-acciones">{acciones}</div>
    </li>
  );
}
