import { useEffect, useRef } from 'react';
import { diaClinica, etiquetaDiaLarga, horaClinica } from '../lib/tiempo';
import type { Profesional, ReservaCreada, Tratamiento } from '../lib/tipos';

interface Props {
  readonly reserva: ReservaCreada;
  readonly tratamiento: Tratamiento;
  readonly profesional: Profesional;
  readonly onNueva: () => void;
}

export function Confirmacion({ reserva, tratamiento, profesional, onNueva }: Props) {
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
        {etiquetaDiaLarga(diaClinica(reserva.inicio))}, {horaClinica(reserva.inicio)} a {horaClinica(reserva.fin)}
      </p>
      <p className="nota">
        {tratamiento.nombre} con {profesional.nombre}. Hora de Buenos Aires.
      </p>
      <div className="codigo">
        <span>Tu código de gestión</span>
        <strong>{reserva.codigo_gestion}</strong>
      </div>
      <p>Guardá el código. La clínica te confirma el turno por WhatsApp.</p>
      <div className="acciones">
        <button type="button" className="boton boton-secundario" onClick={onNueva}>
          Reservar otro turno
        </button>
      </div>
    </section>
  );
}
