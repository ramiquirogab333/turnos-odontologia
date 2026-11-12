import { Suspense, startTransition, use, useState } from 'react';
import type { Api } from '../lib/api';
import { iniciar } from '../lib/iniciar';
import { ErrorSesion } from '../lib/sesion';
import { diaClinica, etiquetaDiaCorta, horaClinica } from '../lib/tiempo';
import type { ErrorRecordatorio, MotivoFallo, Recordatorio } from '../lib/tipos';
import { Cargando } from './Cargando';
import { Dialogo } from './Dialogo';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';

interface Props {
  readonly api: Api;
}

const MOTIVOS: readonly { readonly valor: MotivoFallo; readonly etiqueta: string }[] = [
  { valor: 'numero_invalido', etiqueta: 'El número no es válido' },
  { valor: 'sin_whatsapp', etiqueta: 'No tiene WhatsApp' },
  { valor: 'otro', etiqueta: 'Otro motivo' },
];

const TEXTO_MOTIVO: Readonly<Record<string, string>> = {
  sin_telefono: 'Sin teléfono: cargá uno en la ficha o avisá por otro medio',
  numero_invalido: 'No se pudo enviar: el número no es válido',
  sin_whatsapp: 'No se pudo enviar: no tiene WhatsApp',
  otro: 'No se pudo enviar: otro motivo',
  error_proveedor: 'No se pudo enviar: falló el servicio de mensajes',
};

function etiquetaEstado(r: Recordatorio): string {
  switch (r.estado) {
    case 'pendiente':
      return 'Pendiente';
    case 'enviado':
      return 'Enviado';
    case 'confirmado':
      return 'Confirmado';
    case 'fallido':
      return (r.motivo !== null ? TEXTO_MOTIVO[r.motivo] : undefined) ?? 'No se pudo enviar';
  }
}

function mensajeDeError(error: ErrorRecordatorio): string {
  switch (error.tipo) {
    case 'no_vigente':
    case 'no_encontrado':
      return 'Ese recordatorio ya no corresponde: el turno se confirmó, se canceló o cambió de horario.';
    case 'sin_permiso':
      return 'No tenés permiso para esta acción.';
    case 'desconocido':
      return 'No pudimos registrar el envío. Revisá tu conexión e intentá de nuevo.';
  }
}

const sacar = (filas: readonly Recordatorio[], id: number): Recordatorio[] => filas.filter((f) => f.id !== id);
const reemplazar = (filas: readonly Recordatorio[], nueva: Recordatorio): Recordatorio[] =>
  filas.map((f) => (f.id === nueva.id ? nueva : f));

export function Recordatorios({ api }: Props) {
  const [lectura, setLectura] = useState(() => iniciar(() => api.recordatorios()));
  const [ronda, setRonda] = useState(0);

  function recargar(): void {
    startTransition(() => {
      setLectura(iniciar(() => api.recordatorios()));
      setRonda((r) => r + 1);
    });
  }

  return (
    <section className="recordatorios" aria-label="Recordatorios">
      <div className="barra">
        <button type="button" className="boton boton-secundario" onClick={recargar}>
          Actualizar
        </button>
      </div>
      <ErrorBoundary
        onReintentar={() => {
          setLectura(iniciar(() => api.recordatorios()));
          setRonda((r) => r + 1);
        }}
        fallback={(volver) => (
          <ErrorCarga mensaje="No pudimos cargar los recordatorios. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />
        )}
      >
        <Suspense fallback={<Cargando texto="Cargando los recordatorios…" />}>
          <Contenido key={ronda} api={api} lectura={lectura} />
        </Suspense>
      </ErrorBoundary>
    </section>
  );
}

