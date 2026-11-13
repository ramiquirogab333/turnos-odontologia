import { Suspense, use, useEffect, useRef, useState, type FormEvent } from 'react';
import { cancelarTurno, consultarGestion, obtenerDisponibilidad, reprogramarTurno, type ResultadoGestion } from '../lib/api';
import { leerCodigoDelHash } from '../lib/codigo';
import { montoExacto } from '../lib/formato';
import { diaClinica, etiquetaDiaLarga, horaClinica, hoyClinica, sumarDias } from '../lib/tiempo';
import type { Alternativa, ErrorGestion, GestionTurno as Gestion, Slot } from '../lib/tipos';
import { Cargando } from './Cargando';
import { PasoHorario } from './PasoHorario';

const DIAS_DE_BUSQUEDA = 14;

function momento(iso: string): string {
  return `${etiquetaDiaLarga(diaClinica(iso))} a las ${horaClinica(iso)}`;
}

function textoFueraDePlazo(limite: string | null): string {
  const hasta = limite === null ? '' : ` El límite era el ${momento(limite)}.`;
  return `Ya no podés cancelar ni cambiar el turno online porque faltan menos de 24 h.${hasta} Comunicate con la clínica.`;
}

function mensajeDeError(error: ErrorGestion): string {
  switch (error.tipo) {
    case 'fuera_de_plazo':
      return textoFueraDePlazo(error.limite_cambios);
    case 'turno_no_modificable':
      return 'Este turno ya no se puede modificar.';
    case 'sena_pendiente':
      return 'Tu turno todavía no está confirmado. Cancelalo y reservá otro horario.';
    case 'turno_iniciado':
      return 'Este turno ya empezó.';
    case 'no_encontrado':
      return 'No encontramos un turno con ese código. Revisá que esté bien escrito.';
    case 'horario_invalido':
    case 'limite':
    case 'desconocido':
      return error.mensaje;
    case 'conflicto':
      return 'Ese horario ya no está disponible.';
  }
}

type Vista =
  | { readonly tipo: 'detalle' }
  | { readonly tipo: 'confirmar_cancelacion' }
  | { readonly tipo: 'cancelado' }
  | { readonly tipo: 'horarios' }
  | { readonly tipo: 'confirmar_cambio' }
  | { readonly tipo: 'reprogramado'; readonly inicio: string; readonly fin: string };

function Cabecera({ gestion }: { readonly gestion: Gestion }) {
  return (
    <div className="resumen">
      <p>
        <strong>{etiquetaDiaLarga(diaClinica(gestion.inicio))}</strong>, {horaClinica(gestion.inicio)} a {horaClinica(gestion.fin)}
      </p>
      <p className="nota">
        {gestion.tratamiento.nombre} con {gestion.profesional.nombre}. Hora de Buenos Aires.
      </p>
      {gestion.sena !== null && gestion.estado !== 'cancelado' ? (
        <p className="nota">
          Seña: {montoExacto(gestion.sena.monto)} ({gestion.sena.estado === 'acreditado' ? 'acreditada' : 'pendiente'})
        </p>
      ) : null}
    </div>
  );
}

function Vacio({ children }: { readonly children: string }) {
  return (
    <p className="aviso aviso-error" role="alert">
      {children}
    </p>
  );
}

