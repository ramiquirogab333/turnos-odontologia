import { Suspense, startTransition, use, useState } from 'react';
import type { Api } from '../lib/api';
import { iniciar } from '../lib/iniciar';
import { etiquetaDiaLarga, sumarDias } from '../lib/tiempo';
import type { CajaDia, Pendiente } from '../lib/tipos';
import { Cargando } from './Cargando';
import { CierreCaja } from './CierreCaja';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';
import { PendientesCaja } from './PendientesCaja';
import { ResumenCaja } from './ResumenCaja';

interface Props {
  readonly api: Api;
  /** "Hoy" en la clínica ("YYYY-MM-DD"). */
  readonly hoy: string;
  /** Solo el administrador puede anular un cierre. */
  readonly esAdmin: boolean;
}

export function Caja({ api, hoy, esAdmin }: Props) {
  const [dia, setDia] = useState(hoy);
  // La caja del día y los pendientes se piden en el mismo render, en paralelo (R2): ninguno espera al otro.
  const [cajaPendiente, setCajaPendiente] = useState(() => iniciar(() => api.caja(hoy)));
  const [pendientes, setPendientes] = useState(() => iniciar(() => api.pendientes()));

  function cambiarDia(nuevo: string): void {
    startTransition(() => {
      setDia(nuevo);
      setCajaPendiente(iniciar(() => api.caja(nuevo)));
    });
  }

  function recargar(): void {
    startTransition(() => {
      setCajaPendiente(iniciar(() => api.caja(dia)));
      setPendientes(iniciar(() => api.pendientes()));
    });
  }

  function reintentar(): void {
    setCajaPendiente(iniciar(() => api.caja(dia)));
    setPendientes(iniciar(() => api.pendientes()));
  }

  return (
    <section className="caja" aria-label="Caja">
      <div className="barra">
        <div className="navegacion">
          <button
            type="button"
            className="boton boton-secundario"
            aria-label="Día anterior"
            onClick={() => {
              cambiarDia(sumarDias(dia, -1));
            }}
          >
            ‹
          </button>
          <button
            type="button"
            className="boton boton-secundario"
            onClick={() => {
              cambiarDia(hoy);
            }}
          >
            Hoy
          </button>
          <button
            type="button"
            className="boton boton-secundario"
            aria-label="Día siguiente"
            disabled={dia >= hoy}
            onClick={() => {
              cambiarDia(sumarDias(dia, 1));
            }}
          >
            ›
          </button>
        </div>
      </div>
      <h2 className="fecha">{etiquetaDiaLarga(dia)}</h2>

      <ErrorBoundary
        onReintentar={reintentar}
        fallback={(volver) => <ErrorCarga mensaje="No pudimos cargar la caja. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />}
      >
        <Suspense fallback={<Cargando texto="Cargando la caja…" />}>
          <Contenido
            api={api}
            hoy={hoy}
            esAdmin={esAdmin}
            cajaPendiente={cajaPendiente}
            pendientes={pendientes}
            onCambio={recargar}
          />
        </Suspense>
      </ErrorBoundary>
    </section>
  );
}

interface PropsContenido {
  readonly api: Api;
  readonly hoy: string;
  readonly esAdmin: boolean;
  readonly cajaPendiente: Promise<CajaDia>;
  readonly pendientes: Promise<readonly Pendiente[]>;
  readonly onCambio: () => void;
}

/** Las dos lecturas se esperan juntas: si una falla no se muestra la otra a medias. */
function Contenido({ api, hoy, esAdmin, cajaPendiente, pendientes, onCambio }: PropsContenido) {
  const caja = use(cajaPendiente);
  const lista = use(pendientes);

  return (
    <>
      <p className="estado-caja">{caja.estado === 'cerrado' ? 'Caja cerrada' : 'Caja abierta'}</p>
      <ResumenCaja caja={caja} />
      <PendientesCaja pendientes={lista} api={api} onCambio={onCambio} />
      <CierreCaja key={`${caja.dia}-${String(caja.cierre_id)}`} caja={caja} hoy={hoy} esAdmin={esAdmin} api={api} onCambio={onCambio} />
    </>
  );
}
