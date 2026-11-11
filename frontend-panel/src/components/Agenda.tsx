import { Suspense, startTransition, use, useEffect, useState } from 'react';
import { ErrorApiPanel, type Api } from '../lib/api';
import { iniciar } from '../lib/iniciar';
import { diaClinica, etiquetaDiaCorta, etiquetaDiaLarga, etiquetaSemana, inicioSemana, sumarDias } from '../lib/tiempo';
import type { Agenda as DatosAgenda, Consulta, Opciones, TurnoAgenda, Vista } from '../lib/tipos';
import { AltaManual } from './AltaManual';
import { Cargando } from './Cargando';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';
import { TarjetaTurno } from './TarjetaTurno';

interface Props {
  readonly api: Api;
  /** "Hoy" en la clínica ("YYYY-MM-DD"). */
  readonly hoy: string;
}

/** Semana en pantalla ancha: una grilla de lunes a domingo; en pantallas chicas, una lista agrupada por día. */
function useEscritorio(): boolean {
  const consulta = '(min-width: 1024px)';
  const [ancho, setAncho] = useState(() => typeof window.matchMedia === 'function' && window.matchMedia(consulta).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const medios = window.matchMedia(consulta);
    const alCambiar = (): void => {
      setAncho(medios.matches);
    };
    medios.addEventListener('change', alCambiar);
    return () => {
      medios.removeEventListener('change', alCambiar);
    };
  }, []);
  return ancho;
}

function mensajeDeError(error: Error): string {
  return error instanceof ErrorApiPanel && error.status === 403 && error.motivo !== null
    ? error.message
    : 'No pudimos cargar la agenda. Revisá tu conexión e intentá de nuevo.';
}

export function Agenda({ api, hoy }: Props) {
  const [consulta, setConsulta] = useState<Consulta>({ vista: 'dia', fecha: hoy, profesionalId: null, sillonId: null });
  // Agenda y opciones se piden en el mismo render, en paralelo (R2): ninguno espera al otro.
  const [opcionesPendientes, setOpcionesPendientes] = useState(() => iniciar(() => api.opciones()));
  const [agendaPendiente, setAgendaPendiente] = useState(() => iniciar(() => api.agenda(consulta)));

  function cambiar(cambios: Partial<Consulta>): void {
    const nueva = { ...consulta, ...cambios };
    startTransition(() => {
      setConsulta(nueva);
      setAgendaPendiente(iniciar(() => api.agenda(nueva)));
    });
  }

  function recargar(): void {
    startTransition(() => {
      setAgendaPendiente(iniciar(() => api.agenda(consulta)));
    });
  }

  function reintentar(): void {
    setOpcionesPendientes(iniciar(() => api.opciones()));
    setAgendaPendiente(iniciar(() => api.agenda(consulta)));
  }

  const paso = consulta.vista === 'dia' ? 1 : 7;
  const unidad = consulta.vista === 'dia' ? 'Día' : 'Semana';
  const etiqueta = consulta.vista === 'dia' ? etiquetaDiaLarga(consulta.fecha) : etiquetaSemana(consulta.fecha);

  return (
    <section className="agenda" aria-label="Agenda">
      <div className="barra">
        <div className="selector" role="group" aria-label="Vista">
          {(['dia', 'semana'] as const satisfies readonly Vista[]).map((vista) => (
            <button
              key={vista}
              type="button"
              className={`selector-boton${consulta.vista === vista ? ' activo' : ''}`}
              aria-pressed={consulta.vista === vista}
              onClick={() => {
                cambiar({ vista });
              }}
            >
              {vista === 'dia' ? 'Día' : 'Semana'}
            </button>
          ))}
        </div>
        <div className="navegacion">
          <button
            type="button"
            className="boton boton-secundario"
            aria-label={`${unidad} anterior`}
            onClick={() => {
              cambiar({ fecha: sumarDias(consulta.fecha, -paso) });
            }}
          >
            ‹
          </button>
          <button
            type="button"
            className="boton boton-secundario"
            onClick={() => {
              cambiar({ fecha: hoy });
            }}
          >
            Hoy
          </button>
          <button
            type="button"
            className="boton boton-secundario"
            aria-label={`${unidad} siguiente`}
            onClick={() => {
              cambiar({ fecha: sumarDias(consulta.fecha, paso) });
            }}
          >
            ›
          </button>
        </div>
      </div>
      <h2 className="fecha">{etiqueta}</h2>

      <ErrorBoundary
        onReintentar={reintentar}
        fallback={(reintentar, error) => <ErrorCarga mensaje={mensajeDeError(error)} onReintentar={reintentar} />}
      >
        <Suspense fallback={<Cargando texto="Cargando la agenda…" />}>
          <Contenido
            api={api}
            consulta={consulta}
            opcionesPendientes={opcionesPendientes}
            agendaPendiente={agendaPendiente}
            onFiltro={cambiar}
            onCambio={recargar}
          />
        </Suspense>
      </ErrorBoundary>
    </section>
  );
}

interface PropsContenido {
  readonly api: Api;
  readonly consulta: Consulta;
  readonly opcionesPendientes: Promise<Opciones>;
  readonly agendaPendiente: Promise<DatosAgenda>;
  readonly onFiltro: (cambios: Partial<Consulta>) => void;
  readonly onCambio: () => void;
}