function Gestionar({ gestion, codigo }: { readonly gestion: Gestion; readonly codigo: string }) {
  const [vista, setVista] = useState<Vista>({ tipo: 'detalle' });
  const [slots, setSlots] = useState<Promise<Slot[]> | null>(null);
  const [elegido, setElegido] = useState<Slot | null>(null);
  const [error, setError] = useState<ErrorGestion | null>(null);
  const [enviando, setEnviando] = useState(false);
  const titulo = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    titulo.current?.focus();
  }, [vista.tipo]);

  function pedirHorarios(): void {
    const hoy = hoyClinica(new Date());
    setSlots(
      obtenerDisponibilidad({
        profesionalId: gestion.profesional.id,
        tratamientoId: gestion.tratamiento.id,
        desde: hoy,
        hasta: sumarDias(hoy, DIAS_DE_BUSQUEDA),
      }),
    );
  }

  function irA(siguiente: Vista): void {
    setError(null);
    setVista(siguiente);
  }

  async function cancelar(): Promise<void> {
    if (enviando) return;
    setEnviando(true);
    const r = await cancelarTurno(codigo);
    setEnviando(false);
    if (r.ok) irA({ tipo: 'cancelado' });
    else {
      setError(r.error);
      setVista({ tipo: 'detalle' });
    }
  }

  async function confirmarCambio(): Promise<void> {
    if (enviando || elegido === null) return;
    setEnviando(true);
    setError(null);
    const r = await reprogramarTurno(codigo, elegido.inicio);
    setEnviando(false);
    if (r.ok) {
      setVista({ tipo: 'reprogramado', inicio: r.reprogramacion.inicio, fin: r.reprogramacion.fin });
      return;
    }
    setError(r.error);
    if (r.error.tipo === 'conflicto') pedirHorarios();
    else if (r.error.tipo !== 'horario_invalido') setVista({ tipo: 'detalle' });
  }

  function elegirAlternativa(a: Alternativa): void {
    setElegido({ inicio: a.inicio, fin: a.fin, profesional_id: gestion.profesional.id, sillon_id: a.sillon_id });
    setError(null);
  }

  if (vista.tipo === 'cancelado') {
    return (
      <section className="confirmacion" aria-labelledby="titulo-gestion">
        <h2 id="titulo-gestion" ref={titulo} tabIndex={-1}>
          Turno cancelado
        </h2>
        <p>Tu turno del {momento(gestion.inicio)} quedó cancelado.</p>
        {gestion.sena?.estado === 'acreditado' ? (
          <p className="nota">La clínica te va a devolver la seña de {montoExacto(gestion.sena.monto)}.</p>
        ) : (
          <p className="nota">No se te cobró nada.</p>
        )}
      </section>
    );
  }

  if (vista.tipo === 'reprogramado') {
    return (
      <section className="confirmacion" aria-labelledby="titulo-gestion">
        <h2 id="titulo-gestion" ref={titulo} tabIndex={-1}>
          Turno reprogramado
        </h2>
        <p>
          {etiquetaDiaLarga(diaClinica(vista.inicio))}, {horaClinica(vista.inicio)} a {horaClinica(vista.fin)}
        </p>
        <p className="nota">
          {gestion.tratamiento.nombre} con {gestion.profesional.nombre}. Hora de Buenos Aires. Tu seña sigue acreditada.
        </p>
        <p className="nota">Tu código de gestión es el mismo. Si necesitás otro cambio, tenés que hacerlo con 24 h de anticipación.</p>
      </section>
    );
  }

  const alternativas = error?.tipo === 'conflicto' ? error.alternativas : [];

  return (
    <section aria-labelledby="titulo-gestion" className="espera">
      <h2 id="titulo-gestion" ref={titulo} tabIndex={-1}>
        {vista.tipo === 'horarios' || vista.tipo === 'confirmar_cambio' ? 'Elegí el nuevo horario' : 'Gestionar mi turno'}
      </h2>

      {error !== null && error.tipo !== 'conflicto' ? <Vacio>{mensajeDeError(error)}</Vacio> : null}

      {vista.tipo === 'detalle' || vista.tipo === 'confirmar_cancelacion' ? (
        <>
          <Cabecera gestion={gestion} />
          {gestion.puede_cancelar || gestion.puede_reprogramar ? (
            <p className="nota">
              Podés cancelar o cambiar el horario hasta el {momento(gestion.limite_cambios)}.
            </p>
          ) : null}
          {gestion.motivo_no_cancelable === 'fuera_de_plazo' ? <Vacio>{textoFueraDePlazo(gestion.limite_cambios)}</Vacio> : null}
          {gestion.motivo_no_cancelable === 'turno_no_modificable' ? (
            <p className="aviso">Este turno ya no se puede modificar.</p>
          ) : null}
          {gestion.motivo_no_reprogramable === 'sena_pendiente' ? (
            <p className="aviso">Tu turno todavía no está confirmado. Cancelalo y reservá otro horario.</p>
          ) : null}
        </>
      ) : null}

      {vista.tipo === 'detalle' && (gestion.puede_cancelar || gestion.puede_reprogramar) ? (
        <div className="acciones acciones-columna">
          {gestion.puede_reprogramar ? (
            <button
              type="button"
              className="boton boton-primario"
              onClick={() => {
                setElegido(null);
                pedirHorarios();
                irA({ tipo: 'horarios' });
              }}
            >
              Cambiar horario
            </button>
          ) : null}
          {gestion.puede_cancelar ? (
            <button
              type="button"
              className="boton boton-secundario"
              onClick={() => {
                irA({ tipo: 'confirmar_cancelacion' });
              }}
            >
              Cancelar turno
            </button>
          ) : null}
        </div>
      ) : null}

      {vista.tipo === 'confirmar_cancelacion' ? (
        <div role="alertdialog" aria-labelledby="titulo-cancelar" aria-describedby="texto-cancelar" className="aviso">
          <h3 id="titulo-cancelar" className="subtitulo">
            ¿Cancelar este turno?
          </h3>
          <p id="texto-cancelar">
            {gestion.sena?.estado === 'acreditado'
              ? `La clínica te va a devolver la seña de ${montoExacto(gestion.sena.monto)}.`
              : 'No se te cobra nada.'}
          </p>
          <div className="acciones acciones-columna">
            <button
              type="button"
              className="boton boton-primario"
              disabled={enviando}
              onClick={() => {
                void cancelar();
              }}
            >
              Sí, cancelar el turno
            </button>
            <button
              type="button"
              className="boton boton-secundario"
              onClick={() => {
                irA({ tipo: 'detalle' });
              }}
            >
              Mantener el turno
            </button>
          </div>
        </div>
      ) : null}

      {vista.tipo === 'horarios' && slots !== null ? (
        <Suspense fallback={<Cargando texto="Buscando horarios libres…" />}>
          <PasoHorario
            slots={slots}
            elegido={elegido}
            onElegir={setElegido}
            onContinuar={() => {
              irA({ tipo: 'confirmar_cambio' });
            }}
            onVolver={() => {
              irA({ tipo: 'detalle' });
            }}
          />
        </Suspense>
      ) : null}

      {vista.tipo === 'confirmar_cambio' && elegido !== null ? (
        <>
          {error?.tipo === 'conflicto' ? (
            <div className="aviso aviso-error" role="alert">
              <p>Ese horario ya no está disponible.{alternativas.length > 0 ? ' Elegí uno de estos horarios libres:' : ' Elegí otro día.'}</p>
              {alternativas.length > 0 ? (
                <ul className="alternativas">
                  {alternativas.map((a) => (
                    <li key={a.inicio}>
                      <button
                        type="button"
                        className="boton boton-secundario"
                        onClick={() => {
                          elegirAlternativa(a);
                        }}
                      >
                        {momento(a.inicio)}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <button
                type="button"
                className="boton boton-texto"
                onClick={() => {
                  irA({ tipo: 'horarios' });
                }}
              >
                Ver otros días
              </button>
            </div>
          ) : null}
          <div className="resumen">
            <p>
              <strong>Nuevo horario:</strong> {momento(elegido.inicio)}
            </p>
            <p className="nota">Después de este cambio solo vas a poder cambiarlo si faltan 24 h o más.</p>
          </div>
          <div className="acciones acciones-doble">
            <button
              type="button"
              className="boton boton-secundario"
              onClick={() => {
                irA({ tipo: 'horarios' });
              }}
            >
              Volver
            </button>
            <button
              type="button"
              className="boton boton-primario"
              disabled={enviando}
              onClick={() => {
                void confirmarCambio();
              }}
            >
              Confirmar cambio
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}

function Consulta({ consulta, codigo }: { readonly consulta: Promise<ResultadoGestion>; readonly codigo: string }) {
  const r = use(consulta);
  if (!r.ok) return <Vacio>{mensajeDeError(r.error)}</Vacio>;
  return <Gestionar gestion={r.gestion} codigo={codigo} />;
}

function PedirCodigo({ onCodigo }: { readonly onCodigo: (codigo: string) => void }) {
  const [texto, setTexto] = useState('');
  function enviar(e: FormEvent): void {
    e.preventDefault();
    const limpio = texto.trim();
    if (limpio !== '') onCodigo(limpio);
  }
  return (
    <form className="espera" onSubmit={enviar}>
      <h2>Gestionar mi turno</h2>
      <p>Pegá el código de gestión que recibiste al reservar.</p>
      <div className="campo">
        <label htmlFor="codigo-gestion">Código de gestión</label>
        <input
          id="codigo-gestion"
          type="text"
          inputMode="text"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value);
          }}
        />
      </div>
      <div className="acciones">
        <button type="submit" className="boton boton-primario">
          Ver mi turno
        </button>
      </div>
    </form>
  );
}

export function GestionTurno() {
  const [codigo, setCodigo] = useState<string | null>(leerCodigoDelHash);
  const [consulta, setConsulta] = useState<Promise<ResultadoGestion> | null>(() =>
    codigo === null ? null : consultarGestion(codigo),
  );

  // El código queda solo en memoria: se saca del fragmento para que no se copie ni se guarde en el historial.
  useEffect(() => {
    if (window.location.hash !== '') window.history.replaceState(null, '', window.location.pathname + window.location.search);
  }, []);

  if (codigo === null || consulta === null) {
    return (
      <PedirCodigo
        onCodigo={(c) => {
          setCodigo(c);
          setConsulta(consultarGestion(c));
        }}
      />
    );
  }

  return (
    <Suspense fallback={<Cargando texto="Buscando tu turno…" />}>
      <Consulta consulta={consulta} codigo={codigo} />
    </Suspense>
  );
}
