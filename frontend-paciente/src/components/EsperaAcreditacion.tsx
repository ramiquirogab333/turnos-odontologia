import { useEffect, useRef, useState, type ReactNode } from 'react';
import { consultarSena } from '../lib/api';
import { borrarPendiente } from '../lib/almacen';
import type { EstadoSena } from '../lib/tipos';
import { Confirmacion } from './Confirmacion';

const INTERVALO_MS = 3_000;
const TOPE_MS = 120_000;

type Fase =
  | { readonly tipo: 'esperando' }
  | { readonly tipo: 'tope' }
  | { readonly tipo: 'no_encontrada' }
  | { readonly tipo: 'reservado'; readonly estado: EstadoSena }
  | { readonly tipo: 'vencida' }
  | { readonly tipo: 'a_reembolsar' }
  | { readonly tipo: 'en_revision' };

const ESTADOS_RESERVADOS: readonly string[] = ['reservado', 'confirmado', 'atendido'];

/** Decide si el estado que informa el servidor ya es definitivo para el paciente. */
function clasificar(estado: EstadoSena): Fase {
  if (ESTADOS_RESERVADOS.includes(estado.estado_turno)) return { tipo: 'reservado', estado };
  if (estado.estado_pago === 'a_reembolsar') return { tipo: 'a_reembolsar' };
  // Con un pago en revisión (RN-SN-09) el dinero pudo llegar: nunca se muestra "La reserva venció", ni siquiera
  // si el barrido ya canceló el turno.
  if (estado.estado_pago === 'en_revision') return { tipo: 'en_revision' };
  if (estado.vencida || estado.estado_turno === 'cancelado') return { tipo: 'vencida' };
  return { tipo: 'esperando' };
}

interface Props {
  readonly turnoId: number;
  readonly codigoGestion: string;
  readonly onNueva: () => void;
  /** Contenido que acompaña la espera (por ejemplo, los datos de la transferencia). */
  readonly encabezado?: ReactNode;
  readonly intervaloMs?: number;
  readonly topeMs?: number;
}

/**
 * Sondea un único recurso (`GET .../sena`) cada 3 s hasta 2 minutos: sin cascadas de fetch (R2).
 * Los errores de red no cortan el sondeo; solo un 404 o un estado terminal lo detienen.
 */
export function EsperaAcreditacion({
  turnoId,
  codigoGestion,
  onNueva,
  encabezado,
  intervaloMs = INTERVALO_MS,
  topeMs = TOPE_MS,
}: Props) {
  const [fase, setFase] = useState<Fase>({ tipo: 'esperando' });
  const [ronda, setRonda] = useState(0);
  const titulo = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let activo = true;
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    const arranque = Date.now();

    async function sondear(): Promise<void> {
      const r = await consultarSena(turnoId, codigoGestion);
      if (!activo) return;
      if (r.ok) {
        const siguiente = clasificar(r.estado);
        if (siguiente.tipo === 'en_revision') {
          setFase(siguiente); // no es terminal: la clínica puede acreditarlo, así que se sigue consultando
          if (Date.now() - arranque >= topeMs) return;
          temporizador = setTimeout(() => {
            void sondear();
          }, intervaloMs);
          return;
        }
        if (siguiente.tipo !== 'esperando') {
          setFase(siguiente);
          return;
        }
      } else if (r.error.tipo === 'no_encontrada') {
        setFase({ tipo: 'no_encontrada' });
        return;
      }
      if (Date.now() - arranque >= topeMs) {
        setFase({ tipo: 'tope' });
        return;
      }
      temporizador = setTimeout(() => {
        void sondear();
      }, intervaloMs);
    }

    void sondear();
    return () => {
      activo = false;
      if (temporizador !== undefined) clearTimeout(temporizador);
    };
  }, [turnoId, codigoGestion, intervaloMs, topeMs, ronda]);

  useEffect(() => {
    if (fase.tipo !== 'esperando') titulo.current?.focus();
    // Estado terminal: la seña pendiente guardada en el navegador ya no hace falta.
    if (['reservado', 'vencida', 'a_reembolsar', 'no_encontrada'].includes(fase.tipo)) borrarPendiente();
  }, [fase.tipo]);

  switch (fase.tipo) {
    case 'reservado':
      return (
        <Confirmacion
          inicio={fase.estado.inicio}
          fin={fase.estado.fin}
          codigoGestion={codigoGestion}
          tratamientoNombre={fase.estado.tratamiento_nombre}
          profesionalNombre={fase.estado.profesional_nombre}
          onNueva={onNueva}
        />
      );
    case 'vencida':
      return (
        <section aria-labelledby="titulo-espera" className="espera">
          <h2 id="titulo-espera" ref={titulo} tabIndex={-1}>
            La reserva venció
          </h2>
          <p>No se acreditó la seña a tiempo, así que liberamos el horario. Si ya pagaste, la clínica se comunica con vos.</p>
          <div className="acciones">
            <button type="button" className="boton boton-primario" onClick={onNueva}>
              Elegir otro horario
            </button>
          </div>
        </section>
      );
    case 'a_reembolsar':
      return (
        <section aria-labelledby="titulo-espera" className="espera">
          <h2 id="titulo-espera" ref={titulo} tabIndex={-1}>
            El horario se ocupó
          </h2>
          <p>Otra persona confirmó este horario antes que vos.</p>
          <p>La clínica se va a comunicar para devolverte la seña.</p>
          <div className="acciones">
            <button type="button" className="boton boton-primario" onClick={onNueva}>
              Elegir otro horario
            </button>
          </div>
        </section>
      );
    case 'en_revision':
      return (
        <section aria-labelledby="titulo-espera" className="espera">
          {encabezado}
          <h2 id="titulo-espera" ref={titulo} tabIndex={-1}>
            Estamos revisando tu pago
          </h2>
          <p>Recibimos tu pago, pero necesitamos verificarlo antes de confirmar el turno.</p>
          <p>La clínica se va a comunicar con vos.</p>
        </section>
      );
    case 'no_encontrada':
      return (
        <section aria-labelledby="titulo-espera" className="espera">
          <h2 id="titulo-espera" ref={titulo} tabIndex={-1}>
            No encontramos tu reserva
          </h2>
          <p>Revisá el código de gestión o reservá de nuevo.</p>
          <div className="acciones">
            <button type="button" className="boton boton-primario" onClick={onNueva}>
              Reservar un turno
            </button>
          </div>
        </section>
      );
    case 'tope':
      return (
        <section aria-labelledby="titulo-espera" className="espera">
          {encabezado}
          <h2 id="titulo-espera" ref={titulo} tabIndex={-1}>
            Seguimos esperando la acreditación
          </h2>
          <p>Todavía no recibimos la confirmación del pago. Puede demorar unos minutos. Tu turno no está confirmado hasta que se acredite.</p>
          <div className="acciones">
            <button
              type="button"
              className="boton boton-primario"
              onClick={() => {
                setFase({ tipo: 'esperando' });
                setRonda((r) => r + 1);
              }}
            >
              Revisar de nuevo
            </button>
          </div>
        </section>
      );
    case 'esperando':
      return (
        <section className="espera" aria-label="Estado del pago">
          {encabezado}
          <p className="estado-carga" role="status">
            Esperando la acreditación de tu pago…
          </p>
        </section>
      );
  }
}
