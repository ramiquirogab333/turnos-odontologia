import { Suspense, useState } from 'react';
import { Cargando } from './components/Cargando';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ErrorCarga } from './components/ErrorCarga';
import { EsperaAcreditacion } from './components/EsperaAcreditacion';
import { ConfirmarTurno, RUTA_CONFIRMAR } from './components/ConfirmarTurno';
import { GestionTurno } from './components/GestionTurno';
import { Reserva } from './components/Reserva';
import { borrarPendiente, leerPendiente, type SenaPendiente } from './lib/almacen';
import type { Catalogo } from './lib/tipos';

interface Props {
  /** Promesa ya iniciada (R2: la carga arranca antes del primer render). */
  readonly inicial: Promise<Catalogo>;
  readonly recargar: () => Promise<Catalogo>;
}

/** Retorno del checkout de Mercado Pago: `/?pago=retorno&turno=ID` (el código de gestión viene del sessionStorage). */
type Retorno = { readonly tipo: 'espera'; readonly pendiente: SenaPendiente } | { readonly tipo: 'sin_datos' };

function leerRetorno(): Retorno | null {
  const params = new URLSearchParams(window.location.search);
  if (params.get('pago') !== 'retorno') return null;
  const pendiente = leerPendiente();
  if (pendiente !== null && pendiente.turnoId === Number(params.get('turno'))) return { tipo: 'espera', pendiente };
  return { tipo: 'sin_datos' };
}

function limpiarRetorno(): void {
  borrarPendiente();
  window.history.replaceState(null, '', window.location.pathname);
}

/** Ruta de gestión del turno: `/gestionar#<código>` (C-07). */
export const RUTA_GESTION = '/gestionar';

export function App({ inicial, recargar }: Props) {
  const [catalogo, setCatalogo] = useState(inicial);
  const [ronda, setRonda] = useState(0);
  const [retorno, setRetorno] = useState<Retorno | null>(leerRetorno);

  if (window.location.pathname === RUTA_CONFIRMAR) {
    return (
      <main className="app">
        <header className="cabecera">
          <h1>Tu turno</h1>
        </header>
        <ConfirmarTurno />
      </main>
    );
  }

  if (window.location.pathname === RUTA_GESTION) {
    return (
      <main className="app">
        <header className="cabecera">
          <h1>Tu turno</h1>
        </header>
        <GestionTurno />
      </main>
    );
  }

  if (retorno !== null) {
    const empezarDeNuevo = (): void => {
      limpiarRetorno();
      setRetorno(null);
    };
    return (
      <main className="app">
        <header className="cabecera">
          <h1>Reservá tu turno</h1>
        </header>
        {retorno.tipo === 'espera' ? (
          <EsperaAcreditacion
            turnoId={retorno.pendiente.turnoId}
            codigoGestion={retorno.pendiente.codigoGestion}
            onNueva={empezarDeNuevo}
          />
        ) : (
          <section className="espera" aria-labelledby="titulo-sin-datos">
            <h2 id="titulo-sin-datos">No encontramos tu reserva en este dispositivo</h2>
            <p>Si ya pagaste, la clínica te confirma el turno por WhatsApp apenas se acredite el pago.</p>
            <div className="acciones">
              <button type="button" className="boton boton-primario" onClick={empezarDeNuevo}>
                Reservar un turno
              </button>
            </div>
          </section>
        )}
      </main>
    );
  }

  return (
    <main className="app">
      <header className="cabecera">
        <h1>Reservá tu turno</h1>
      </header>
      <ErrorBoundary
        onReintentar={() => {
          setCatalogo(recargar());
        }}
        fallback={(reintentar, error) => <ErrorCarga mensaje={error.message} onReintentar={reintentar} />}
      >
        <Suspense fallback={<Cargando texto="Cargando tratamientos…" />}>
          <Reserva
            key={ronda}
            catalogo={catalogo}
            onNueva={() => {
              setRonda((r) => r + 1);
            }}
          />
        </Suspense>
      </ErrorBoundary>
    </main>
  );
}
