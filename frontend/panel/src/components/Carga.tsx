import { Suspense, use, type ReactNode } from 'react';
import { ErrorApiPanel } from '../lib/api';
import { Cargando } from './Cargando';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';
import { SinAcceso, SinPaciente } from './MensajesPaciente';

interface Props<T> {
  readonly pendiente: Promise<T>;
  readonly textoCarga: string;
  /** Qué no se pudo cargar (se lee como alerta, con «Reintentar»). */
  readonly mensajeError: string;
  /** Vuelve a pedir el recurso: el padre reemplaza la promesa. */
  readonly onReintentar: () => void;
  readonly volverA?: string;
  readonly children: (datos: T) => ReactNode;
}

function Lector<T>({ pendiente, children }: { readonly pendiente: Promise<T>; readonly children: (datos: T) => ReactNode }) {
  return <>{children(use(pendiente))}</>;
}

/**
 * Límite de carga de un recurso del detalle: `Suspense` + `ErrorBoundary`. El 403 `paciente_ajeno` y el 404 se explican
 * con su mensaje (sin «Reintentar»: no se arreglan reintentando); cualquier otra falla ofrece «Reintentar».
 */
export function Carga<T>({ pendiente, textoCarga, mensajeError, onReintentar, volverA = '#/agenda', children }: Props<T>) {
  return (
    <ErrorBoundary
      onReintentar={onReintentar}
      fallback={(reintentar, error) => {
        if (error instanceof ErrorApiPanel && error.status === 403 && error.motivo === 'paciente_ajeno') {
          return <SinAcceso volverA={volverA} />;
        }
        if (error instanceof ErrorApiPanel && error.status === 404) return <SinPaciente />;
        return <ErrorCarga mensaje={mensajeError} onReintentar={reintentar} />;
      }}
    >
      <Suspense fallback={<Cargando texto={textoCarga} />}>
        <Lector pendiente={pendiente}>{children}</Lector>
      </Suspense>
    </ErrorBoundary>
  );
}
