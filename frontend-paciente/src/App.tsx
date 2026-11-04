import { Suspense, useState } from 'react';
import { Cargando } from './components/Cargando';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ErrorCarga } from './components/ErrorCarga';
import { Reserva } from './components/Reserva';
import type { Catalogo } from './lib/tipos';

interface Props {
  /** Promesa ya iniciada (R2: la carga arranca antes del primer render). */
  readonly inicial: Promise<Catalogo>;
  readonly recargar: () => Promise<Catalogo>;
}

export function App({ inicial, recargar }: Props) {
  const [catalogo, setCatalogo] = useState(inicial);
  const [ronda, setRonda] = useState(0);

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
