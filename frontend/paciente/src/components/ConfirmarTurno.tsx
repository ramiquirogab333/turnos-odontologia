import { Suspense, use, useEffect, useRef, useState } from 'react';
import { confirmarTurno, consultarGestion, type ResultadoGestion } from '../lib/api';
import { leerCodigoDelHash, sacarCodigoDeLaUrl } from '../lib/codigo';
import { diaClinica, etiquetaDiaLarga, etiquetaDiaNumerica, horaClinica } from '../lib/tiempo';
import type { ErrorGestion, GestionTurno } from '../lib/tipos';
import { Cargando } from './Cargando';

/** Ruta de confirmación de asistencia: `/confirmar#<código>` (C-09). */
export const RUTA_CONFIRMAR = '/confirmar';

function enlaceGestion(codigo: string): string {
  return `/gestionar#${encodeURIComponent(codigo)}`;
}

function mensajeDeError(error: ErrorGestion): string {
  switch (error.tipo) {
    case 'no_encontrado':
      return 'No encontramos un turno con ese código. Revisá que el enlace esté completo.';
    case 'turno_iniciado':
      return 'Este turno ya empezó, por eso no se puede confirmar.';
    case 'turno_no_modificable':
      return 'Este turno ya no se puede confirmar.';
    case 'sena_pendiente':
      return 'Tu turno todavía no está confirmado: falta que se acredite la seña.';
    case 'horario_invalido':
    case 'limite':
    case 'desconocido':
      return error.mensaje;
    case 'fuera_de_plazo':
    case 'conflicto':
      return 'No pudimos completar la operación. Intentá de nuevo en unos minutos.';
  }
}

/** Errores definitivos: reintentar no cambia nada, así que el botón desaparece. */
function esDefinitivo(error: ErrorGestion): boolean {
  return error.tipo !== 'desconocido' && error.tipo !== 'limite';
}

function Datos({ gestion }: { readonly gestion: GestionTurno }) {
  return (
    <div className="resumen">
      <p>
        <strong>{etiquetaDiaLarga(diaClinica(gestion.inicio))}</strong>, {horaClinica(gestion.inicio)} a {horaClinica(gestion.fin)}
      </p>
      <p className="nota">
        {gestion.tratamiento.nombre} con {gestion.profesional.nombre}. Hora de Buenos Aires.
      </p>
    </div>
  );
}

function Aviso({ children }: { readonly children: string }) {
  return (
    <p className="aviso aviso-error" role="alert">
      {children}
    </p>
  );
}

function VerGestion({ codigo }: { readonly codigo: string }) {
  return (
    <div className="acciones">
      <a className="boton boton-secundario" href={enlaceGestion(codigo)}>
        Gestionar mi turno
      </a>
    </div>
  );
}

type Vista =
  | { readonly tipo: 'inicial' }
  | { readonly tipo: 'confirmado'; readonly inicio: string }
  | { readonly tipo: 'rechazado'; readonly error: ErrorGestion };

