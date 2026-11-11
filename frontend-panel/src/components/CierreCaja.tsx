import { Suspense, use, useState } from 'react';
import type { Api } from '../lib/api';
import { pesos } from '../lib/formato';
import { iniciar } from '../lib/iniciar';
import { etiquetaLinea } from '../lib/presentacion';
import { etiquetaDiaLarga, fechaCorta, horaClinica } from '../lib/tiempo';
import type { CajaDia, CierreDetalle } from '../lib/tipos';
import { Cargando } from './Cargando';
import { Dialogo } from './Dialogo';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';
import { useEnvio } from './useEnvio';

interface Props {
  readonly caja: CajaDia;
  /** "Hoy" en la clínica ("YYYY-MM-DD"). */
  readonly hoy: string;
  readonly esAdmin: boolean;
  readonly api: Api;
  readonly onCambio: () => void;
}

const FALTA_MOTIVO = 'Escribí el motivo de la anulación (al menos 3 letras).';

export function CierreCaja({ caja, hoy, esAdmin, api, onCambio }: Props) {
  return (
    <section className="cierre-caja" aria-labelledby="titulo-cierre">
      <h3 id="titulo-cierre">Cierre de caja</h3>
      {caja.estado === 'cerrado' && caja.cierre_id !== null ? (
        <CierreVigente key={caja.cierre_id} cierreId={caja.cierre_id} dia={caja.dia} esAdmin={esAdmin} api={api} onCambio={onCambio} />
      ) : caja.dia >= hoy ? (
        <p className="nota">El día todavía no terminó: se puede cerrar desde mañana a las 00:15.</p>
      ) : (
        <CerrarDia caja={caja} api={api} onCambio={onCambio} />
      )}
    </section>
  );
}

// --- Cerrar un día terminado ---------------------------------------------------------------------------------------

function CerrarDia({ caja, api, onCambio }: Pick<Props, 'caja' | 'api' | 'onCambio'>) {
  const [abierto, setAbierto] = useState(false);
  const { enviando, rechazo, setRechazo, ejecutar } = useEnvio('cierre', onCambio);

  function cerrar(): void {
    setAbierto(false);
    setRechazo(null);
  }

  return (
    <>
      <p className="nota">El día ya terminó. Al cerrar la caja se guardan los totales y queda registrado quién la cerró.</p>
      <button
        type="button"
        className="boton boton-primario"
        onClick={() => {
          setRechazo(null);
          setAbierto(true);
        }}
      >
        Cerrar caja
      </button>
      {abierto && (
        <Dialogo
          titulo={`¿Cerrar la caja del ${etiquetaDiaLarga(caja.dia)}?`}
          confirmar="Sí, cerrar la caja"
          enviando={enviando}
          rechazo={rechazo}
          onVolver={cerrar}
          onConfirmar={() => {
            void ejecutar(() => api.cerrarCaja(caja.dia), () => {
              cerrar();
              onCambio();
            });
          }}
        >
          <p>Ingresos {pesos(caja.total_ingresos)}</p>
          <p>Egresos {pesos(caja.total_egresos)}</p>
          <p>Total del día {pesos(caja.total_neto)}</p>
          <p>Después de cerrar, no se pueden cargar ni quitar movimientos de ese día.</p>
        </Dialogo>
      )}
    </>
  );
}

// --- Un día cerrado: quién, cuándo, si cuadra y cómo anularlo -------------------------------------------------------

interface PropsVigente {
  readonly cierreId: number;
  readonly dia: string;
  readonly esAdmin: boolean;
  readonly api: Api;
  readonly onCambio: () => void;
}

function CierreVigente({ cierreId, dia, esAdmin, api, onCambio }: PropsVigente) {
  const [pendiente, setPendiente] = useState(() => iniciar(() => api.cierre(cierreId)));
  return (
    <ErrorBoundary
      onReintentar={() => {
        setPendiente(iniciar(() => api.cierre(cierreId)));
      }}
      fallback={(volver) => <ErrorCarga mensaje="No pudimos cargar el cierre. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />}
    >
      <Suspense fallback={<Cargando texto="Cargando el cierre…" />}>
        <DetalleCierre pendiente={pendiente} cierreId={cierreId} dia={dia} esAdmin={esAdmin} api={api} onCambio={onCambio} />
      </Suspense>
    </ErrorBoundary>
  );
}

function DetalleCierre({ pendiente, cierreId, dia, esAdmin, api, onCambio }: PropsVigente & { readonly pendiente: Promise<CierreDetalle> }) {
  const cierre = use(pendiente);
  const [anulando, setAnulando] = useState(false);
  const [motivo, setMotivo] = useState('');
  const { enviando, rechazo, setRechazo, ejecutar } = useEnvio('cierre', onCambio);

  function cerrarDialogo(): void {
    setAnulando(false);
    setMotivo('');
    setRechazo(null);
  }

  function anular(): void {
    const limpio = motivo.trim();
    if (limpio.length < 3) {
      setRechazo(FALTA_MOTIVO);
      return;
    }
    void ejecutar(() => api.anularCierre(cierreId, limpio), () => {
      cerrarDialogo();
      onCambio();
    });
  }

  return (
    <>
      <p>
        {cierre.cerrado_por_nombre !== null ? `Cerrada por ${cierre.cerrado_por_nombre} ` : 'Cerrada '}
        el {fechaCorta(cierre.cerrado_en)} a las {horaClinica(cierre.cerrado_en)}
      </p>
      {cierre.cuadra === true && <p className="aviso aviso-exito">El cierre cuadra</p>}
      {cierre.cuadra === false && (
        <div className="aviso aviso-error">
          <p>El cierre no cuadra con los movimientos del día</p>
          <ul className="lista-simple">
            {cierre.diferencias.map((d) => (
              <li key={`${d.concepto}-${d.medio}`}>
                {`${etiquetaLinea(d.concepto, d.medio)}: al cerrar ${pesos(d.total_cierre)} (${String(d.cantidad_cierre)}), ahora ${pesos(d.total_actual)} (${String(d.cantidad_actual)})`}
              </li>
            ))}
          </ul>
        </div>
      )}
      {esAdmin && (
        <button
          type="button"
          className="boton boton-secundario"
          onClick={() => {
            setRechazo(null);
            setAnulando(true);
          }}
        >
          Anular cierre
        </button>
      )}
      {anulando && (
        <Dialogo
          titulo={`¿Anular el cierre del ${etiquetaDiaLarga(dia)}?`}
          confirmar="Sí, anular el cierre"
          enviando={enviando}
          rechazo={rechazo}
          onVolver={cerrarDialogo}
          onConfirmar={anular}
        >
          <p>El día vuelve a estar abierto: se van a poder cargar y quitar movimientos. Queda registrado quién anuló y por qué.</p>
          <div className="campo">
            <label htmlFor="motivo-anulacion">Motivo de la anulación</label>
            <input
              id="motivo-anulacion"
              type="text"
              autoComplete="off"
              maxLength={300}
              value={motivo}
              onChange={(e) => {
                setMotivo(e.target.value);
              }}
            />
          </div>
        </Dialogo>
      )}
    </>
  );
}