function Contenido({ api, consulta, opcionesPendientes, agendaPendiente, onFiltro, onCambio }: PropsContenido) {
  const opciones = use(opcionesPendientes);
  const datos = use(agendaPendiente);
  const escritorio = useEscritorio();
  const [creando, setCreando] = useState(false);

  const principales = datos.turnos.filter((t) => t.bloquea_agenda);
  const preReservas = datos.turnos.filter((t) => !t.bloquea_agenda);
  const variasProfesionales = opciones.profesionales.length > 1;

  return (
    <>
      <div className="filtros">
        {variasProfesionales && (
          <div className="campo">
            <label htmlFor="filtro-profesional">Profesional</label>
            <select
              id="filtro-profesional"
              value={consulta.profesionalId ?? ''}
              onChange={(e) => {
                onFiltro({ profesionalId: e.target.value === '' ? null : Number(e.target.value) });
              }}
            >
              <option value="">Todos los profesionales</option>
              {opciones.profesionales.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </select>
          </div>
        )}
        {opciones.sillones.length > 1 && (
          <div className="campo">
            <label htmlFor="filtro-sillon">Sillón</label>
            <select
              id="filtro-sillon"
              value={consulta.sillonId ?? ''}
              onChange={(e) => {
                onFiltro({ sillonId: e.target.value === '' ? null : Number(e.target.value) });
              }}
            >
              <option value="">Todos los sillones</option>
              {opciones.sillones.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                </option>
              ))}
            </select>
          </div>
        )}
        {opciones.puede_escribir && (
          <button
            type="button"
            className="boton boton-primario"
            onClick={() => {
              setCreando(true);
            }}
          >
            Nuevo turno
          </button>
        )}
      </div>

      {principales.length === 0 && preReservas.length === 0 ? (
        <p className="vacio">
          No hay turnos para {consulta.vista === 'dia' ? 'este día' : 'esta semana'}.
          {opciones.puede_escribir ? ' Usá «Nuevo turno» para cargar uno.' : ''}
        </p>
      ) : consulta.vista === 'dia' ? (
        <ListaTurnos
          nombre="Turnos del día"
          turnos={principales}
          api={api}
          onCambio={onCambio}
          conProfesional={variasProfesionales}
        />
      ) : escritorio ? (
        <GrillaSemana fecha={consulta.fecha} turnos={principales} api={api} onCambio={onCambio} />
      ) : (
        <ListaSemana turnos={principales} api={api} onCambio={onCambio} conProfesional={variasProfesionales} />
      )}

      {preReservas.length > 0 && (
        <section className="banda" aria-labelledby="titulo-banda">
          <h2 id="titulo-banda">Pre-reservas sin pagar</h2>
          <p className="nota">No ocupan horario: si no pagan la seña a tiempo, se liberan solas.</p>
          <ul className="lista-turnos" aria-label="Pre-reservas">
            {preReservas.map((t) => (
              <TarjetaTurno key={t.id} turno={t} api={api} onCambio={onCambio} conProfesional={variasProfesionales} />
            ))}
          </ul>
        </section>
      )}

      {creando && (
        <AltaManual
          api={api}
          opciones={opciones}
          fechaInicial={consulta.fecha}
          onCreado={onCambio}
          onCerrar={() => {
            setCreando(false);
          }}
        />
      )}
    </>
  );
}

interface PropsLista {
  readonly turnos: readonly TurnoAgenda[];
  readonly api: Api;
  readonly onCambio: () => void;
  readonly conProfesional: boolean;
}

function ListaTurnos({ nombre, turnos, api, onCambio, conProfesional }: PropsLista & { readonly nombre: string }) {
  if (turnos.length === 0) return null;
  return (
    <ul className="lista-turnos" aria-label={nombre}>
      {turnos.map((t) => (
        <TarjetaTurno key={t.id} turno={t} api={api} onCambio={onCambio} conProfesional={conProfesional} />
      ))}
    </ul>
  );
}

function agruparPorDia(turnos: readonly TurnoAgenda[]): Map<string, TurnoAgenda[]> {
  const grupos = new Map<string, TurnoAgenda[]>();
  for (const t of turnos) {
    const dia = diaClinica(t.inicio);
    const lista = grupos.get(dia);
    if (lista) lista.push(t);
    else grupos.set(dia, [t]);
  }
  return grupos;
}

function ListaSemana({ turnos, api, onCambio, conProfesional }: PropsLista) {
  return (
    <>
      {[...agruparPorDia(turnos)].map(([dia, delDia]) => (
        <section key={dia} className="dia-semana">
          <h3>{etiquetaDiaLarga(dia)}</h3>
          <ListaTurnos nombre={`Turnos del ${etiquetaDiaLarga(dia)}`} turnos={delDia} api={api} onCambio={onCambio} conProfesional={conProfesional} />
        </section>
      ))}
    </>
  );
}

function GrillaSemana({ fecha, turnos, api, onCambio }: Omit<PropsLista, 'conProfesional'> & { readonly fecha: string }) {
  const lunes = inicioSemana(fecha);
  const dias = Array.from({ length: 7 }, (_, i) => sumarDias(lunes, i));
  const porDia = agruparPorDia(turnos);
  return (
    <div className="grilla-contenedor">
      <table className="grilla" aria-label={etiquetaSemana(fecha)}>
        <thead>
          <tr>
            {dias.map((dia) => (
              <th key={dia} scope="col">
                {etiquetaDiaCorta(dia)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {dias.map((dia) => (
              <td key={dia}>
                <ListaTurnos nombre={`Turnos del ${etiquetaDiaLarga(dia)}`} turnos={porDia.get(dia) ?? []} api={api} onCambio={onCambio} conProfesional />
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
