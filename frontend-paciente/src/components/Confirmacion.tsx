import { useEffect, useRef } from 'react';
import { diaClinica, etiquetaDiaLarga, horaClinica } from '../lib/tiempo';

interface Props {
  readonly inicio: string;
  readonly fin: string;
  readonly codigoGestion: string;
  readonly tratamientoNombre: string;
  readonly profesionalNombre: string;
  readonly onNueva: () => void;
}

export function Confirmacion({ inicio, fin, codigoGestion, tratamientoNombre, profesionalNombre, onNueva }: Props) {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    titulo.current?.focus();
  }, []);

  return (
    <section aria-labelledby="titulo-confirmacion" className="confirmacion">
      <h2 id="titulo-confirmacion" ref={titulo} tabIndex={-1}>
        Turno reservado
      </h2>
      <p>
        {etiquetaDiaLarga(diaClinica(inicio))}, {horaClinica(inicio)} a {horaClinica(fin)}
      </p>
      <p className="nota">
        {tratamientoNombre} con {profesionalNombre}. Hora de Buenos Aires.
      </p>
      <div className="codigo">
        <span>Tu código de gestión</span>
        <strong>{codigoGestion}</strong>
      </div>
      <p>Guardá el código. La clínica te confirma el turno por WhatsApp.</p>
      <p className="nota">Podés cancelar o cambiar el horario hasta 24 h antes.</p>
      <div className="acciones">
        <a className="boton boton-primario" href={`/gestionar#${encodeURIComponent(codigoGestion)}`}>
          Gestionar mi turno
        </a>
        <button type="button" className="boton boton-secundario" onClick={onNueva}>
          Reservar otro turno
        </button>
      </div>
    </section>
  );
}
