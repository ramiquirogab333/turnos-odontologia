import { pesos } from '../lib/formato';
import { cantidad } from '../lib/iniciar';
import { etiquetaLinea, etiquetaMovimiento } from '../lib/presentacion';
import { horaClinica } from '../lib/tiempo';
import type { CajaDia } from '../lib/tipos';

/** Lo que entró y salió de la caja en el día, por concepto y medio de pago. Los importes solo se formatean. */
export function ResumenCaja({ caja }: { readonly caja: CajaDia }) {
  const sinMovimientos = caja.lineas.length === 0 && caja.movimientos.length === 0;

  return (
    <section className="resumen-caja" aria-label="Resumen de la caja">
      {sinMovimientos ? (
        <p className="vacio">No hubo movimientos este día</p>
      ) : (
        <>
          <p className="total-dia">Total del día: {pesos(caja.total_neto)}</p>
          <p>
            Ingresos {pesos(caja.total_ingresos)} · Egresos {pesos(caja.total_egresos)}
          </p>
          <ul className="lista-simple" aria-label="Detalle por concepto y medio de pago">
            {caja.lineas.map((l) => (
              <li key={`${l.concepto}-${l.medio}`}>{`${etiquetaLinea(l.concepto, l.medio)}: ${pesos(l.total)} (${String(l.cantidad)})`}</li>
            ))}
          </ul>
          {caja.senas_retenidas.cantidad > 0 && (
            <p className="nota">{`Señas retenidas por ausencia: ${pesos(caja.senas_retenidas.total)} (${cantidad(caja.senas_retenidas.cantidad, 'seña', 'señas')})`}</p>
          )}
          {caja.movimientos.length > 0 && (
            <details>
              <summary>Movimientos del día</summary>
              <ul className="lista-simple" aria-label="Movimientos del día">
                {caja.movimientos.map((m, i) => (
                  <li key={`${m.hora}-${String(i)}`}>
                    {`${horaClinica(m.hora)} · ${etiquetaMovimiento(m.concepto, m.medio)}: ${pesos(m.importe)}${m.referencia !== null ? ` · ${m.referencia}` : ''}`}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