function Contenido({ api, lectura }: { readonly api: Api; readonly lectura: Promise<readonly Recordatorio[]> }) {
  const inicial = use(lectura);
  const [filas, setFilas] = useState<readonly Recordatorio[]>(inicial);
  const [errores, setErrores] = useState<Readonly<Record<number, string>>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const [fallando, setFallando] = useState<Recordatorio | null>(null);

  const porEnviar = filas.filter((f) => f.estado === 'pendiente' || f.estado === 'fallido');
  const enviados = filas.filter((f) => f.estado === 'enviado');

  function sinError(id: number): void {
    setErrores((e) => Object.fromEntries(Object.entries(e).filter(([k]) => k !== String(id))));
  }

  async function registrarEnvio(fila: Recordatorio): Promise<void> {
    sinError(fila.id);
    try {
      const r = await api.marcarRecordatorioEnviado(fila.id);
      if (r.ok) {
        setFilas((actuales) => reemplazar(actuales, r.valor));
      } else if (r.error.tipo === 'no_vigente' || r.error.tipo === 'no_encontrado') {
        setFilas((actuales) => sacar(actuales, fila.id));
        setAviso(mensajeDeError(r.error));
      } else {
        setErrores((e) => ({ ...e, [fila.id]: mensajeDeError(r.error) }));
      }
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      setErrores((e) => ({ ...e, [fila.id]: mensajeDeError({ tipo: 'desconocido' }) }));
    }
  }

  return (
    <>
      {aviso !== null && (
        <p className="aviso aviso-error" role="alert">
          {aviso}
        </p>
      )}
      {porEnviar.length === 0 ? (
        <p className="vacio">No hay recordatorios por enviar</p>
      ) : (
        <ul className="lista-pendientes">
          {porEnviar.map((fila) => (
            <Fila key={fila.id} fila={fila} error={errores[fila.id] ?? null} onAbrir={registrarEnvio} onFallo={setFallando} />
          ))}
        </ul>
      )}
      {enviados.length > 0 && (
        <>
          <h3>Enviados</h3>
          <ul className="lista-pendientes">
            {enviados.map((fila) => (
              <Fila key={fila.id} fila={fila} error={errores[fila.id] ?? null} onAbrir={registrarEnvio} onFallo={setFallando} />
            ))}
          </ul>
        </>
      )}
      {fallando !== null && (
        <DialogoFallo
          fila={fallando}
          api={api}
          onCerrar={() => {
            setFallando(null);
          }}
          onHecho={(nueva) => {
            setFilas((actuales) => reemplazar(actuales, nueva));
            setFallando(null);
          }}
          onNoVigente={(error) => {
            setFilas((actuales) => sacar(actuales, fallando.id));
            setAviso(mensajeDeError(error));
            setFallando(null);
          }}
        />
      )}
    </>
  );
}

interface PropsFila {
  readonly fila: Recordatorio;
  readonly error: string | null;
  readonly onAbrir: (fila: Recordatorio) => Promise<void>;
  readonly onFallo: (fila: Recordatorio) => void;
}

function Fila({ fila, error, onAbrir, onFallo }: PropsFila) {
  const dia = etiquetaDiaCorta(diaClinica(fila.turno_inicio));
  return (
    <li className="pendiente">
      <p className="pendiente-titulo">{fila.contacto_nombre ?? 'Sin nombre'}</p>
      <p className="nota">
        {dia} · {horaClinica(fila.turno_inicio)}
      </p>
      <p className="nota">
        {fila.tratamiento} · {fila.profesional}
      </p>
      <p className="nota">
        <span className={`insignia insignia-recordatorio-${fila.estado}`}>{etiquetaEstado(fila)}</span>
      </p>
      {error !== null && (
        <div className="aviso aviso-error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="boton boton-secundario"
            onClick={() => {
              void onAbrir(fila);
            }}
          >
            Reintentar registro
          </button>
        </div>
      )}
      <div className="acciones-turno">
        {fila.link !== null && (
          // El toque abre WhatsApp (comportamiento del enlace) y, sin bloquearlo, registra el envío.
          <a
            className="boton boton-primario"
            href={fila.link}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => {
              void onAbrir(fila);
            }}
          >
            Abrir WhatsApp
          </a>
        )}
        {fila.estado !== 'fallido' && (
          <button
            type="button"
            className="boton boton-secundario"
            onClick={() => {
              onFallo(fila);
            }}
          >
            No se pudo enviar
          </button>
        )}
      </div>
    </li>
  );
}

interface PropsDialogo {
  readonly fila: Recordatorio;
  readonly api: Api;
  readonly onCerrar: () => void;
  readonly onHecho: (nueva: Recordatorio) => void;
  readonly onNoVigente: (error: ErrorRecordatorio) => void;
}

function DialogoFallo({ fila, api, onCerrar, onHecho, onNoVigente }: PropsDialogo) {
  const [motivo, setMotivo] = useState<MotivoFallo | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [rechazo, setRechazo] = useState<string | null>(null);

  async function confirmar(): Promise<void> {
    if (enviando) return;
    if (motivo === null) {
      setRechazo('Elegí un motivo.');
      return;
    }
    setEnviando(true);
    setRechazo(null);
    try {
      const r = await api.marcarRecordatorioFallido(fila.id, motivo);
      if (r.ok) onHecho(r.valor);
      else if (r.error.tipo === 'no_vigente' || r.error.tipo === 'no_encontrado') onNoVigente(r.error);
      else {
        setEnviando(false);
        setRechazo(mensajeDeError(r.error));
      }
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      setEnviando(false);
      setRechazo(mensajeDeError({ tipo: 'desconocido' }));
    }
  }

  return (
    <Dialogo
      titulo={`¿No se pudo avisar a ${fila.contacto_nombre ?? 'esta persona'}?`}
      confirmar="Marcar como no enviado"
      enviando={enviando}
      rechazo={rechazo}
      onVolver={onCerrar}
      onConfirmar={() => void confirmar()}
    >
      <fieldset className="campo">
        <legend>Motivo</legend>
        {MOTIVOS.map((m) => (
          <label key={m.valor} className="opcion">
            <input
              type="radio"
              name="motivo-fallo"
              value={m.valor}
              checked={motivo === m.valor}
              onChange={() => {
                setMotivo(m.valor);
              }}
            />{' '}
            {m.etiqueta}
          </label>
        ))}
      </fieldset>
    </Dialogo>
  );
}
