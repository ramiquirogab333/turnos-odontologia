import { pesosCompactos } from '../lib/presupuestos';
import type { LineaPresupuesto } from '../lib/tipos';

interface Props {
  readonly lineas: readonly LineaPresupuesto[];
  /** Tratamientos que ya no se ofrecen para líneas nuevas (C-14): la línea existente sigue mostrándose con «(inactivo)». */
  readonly inactivos?: ReadonlySet<number>;
}

/** Líneas de un presupuesto, una tarjeta por línea con los importes tal como los calculó el servidor (RN-PG-04). */
export function LineasPresupuesto({ lineas, inactivos }: Props) {
  return (
    <ul className="lineas-presupuesto" aria-label="Líneas del presupuesto">
      {lineas.map((l) => (
        <li key={l.id} className="linea-presupuesto">
          <p className="linea-nombre texto-largo">
            <span className="linea-tratamiento">{l.tratamiento.nombre}</span>
            {inactivos?.has(l.tratamiento.id) === true ? ' (inactivo)' : ''} × {l.cantidad}
            {l.pieza !== null ? ` · pieza ${String(l.pieza)}` : ''}
            {l.cara !== null ? ` · ${l.cara}` : ''}
          </p>
          <dl className="importes">
            <div>
              <dt>Bruto</dt>
              <dd className="monto">{pesosCompactos(l.importe_bruto)}</dd>
            </div>
            <div>
              <dt>Cobertura</dt>
              <dd className="monto">{pesosCompactos(l.importe_cobertura)}</dd>
            </div>
            {l.importe_diferencial !== '0.00' && (
              <div>
                <dt>Diferencial</dt>
                <dd className="monto">{pesosCompactos(l.importe_diferencial)}</dd>
              </div>
            )}
            <div>
              <dt>A cargo</dt>
              <dd className="monto">{pesosCompactos(l.importe_paciente)}</dd>
            </div>
          </dl>
          {l.sin_cobertura && <p className="nota">Sin cobertura para esta prestación</p>}
        </li>
      ))}
    </ul>
  );
}