function Confirmar({ gestion, codigo }: { readonly gestion: GestionTurno; readonly codigo: string }) {
  const [vista, setVista] = useState<Vista>({ tipo: 'inicial' });
  const [error, setError] = useState<ErrorGestion | null>(null);
  const [enviando, setEnviando] = useState(false);
  const titulo = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    titulo.current?.focus();
  }, [vista.tipo]);

  // Solo el toque en el botón confirma: una vista previa de WhatsApp o abrir el enlace no envía nada.
  async function confirmar(): Promise<void> {
    if (enviando) return;
    setEnviando(true);
    setError(null);
    const r = await confirmarTurno(codigo);
    setEnviando(false);
    if (r.ok) setVista({ tipo: 'confirmado', inicio: r.confirmacion.inicio });
    else if (esDefinitivo(r.error)) setVista({ tipo: 'rechazado', error: r.error });
    else setError(r.error);
  }

  if (vista.tipo === 'confirmado') {
    const dia = diaClinica(vista.inicio);
    return (
      <section className="confirmacion" aria-labelledby="titulo-confirmar">
        <h2 id="titulo-confirmar" ref={titulo} tabIndex={-1}>
          ¡Listo! Confirmaste tu turno del {etiquetaDiaNumerica(dia)} a las {horaClinica(vista.inicio)}
        </h2>
        <p className="nota">
          {gestion.tratamiento.nombre} con {gestion.profesional.nombre}. Hora de Buenos Aires.
        </p>
        <p className="nota">Si necesitás cancelar o cambiar el horario, hacelo con 24 h de anticipación.</p>
        <VerGestion codigo={codigo} />
      </section>
    );
  }

  if (vista.tipo === 'rechazado') {
    return (
      <section className="espera" aria-labelledby="titulo-confirmar">
        <h2 id="titulo-confirmar" ref={titulo} tabIndex={-1}>
          Este turno ya no se puede confirmar
        </h2>
        <Aviso>{mensajeDeError(vista.error)}</Aviso>
        <Datos gestion={gestion} />
        <VerGestion codigo={codigo} />
      </section>
    );
  }

  if (gestion.puede_confirmar) {
    return (
      <section className="espera" aria-labelledby="titulo-confirmar">
        <h2 id="titulo-confirmar" ref={titulo} tabIndex={-1}>
          Confirmar asistencia
        </h2>
        {error !== null ? <Aviso>{mensajeDeError(error)}</Aviso> : null}
        <Datos gestion={gestion} />
        <div className="acciones acciones-columna">
          <button
            type="button"
            className="boton boton-primario"
            disabled={enviando}
            onClick={() => {
              void confirmar();
            }}
          >
            Confirmar asistencia
          </button>
          <a className="boton boton-secundario" href={enlaceGestion(codigo)}>
            Gestionar mi turno
          </a>
        </div>
      </section>
    );
  }

  const yaConfirmado = gestion.motivo_no_confirmable === 'ya_confirmado';
  return (
    <section className="espera" aria-labelledby="titulo-confirmar">
      <h2 id="titulo-confirmar" ref={titulo} tabIndex={-1}>
        {yaConfirmado ? 'Ya confirmaste tu turno' : 'Este turno ya no se puede confirmar'}
      </h2>
      {!yaConfirmado && gestion.motivo_no_confirmable !== null ? (
        <Aviso>{mensajeDeError({ tipo: gestion.motivo_no_confirmable })}</Aviso>
      ) : null}
      <Datos gestion={gestion} />
      <VerGestion codigo={codigo} />
    </section>
  );
}

function Consulta({ consulta, codigo }: { readonly consulta: Promise<ResultadoGestion>; readonly codigo: string }) {
  const r = use(consulta);
  if (!r.ok) return <Aviso>{mensajeDeError(r.error)}</Aviso>;
  return <Confirmar gestion={r.gestion} codigo={codigo} />;
}

export function ConfirmarTurno() {
  const [codigo] = useState<string | null>(leerCodigoDelHash);
  const [consulta] = useState<Promise<ResultadoGestion> | null>(() => (codigo === null ? null : consultarGestion(codigo)));

  // El código queda solo en memoria: se saca del fragmento para que no se copie ni se guarde en el historial.
  useEffect(sacarCodigoDeLaUrl, []);

  if (codigo === null || consulta === null) {
    return (
      <section className="espera" aria-labelledby="titulo-sin-codigo">
        <h2 id="titulo-sin-codigo">Confirmar asistencia</h2>
        <p>Abrí el enlace del mensaje que te mandó la clínica para confirmar tu turno.</p>
      </section>
    );
  }

  return (
    <Suspense fallback={<Cargando texto="Buscando tu turno…" />}>
      <Consulta consulta={consulta} codigo={codigo} />
    </Suspense>
  );
}
