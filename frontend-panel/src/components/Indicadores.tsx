import { Suspense, startTransition, use, useState } from 'react';
import type { Api } from '../lib/api';
import { pesos, porcentaje } from '../lib/formato';
import { cantidad, iniciar } from '../lib/iniciar';
import { etiquetaDiaCorta, inicioSemana, sumarDias } from '../lib/tiempo';
import type { Ausentismo, Ocupacion, OcupacionDia, OcupacionSillon } from '../lib/tipos';
import { Cargando } from './Cargando';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';

interface Props {
  readonly api: Api;
  /** "Hoy" en la clínica ("YYYY-MM-DD"). */
  readonly hoy: string;
}

type Periodo = 'hoy' | 'semana' | 'mes';

const PERIODOS: readonly { readonly clave: Periodo; readonly etiqueta: string }[] = [
  { clave: 'hoy', etiqueta: 'Hoy' },
  { clave: 'semana', etiqueta: 'Esta semana' },
  { clave: 'mes', etiqueta: 'Últimos 30 días' },
];

/** Rango inclusivo del período; la ocupación admite hasta 31 días. */
function rangoDe(periodo: Periodo, hoy: string): readonly [string, string] {
  if (periodo === 'hoy') return [hoy, hoy];
  if (periodo === 'semana') {
    const lunes = inicioSemana(hoy);
    return [lunes, sumarDias(lunes, 6)];
  }
  return [sumarDias(hoy, -29), hoy];
}

