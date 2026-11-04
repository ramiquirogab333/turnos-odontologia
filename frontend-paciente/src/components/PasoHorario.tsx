import { use, useMemo, useState } from 'react';
import { agruparPorDia, etiquetaDiaCorta, etiquetaDiaLarga, horaClinica } from '../lib/tiempo';
import type { Slot } from '../lib/tipos';

interface Props {
  readonly slots: Promise<Slot[]>;
  readonly elegido: Slot | null;
  readonly onElegir: (slot: Slot) => void;
  readonly onContinuar: () => void;
  readonly onVolver: () => void;
}

export function PasoHorario({ slots, elegido, onElegir, onContinuar, onVolver }: Props) {
  const lista = use(slots);
  const porDia = useMemo(() => agruparPorDia(lista), [lista]);
  const dias = useMemo(() => [...porDia.keys()], [porDia]);
  const [diaElegido, setDiaElegido] = useState<string | null>(null);
  const diaDelElegido = elegido ? dias.find((d) => porDia.get(d)?.some((s) => s.inicio === elegido.inicio)) : undefined;
  const dia = diaElegido ?? diaDelElegido ?? dias[0];

  if (dia === undefined) {
    return (
      <div>
        <p className="aviso">No hay horarios libres en los próximos días con este profesional.</p>
        <div className="acciones">
          <button type="button" className="boton boton-secundario" onClick={onVolver}>
            Cambiar tratamiento o profesional
          </button>
        </div>
      </div>
    );
  }

  const delDia = porDia.get(dia) ?? [];

  return (
    <div>
      <h3 className="subtitulo" id="titulo-dias">
        Día
      </h3>
      <div className="dias" role="group" aria-labelledby="titulo-dias">
        {dias.map((d) => (
          <button
            key={d}
            type="button"
            className={d === dia ? 'dia seleccionado' : 'dia'}
            aria-pressed={d === dia}
            aria-label={etiquetaDiaLarga(d)}
            onClick={() => {
              setDiaElegido(d);
            }}
          >
            {etiquetaDiaCorta(d)}
          </button>
        ))}
      </div>

      <h3 className="subtitulo" id="titulo-horas">
        Horarios del {etiquetaDiaLarga(dia)}
      </h3>
      <p className="nota">Hora de Buenos Aires.</p>
      <div className="horarios" role="group" aria-labelledby="titulo-horas">
        {delDia.map((s) => (
          <button
            key={s.inicio}
            type="button"
            className={s.inicio === elegido?.inicio ? 'horario seleccionado' : 'horario'}
            aria-pressed={s.inicio === elegido?.inicio}
            onClick={() => {
              onElegir(s);
            }}
          >
            {horaClinica(s.inicio)}
          </button>
        ))}
      </div>

      <div className="acciones acciones-doble">
        <button type="button" className="boton boton-secundario" onClick={onVolver}>
          Volver
        </button>
        <button type="button" className="boton boton-primario" disabled={elegido === null} onClick={onContinuar}>
          Continuar
        </button>
      </div>
    </div>
  );
}
