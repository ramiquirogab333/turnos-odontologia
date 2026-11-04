interface Props {
  readonly mensaje: string;
  readonly onReintentar: () => void;
}

export function ErrorCarga({ mensaje, onReintentar }: Props) {
  return (
    <div className="aviso aviso-error" role="alert">
      <p>{mensaje}</p>
      <button type="button" className="boton boton-secundario" onClick={onReintentar}>
        Reintentar
      </button>
    </div>
  );
}