export function Indicadores({ api, hoy }: Props) {
  const [periodo, setPeriodo] = useState<Periodo>('hoy');
  // Ocupación y ausentismo se piden juntos, en el mismo render (R2): ninguno espera al otro.
  const [ocupacion, setOcupacion] = useState(() => iniciar(() => api.ocupacion(...rangoDe('hoy', hoy))));
  const [ausentismo, setAusentismo] = useState(() => iniciar(() => api.ausentismo(...rangoDe('hoy', hoy))));

  function cambiar(nuevo: Periodo): void {
    const [desde, hasta] = rangoDe(nuevo, hoy);
    startTransition(() => {
      setPeriodo(nuevo);
      setOcupacion(iniciar(() => api.ocupacion(desde, hasta)));
      setAusentismo(iniciar(() => api.ausentismo(desde, hasta)));
    });
  }

  const [desde, hasta] = rangoDe(periodo, hoy);

  return (
    <section className="indicadores" aria-label="Indicadores">
      <div className="selector selector-periodo" role="group" aria-label="Período">
        {PERIODOS.map(({ clave, etiqueta }) => (
          <button
            key={clave}
            type="button"
            className={`selector-boton${periodo === clave ? ' activo' : ''}`}
            aria-pressed={periodo === clave}
            onClick={() => {
              cambiar(clave);
            }}
          >
            {etiqueta}
          </button>
        ))}
      </div>

      {/* Un bloque que falla no se lleva al otro: cada uno tiene su error y su reintento. */}
      <section className="bloque" aria-labelledby="titulo-ocupacion">
        <h2 id="titulo-ocupacion">Ocupación por sillón</h2>
        <ErrorBoundary
          key={`ocupacion-${desde}-${hasta}`}
          onReintentar={() => {
            setOcupacion(iniciar(() => api.ocupacion(desde, hasta)));
          }}
          fallback={(volver) => <ErrorCarga mensaje="No pudimos cargar la ocupación. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />}
        >
          <Suspense fallback={<Cargando texto="Cargando la ocupación…" />}>
            <BloqueOcupacion pendiente={ocupacion} />
          </Suspense>
        </ErrorBoundary>
      </section>

      <section className="bloque" aria-labelledby="titulo-ausentismo">
        <h2 id="titulo-ausentismo">Ausentismo</h2>
        <ErrorBoundary
          key={`ausentismo-${desde}-${hasta}`}
          onReintentar={() => {
            setAusentismo(iniciar(() => api.ausentismo(desde, hasta)));
          }}
          fallback={(volver) => <ErrorCarga mensaje="No pudimos cargar el ausentismo. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />}
        >
          <Suspense fallback={<Cargando texto="Cargando el ausentismo…" />}>
            <BloqueAusentismo pendiente={ausentismo} />
          </Suspense>
        </ErrorBoundary>
      </section>
    </section>
  );
}

// --- Ocupación -------------------------------------------------------------------------------------------------

function textoDeOcupacion(ocupados: number, atencion: number, turnos: number, pct: string | null, sinAtencion: string): string {
  if (pct === null) return sinAtencion;
  return `${porcentaje(pct)} ocupado · ${String(ocupados)} de ${String(atencion)} minutos · ${cantidad(turnos, 'turno', 'turnos')}`;
}

/** Porcentaje del período con un decimal, a partir de minutos enteros (no hay importes en juego). */
function porcentajeDe(ocupados: number, atencion: number): string | null {
  return atencion === 0 ? null : (Math.round((ocupados * 1000) / atencion) / 10).toFixed(1);
}

function LineaDia({ dia }: { readonly dia: OcupacionDia }) {
  return (
    <li>
      <span className="dia-etiqueta">{etiquetaDiaCorta(dia.dia)}</span>{' '}
      {textoDeOcupacion(dia.minutos_ocupados, dia.minutos_atencion, dia.turnos, dia.porcentaje, 'Sin atención ese día')}
    </li>
  );
}

function Sillon({ sillon }: { readonly sillon: OcupacionSillon }) {
  const { dias } = sillon;
  const unico = dias.length === 1 ? dias[0] : undefined;
  const ocupados = dias.reduce((suma, d) => suma + d.minutos_ocupados, 0);
  const atencion = dias.reduce((suma, d) => suma + d.minutos_atencion, 0);
  const turnos = dias.reduce((suma, d) => suma + d.turnos, 0);
  const perdidos = dias.reduce((suma, d) => suma + d.minutos_perdidos, 0);

  return (
    <section className="sillon" aria-label={`Ocupación de ${sillon.nombre}`}>
      <h3>{sillon.nombre}</h3>
      {sillon.estado !== 'activo' && <p className="nota">Este sillón está {sillon.estado === 'mantenimiento' ? 'en mantenimiento' : 'inactivo'}.</p>}
      {unico !== undefined ? (
        <p>{textoDeOcupacion(unico.minutos_ocupados, unico.minutos_atencion, unico.turnos, unico.porcentaje, 'Sin atención ese día')}</p>
      ) : (
        <>
          <p>{textoDeOcupacion(ocupados, atencion, turnos, porcentajeDe(ocupados, atencion), 'Sin atención en este período')}</p>
          <details>
            <summary>Detalle por día</summary>
            <ul className="lista-simple">
              {dias.map((d) => (
                <LineaDia key={d.dia} dia={d} />
              ))}
            </ul>
          </details>
        </>
      )}
      {perdidos > 0 && <p className="nota">{String(perdidos)} minutos perdidos por ausencias.</p>}
    </section>
  );
}

function BloqueOcupacion({ pendiente }: { readonly pendiente: Promise<Ocupacion> }) {
  const datos = use(pendiente);
  if (datos.sillones.length === 0) return <p className="vacio">No hay sillones activos para medir.</p>;
  return (
    <>
      {datos.sillones.map((s) => (
        <Sillon key={s.sillon_id} sillon={s} />
      ))}
    </>
  );
}

// --- Ausentismo ------------------------------------------------------------------------------------------------

function BloqueAusentismo({ pendiente }: { readonly pendiente: Promise<Ausentismo> }) {
  const datos = use(pendiente);
  const marcados = datos.atendidos + datos.ausentes;
  const { recupero } = datos;

  return (
    <>
      {datos.tasa === null ? (
        <p>Sin turnos marcados en este período</p>
      ) : (
        <>
          <p className="indicador">Tasa de ausentismo: {porcentaje(datos.tasa)}</p>
          <p>
            {cantidad(datos.ausentes, 'ausente', 'ausentes')} de {cantidad(marcados, 'turno marcado', 'turnos marcados')}
          </p>
        </>
      )}
      {datos.sin_marcar > 0 && (
        <p className="nota">
          {cantidad(datos.sin_marcar, 'turno sin marcar', 'turnos sin marcar')}: ya terminaron y siguen sin atendido ni ausente.
        </p>
      )}
      <p>
        Señas retenidas: {pesos(recupero.importe_retenido)} ({cantidad(recupero.senas_retenidas, 'seña', 'señas')})
      </p>
      {recupero.porcentaje !== null && (
        <p className="nota">En el {porcentaje(recupero.porcentaje)} de los turnos ausentes la seña quedó en la clínica.</p>
      )}
      {datos.por_profesional.length > 0 && (
        <ul className="lista-simple" aria-label="Ausentismo por profesional">
          {datos.por_profesional.map((p) => (
            <li key={p.profesional_id}>
              <span className="profesional-nombre">{p.nombre}</span>{' '}
              <span className="nota">
                {p.tasa === null ? 'sin turnos marcados' : `${porcentaje(p.tasa)} · ${cantidad(p.ausentes, 'ausente', 'ausentes')}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
