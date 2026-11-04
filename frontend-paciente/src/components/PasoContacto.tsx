import { useId } from 'react';
import type { ErrorApi } from '../lib/errores';
import { diaClinica, etiquetaDiaLarga, horaClinica } from '../lib/tiempo';
import type { Alternativa, Profesional, Slot, Tratamiento } from '../lib/tipos';
import { EJEMPLO_TELEFONO, validarNombre, validarTelefono } from '../lib/validacion';

interface Props {
  readonly tratamiento: Tratamiento;
  readonly profesional: Profesional;
  readonly slot: Slot;
  readonly nombre: string;
  readonly telefono: string;
  readonly intentado: boolean;
  readonly enviando: boolean;
  readonly error: ErrorApi | null;
  readonly aviso: string | null;
  readonly onNombre: (valor: string) => void;
  readonly onTelefono: (valor: string) => void;
  readonly onEnviar: () => void;
  readonly onVolver: () => void;
  readonly onOtroHorario: () => void;
  readonly onAlternativa: (alternativa: Alternativa) => void;
}

function etiquetaAlternativa(a: Alternativa): string {
  return `${etiquetaDiaLarga(diaClinica(a.inicio))}, ${horaClinica(a.inicio)}`;
}

function AvisoDeError({
  error,
  onOtroHorario,
  onAlternativa,
}: {
  readonly error: ErrorApi;
  readonly onOtroHorario: () => void;
  readonly onAlternativa: (a: Alternativa) => void;
}) {
  switch (error.tipo) {
    case 'conflicto':
      return (
        <div className="aviso aviso-error" role="alert">
          {error.alternativas.length > 0 ? (
            <>
              <p>Ese horario ya fue reservado por otra persona. Elegí uno de estos horarios libres:</p>
              <ul className="alternativas">
                {error.alternativas.map((a) => (
                  <li key={a.inicio}>
                    <button type="button" className="boton boton-secundario" onClick={() => { onAlternativa(a); }}>
                      {etiquetaAlternativa(a)}
                    </button>
                  </li>
                ))}
              </ul>
              <button type="button" className="boton boton-texto" onClick={onOtroHorario}>
                Ver otros días
              </button>
            </>
          ) : (
            <>
              <p>Ese horario ya fue reservado y no quedan horarios cercanos libres. Elegí otro día.</p>
              <button type="button" className="boton boton-secundario" onClick={onOtroHorario}>
                Elegir otro horario
              </button>
            </>
          )}
        </div>
      );
    case 'fuera_de_horario':
      return (
        <div className="aviso aviso-error" role="alert">
          <p>{error.mensaje}</p>
          <button type="button" className="boton boton-secundario" onClick={onOtroHorario}>
            Elegir otro horario
          </button>
        </div>
      );
    case 'validacion':
      return error.generales.length > 0 ? (
        <div className="aviso aviso-error" role="alert">
          {error.generales.map((g) => (
            <p key={g}>{g}</p>
          ))}
        </div>
      ) : null;
    case 'desconocido':
      return (
        <div className="aviso aviso-error" role="alert">
          <p>{error.mensaje}</p>
        </div>
      );
  }
}

export function PasoContacto(props: Props) {
  const { slot, nombre, telefono, intentado, enviando, error } = props;
  const id = useId();
  const idNombreError = `${id}-nombre-error`;
  const idTelefonoError = `${id}-telefono-error`;
  const idTelefonoAyuda = `${id}-telefono-ayuda`;

  const errorNombre =
    (error?.tipo === 'validacion' ? error.campos.nombre : undefined) ?? (intentado ? validarNombre(nombre) : null);
  const errorTelefono =
    (error?.tipo === 'validacion' ? error.campos.telefono : undefined) ?? (intentado ? validarTelefono(telefono) : null);

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        props.onEnviar();
      }}
    >
      <dl className="resumen">
        <div>
          <dt>Tratamiento</dt>
          <dd>
            {props.tratamiento.nombre} ({props.tratamiento.duracion_minutos} min)
          </dd>
        </div>
        <div>
          <dt>Profesional</dt>
          <dd>{props.profesional.nombre}</dd>
        </div>
        <div>
          <dt>Cuándo</dt>
          <dd>
            {etiquetaDiaLarga(diaClinica(slot.inicio))}, {horaClinica(slot.inicio)} a {horaClinica(slot.fin)}
            <span className="nota"> (hora de Buenos Aires)</span>
          </dd>
        </div>
      </dl>

      {props.aviso ? (
        <p className="aviso aviso-ok" role="status">
          {props.aviso}
        </p>
      ) : null}
      {error ? <AvisoDeError error={error} onOtroHorario={props.onOtroHorario} onAlternativa={props.onAlternativa} /> : null}

      <div className="campo">
        <label htmlFor={`${id}-nombre`}>Nombre completo</label>
        <input
          id={`${id}-nombre`}
          name="nombre"
          type="text"
          autoComplete="name"
          maxLength={200}
          value={nombre}
          aria-invalid={errorNombre ? true : undefined}
          aria-describedby={errorNombre ? idNombreError : undefined}
          onChange={(e) => {
            props.onNombre(e.target.value);
          }}
        />
        {errorNombre ? (
          <p className="campo-error" id={idNombreError}>
            {errorNombre}
          </p>
        ) : null}
      </div>

      <div className="campo">
        <label htmlFor={`${id}-telefono`}>Teléfono (WhatsApp)</label>
        <input
          id={`${id}-telefono`}
          name="telefono"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder={EJEMPLO_TELEFONO}
          value={telefono}
          aria-invalid={errorTelefono ? true : undefined}
          aria-describedby={errorTelefono ? idTelefonoError : idTelefonoAyuda}
          onChange={(e) => {
            props.onTelefono(e.target.value);
          }}
        />
        {errorTelefono ? (
          <p className="campo-error" id={idTelefonoError}>
            {errorTelefono}
          </p>
        ) : (
          <p className="nota" id={idTelefonoAyuda}>
            Con + y código de país. Te avisamos por WhatsApp a este número.
          </p>
        )}
      </div>

      <div className="acciones acciones-doble">
        <button type="button" className="boton boton-secundario" onClick={props.onVolver} disabled={enviando}>
          Volver
        </button>
        <button type="submit" className="boton boton-primario" disabled={enviando}>
          {enviando ? 'Reservando…' : 'Confirmar turno'}
        </button>
      </div>
    </form>
  );
}
