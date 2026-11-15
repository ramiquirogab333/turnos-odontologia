import { useEffect, useId, useRef, type ReactNode } from 'react';

interface Props {
  readonly titulo: string;
  readonly confirmar: string;
  /** Texto del botón que cierra sin hacer nada (por defecto «Volver»). */
  readonly volver?: string;
  readonly enviando: boolean;
  /** Mientras falte algo por completar el botón de confirmar queda apagado. */
  readonly confirmarDeshabilitado?: boolean;
  /** Por qué no se pudo guardar (o qué falta completar); se lee como alerta. */
  readonly rechazo: string | null;
  readonly onConfirmar: () => void;
  readonly onVolver: () => void;
  readonly children?: ReactNode;
}

/** Confirmación de una acción seria: dice qué pasa antes de hacerlo, recibe el foco y se cierra con Escape. */
export function Dialogo({ titulo, confirmar, volver = 'Volver', enviando, confirmarDeshabilitado = false, rechazo, onConfirmar, onVolver, children }: Props) {
  const idTitulo = useId();
  const tituloRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    tituloRef.current?.focus();
  }, []);

  return (
    <div className="velo">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        className="dialogo"
        onKeyDown={(e) => {
          if (e.key === 'Escape' && !enviando) onVolver();
        }}
      >
        <h2 id={idTitulo} ref={tituloRef} tabIndex={-1}>
          {titulo}
        </h2>
        {children}
        {rechazo !== null && (
          <p className="aviso aviso-error" role="alert">
            {rechazo}
          </p>
        )}
        <div className="acciones">
          <button type="button" className="boton boton-secundario" onClick={onVolver} disabled={enviando}>
            {volver}
          </button>
          <button type="button" className="boton boton-primario" disabled={enviando || confirmarDeshabilitado} onClick={onConfirmar}>
            {enviando ? 'Guardando…' : confirmar}
          </button>
        </div>
      </div>
    </div>
  );
}
