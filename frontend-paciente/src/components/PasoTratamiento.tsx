import { precioOrientativo } from '../lib/formato';
import type { Catalogo } from '../lib/tipos';

interface Props {
  readonly catalogo: Catalogo;
  readonly tratamientoId: number | null;
  readonly profesionalId: number | null;
  readonly onTratamiento: (id: number) => void;
  readonly onProfesional: (id: number) => void;
  readonly onContinuar: () => void;
  readonly puedeContinuar: boolean;
}

export function PasoTratamiento({
  catalogo,
  tratamientoId,
  profesionalId,
  onTratamiento,
  onProfesional,
  onContinuar,
  puedeContinuar,
}: Props) {
  const { tratamientos, profesionales } = catalogo;

  if (tratamientos.length === 0 || profesionales.length === 0) {
    return <p className="aviso">La clínica todavía no tiene horarios para reservar online. Volvé a probar más tarde.</p>;
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (puedeContinuar) onContinuar();
      }}
    >
      <fieldset className="grupo">
        <legend>Elegí el tratamiento</legend>
        {tratamientos.map((t) => (
          <label key={t.id} className={t.id === tratamientoId ? 'opcion seleccionada' : 'opcion'}>
            <input
              type="radio"
              name="tratamiento"
              checked={t.id === tratamientoId}
              onChange={() => {
                onTratamiento(t.id);
              }}
            />
            <span className="opcion-texto">
              <span className="opcion-titulo">{t.nombre}</span>
              <span className="opcion-detalle">
                {t.duracion_minutos} min · desde {precioOrientativo(t.precio_base)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      {profesionales.length > 1 ? (
        <fieldset className="grupo">
          <legend>Elegí con quién atenderte</legend>
          {profesionales.map((p) => (
            <label key={p.id} className={p.id === profesionalId ? 'opcion seleccionada' : 'opcion'}>
              <input
                type="radio"
                name="profesional"
                checked={p.id === profesionalId}
                onChange={() => {
                  onProfesional(p.id);
                }}
              />
              <span className="opcion-texto">
                <span className="opcion-titulo">{p.nombre}</span>
                {p.especialidad ? <span className="opcion-detalle">{p.especialidad}</span> : null}
              </span>
            </label>
          ))}
        </fieldset>
      ) : (
        <p className="nota">Te atiende {profesionales[0]?.nombre}.</p>
      )}

      <div className="acciones">
        <button type="submit" className="boton boton-primario" disabled={!puedeContinuar}>
          Ver horarios
        </button>
      </div>
    </form>
  );
}
