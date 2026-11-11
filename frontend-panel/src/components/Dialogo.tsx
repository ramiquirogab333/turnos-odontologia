import { useEffect, useId, useRef, type ReactNode } from 'react';

interface Props {
  readonly titulo: string;
  readonly confirmar: string;
  readonly enviando: boolean;
  /** Por qué no se pudo guardar (o qué falta completar); se lee como alerta. */
  readonly rechazo: string | null;
  readonly onConfirmar: () => void;
  readonly onVolver: () => void;
  readonly children?: ReactNode;
}

/** Confirmación de una acción seria: dice qué pasa antes de hacerlo, recibe el foco y se cierra con Escape. */
export function Dialogo({ titulo, confirmar, enviando, rechazo, onConfirmar, onVolver, children }: Props) {
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
            Volver
          </button>
          <button type="button" className="boton boton-primario" disabled={enviando} onClick={onConfirmar}>
            {enviando ? 'Guardando…' : confirmar}
          </button>
        </div>
      </div>
    </div>
  );
}
