import { Suspense, startTransition, use, useState } from 'react';
import type { Api } from '../lib/api';
import { iniciar } from '../lib/iniciar';
import type { ResultadoGoogle } from '../lib/ruta';
import { ErrorSesion } from '../lib/sesion';
import { diaClinica, etiquetaDiaCorta, horaClinica } from '../lib/tiempo';
import type { AccionConflicto, ConexionGoogle, ConflictoGoogle, ErrorGoogle, EstadoConexion } from '../lib/tipos';
import { Cargando } from './Cargando';
import { Dialogo } from './Dialogo';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';

interface Props {
  readonly api: Api;
  /** Recepción y admin resuelven conflictos; la odontóloga los ve sin acciones (C-08 O5, C-10 O12). */
  readonly puedeResolver: boolean;
  readonly esAdmin: boolean;
  readonly esOdontologa: boolean;
  /** Resultado de la vuelta de Google (`?resultado=` del hash). */
  readonly resultado: ResultadoGoogle | null;
  /** Lleva el navegador a Google; se inyecta para poder probarlo sin navegar. */
  readonly irAUrl?: (url: string) => void;
}

const ETIQUETA_CONEXION: Readonly<Record<EstadoConexion, string>> = {
  sin_conectar: 'Sin conectar',
  pendiente: 'Esperando la autorización de Google',
  activa: 'Conectado',
  revocada: 'Se perdió el acceso',
  desconectada: 'Desconectado',
};

const ETIQUETA_ACCION: Readonly<Record<AccionConflicto, string>> = {
  restaurar_en_google: 'Restaurar en Google',
  desvincular: 'Desvincular',
  revisado: 'Marcar como revisado',
};

const EXPLICACION_ACCION: Readonly<Record<AccionConflicto, string>> = {
  restaurar_en_google:
    'El evento vuelve al horario del turno en el próximo ciclo de sincronización (si lo borraron, se crea de nuevo). El turno no cambia.',
  desvincular:
    'El sistema deja de actualizar el evento de este turno en Google. El evento queda donde está y el turno no cambia.',
  revisado: 'Cierra este aviso. El turno y el evento de Google quedan como están.',
};

const MENSAJE_RESULTADO: Readonly<Record<ResultadoGoogle, string>> = {
  conectado: 'Google Calendar quedó conectado. Los turnos reservados van a aparecer en tu calendario.',
  error_autorizacion: 'No se pudo conectar Google Calendar. Volvé a intentarlo',
  permiso_denegado: 'No se conectó Google Calendar: no se dio el permiso',
};

function mensajeIniciar(error: ErrorGoogle): string {
  switch (error.tipo) {
    case 'no_configurado':
      return 'Google Calendar todavía no está configurado en este entorno. Pedile a quien administra el sistema que cargue las credenciales.';
    case 'conexion_activa':
      return 'Google Calendar ya está conectado. Actualizá la pantalla para verlo.';
    case 'sin_permiso':
      return 'No tenés permiso para conectar Google Calendar con este usuario.';
    default:
      return 'No pudimos iniciar la conexión con Google. Revisá tu conexión e intentá de nuevo.';
  }
}

function mensajeResolver(error: ErrorGoogle): string {
  switch (error.tipo) {
    case 'sin_permiso':
      return 'No tenés permiso para resolver conflictos.';
    case 'accion_no_valida':
      return 'Esa acción no corresponde a este tipo de conflicto.';
    default:
      return 'No pudimos resolver el conflicto. Revisá tu conexión e intentá de nuevo.';
  }
}

function horaYDia(iso: string): string {
  return `${etiquetaDiaCorta(diaClinica(iso))} ${horaClinica(iso)}`;
}

/** "Sistema: 10:00–10:30 / Google: 12:00–12:30": el criterio visible de RN-GC-02 en una sola línea. */
function textoHorarios(c: ConflictoGoogle): string {
  const sistema = `${horaClinica(c.sistema_inicio)}–${horaClinica(c.sistema_fin)}`;
  const google =
    c.google_inicio !== null && c.google_fin !== null
      ? `${horaClinica(c.google_inicio)}–${horaClinica(c.google_fin)}`
      : 'el evento ya no está';
  return `Sistema: ${sistema} / Google: ${google}`;
}

type Lectura = Promise<readonly [readonly ConexionGoogle[], readonly ConflictoGoogle[]]>;

/** Conexiones y conflictos se piden juntos (Promise.all, R2): ninguno espera al otro. */
const leer = (api: Api): Lectura => iniciar(() => Promise.all([api.conexionesGoogle(), api.conflictosGoogle()]));

export function GoogleCalendar({ api, puedeResolver, esAdmin, esOdontologa, resultado, irAUrl = (u) => window.location.assign(u) }: Props) {
  const [lectura, setLectura] = useState<Lectura>(() => leer(api));
  const [ronda, setRonda] = useState(0);

  function recargar(): void {
    startTransition(() => {
      setLectura(leer(api));
      setRonda((r) => r + 1);
    });
  }

  return (
    <section className="google-calendar" aria-label="Google Calendar">
      {resultado !== null && (
        <p className={resultado === 'conectado' ? 'aviso aviso-exito' : 'aviso aviso-error'} role={resultado === 'conectado' ? 'status' : 'alert'}>
          {MENSAJE_RESULTADO[resultado]}
        </p>
      )}
      <ErrorBoundary
        onReintentar={() => {
          setLectura(leer(api));
          setRonda((r) => r + 1);
        }}
        fallback={(volver) => (
          <ErrorCarga mensaje="No pudimos cargar Google Calendar. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />
        )}
      >
        <Suspense fallback={<Cargando texto="Cargando Google Calendar…" />}>
          <Contenido
            key={ronda}
            api={api}
            lectura={lectura}
            puedeResolver={puedeResolver}
            puedeConectar={esOdontologa && !puedeResolver}
            esAdmin={esAdmin}
            irAUrl={irAUrl}
            onRecargar={recargar}
          />
        </Suspense>
      </ErrorBoundary>
    </section>
  );
}

interface PropsContenido {
  readonly api: Api;
  readonly lectura: Lectura;
  readonly puedeResolver: boolean;
  readonly puedeConectar: boolean;
  readonly esAdmin: boolean;
  readonly irAUrl: (url: string) => void;
  readonly onRecargar: () => void;
}

function Contenido({ api, lectura, puedeResolver, puedeConectar, esAdmin, irAUrl, onRecargar }: PropsContenido) {
  const [conexiones, inicialConflictos] = use(lectura);
  const [conflictos, setConflictos] = useState<readonly ConflictoGoogle[]>(inicialConflictos);
  const [aviso, setAviso] = useState<string | null>(null);
  const [desconectando, setDesconectando] = useState<ConexionGoogle | null>(null);
  const [resolviendo, setResolviendo] = useState<{ readonly conflicto: ConflictoGoogle; readonly accion: AccionConflicto } | null>(null);
  const ultima = conexiones.find((c) => c.estado === 'activa' && c.ultima_sync_ok_en !== null)?.ultima_sync_ok_en ?? null;

  return (
    <>
      {aviso !== null && (
        <p className="aviso aviso-error" role="alert">
          {aviso}
        </p>
      )}
      <h2>Conexión</h2>
      <ul className="lista-pendientes">
        {conexiones.map((c) => (
          <FilaConexion
            key={c.profesional_id}
            conexion={c}
            puedeConectar={puedeConectar}
            puedeDesconectar={puedeConectar || esAdmin}
            onConectar={async () => {
              setAviso(null);
              try {
                const r = await api.iniciarGoogle();
                if (r.ok) irAUrl(r.valor.url_autorizacion);
                else setAviso(mensajeIniciar(r.error));
              } catch (error) {
                if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
                setAviso(mensajeIniciar({ tipo: 'desconocido' }));
              }
            }}
            onDesconectar={() => {
              setDesconectando(c);
            }}
          />
        ))}
      </ul>

      <h2>Conflictos</h2>
      {conflictos.length === 0 ? (
        <div className="vacio">
          <p>No hay conflictos con Google Calendar</p>
          {ultima !== null && <p className="nota">Última sincronización correcta: {horaYDia(ultima)}</p>}
        </div>
      ) : (
        <ul className="lista-pendientes">
          {conflictos.map((c) => (
            <li key={c.id} className="pendiente conflicto">
              <p className="pendiente-titulo">
                {c.tratamiento} · {c.profesional_nombre}
              </p>
              <p className="nota">{etiquetaDiaCorta(diaClinica(c.sistema_inicio))}</p>
              <p>{c.criterio}</p>
              <p className="conflicto-horarios">{textoHorarios(c)}</p>
              {puedeResolver && c.acciones.length > 0 && (
                <div className="acciones-turno">
                  {c.acciones.map((accion) => (
                    <button
                      key={accion}
                      type="button"
                      className={`boton ${accion === 'restaurar_en_google' ? 'boton-primario' : 'boton-secundario'}`}
                      onClick={() => {
                        setResolviendo({ conflicto: c, accion });
                      }}
                    >
                      {ETIQUETA_ACCION[accion]}
                    </button>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {desconectando !== null && (
        <DialogoDesconectar
          api={api}
          conexion={desconectando}
          onCerrar={() => {
            setDesconectando(null);
          }}
          onHecho={() => {
            setDesconectando(null);
            onRecargar();
          }}
        />
      )}
      {resolviendo !== null && (
        <DialogoResolver
          api={api}
          conflicto={resolviendo.conflicto}
          accion={resolviendo.accion}
          onCerrar={() => {
            setResolviendo(null);
          }}
          onHecho={(id) => {
            setConflictos((actuales) => actuales.filter((c) => c.id !== id));
            setResolviendo(null);
          }}
          onYaCerrado={(id, mensaje) => {
            setConflictos((actuales) => actuales.filter((c) => c.id !== id));
            setAviso(mensaje);
            setResolviendo(null);
          }}
        />
      )}
    </>
  );
}

interface PropsFilaConexion {
  readonly conexion: ConexionGoogle;
  readonly puedeConectar: boolean;
  readonly puedeDesconectar: boolean;
  readonly onConectar: () => Promise<void>;
  readonly onDesconectar: () => void;
}

function FilaConexion({ conexion, puedeConectar, puedeDesconectar, onConectar, onDesconectar }: PropsFilaConexion) {
  const [enviando, setEnviando] = useState(false);
  const activa = conexion.estado === 'activa';
  return (
    <li className="pendiente conexion-google">
      <p className="pendiente-titulo">{conexion.profesional_nombre}</p>
      <p className="nota">
        <span className={`insignia insignia-conexion-${conexion.estado}`}>{ETIQUETA_CONEXION[conexion.estado]}</span>
      </p>
      {activa && conexion.cuenta_email !== null && <p className="nota">Conectado como {conexion.cuenta_email}</p>}
      {activa && conexion.ultima_sync_ok_en !== null && (
        <p className="nota">Última sincronización: {horaYDia(conexion.ultima_sync_ok_en)}</p>
      )}
      {conexion.indicacion !== null && <p className="nota">{conexion.indicacion}</p>}
      {conexion.conflictos_abiertos > 0 && (
        <p className="nota">
          {conexion.conflictos_abiertos === 1 ? '1 conflicto abierto' : `${String(conexion.conflictos_abiertos)} conflictos abiertos`}
        </p>
      )}
      <div className="acciones-turno">
        {puedeConectar && !activa && (
          <button
            type="button"
            className="boton boton-primario"
            disabled={enviando}
            onClick={() => {
              setEnviando(true);
              void onConectar().finally(() => {
                setEnviando(false);
              });
            }}
          >
            Conectar Google Calendar
          </button>
        )}
        {puedeDesconectar && activa && (
          <button type="button" className="boton boton-secundario" onClick={onDesconectar}>
            Desconectar
          </button>
        )}
      </div>
    </li>
  );
}

interface PropsDialogoDesconectar {
  readonly api: Api;
  readonly conexion: ConexionGoogle;
  readonly onCerrar: () => void;
  readonly onHecho: () => void;
}

function DialogoDesconectar({ api, conexion, onCerrar, onHecho }: PropsDialogoDesconectar) {
  const [enviando, setEnviando] = useState(false);
  const [rechazo, setRechazo] = useState<string | null>(null);

  async function confirmar(): Promise<void> {
    if (enviando) return;
    setEnviando(true);
    setRechazo(null);
    try {
      const r = await api.desconectarGoogle(conexion.profesional_id);
      if (r.ok || r.error.tipo === 'no_encontrado') {
        onHecho();
        return;
      }
      setEnviando(false);
      setRechazo(
        r.error.tipo === 'sin_permiso'
          ? 'No tenés permiso para desconectar esta cuenta.'
          : 'No pudimos desconectar Google Calendar. Revisá tu conexión e intentá de nuevo.',
      );
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      setEnviando(false);
      setRechazo('No pudimos desconectar Google Calendar. Revisá tu conexión e intentá de nuevo.');
    }
  }

  return (
    <Dialogo
      titulo="¿Desconectar Google Calendar?"
      confirmar="Desconectar Google Calendar"
      enviando={enviando}
      rechazo={rechazo}
      onVolver={onCerrar}
      onConfirmar={() => void confirmar()}
    >
      <p>
        Los turnos ya cargados siguen en tu Google Calendar, pero el sistema deja de actualizarlos. Podés volver a conectar cuando
        quieras. Ningún turno cambia.
      </p>
    </Dialogo>
  );
}

interface PropsDialogoResolver {
  readonly api: Api;
  readonly conflicto: ConflictoGoogle;
  readonly accion: AccionConflicto;
  readonly onCerrar: () => void;
  readonly onHecho: (id: number) => void;
  readonly onYaCerrado: (id: number, mensaje: string) => void;
}

function DialogoResolver({ api, conflicto, accion, onCerrar, onHecho, onYaCerrado }: PropsDialogoResolver) {
  const [enviando, setEnviando] = useState(false);
  const [rechazo, setRechazo] = useState<string | null>(null);

  async function confirmar(): Promise<void> {
    if (enviando) return;
    setEnviando(true);
    setRechazo(null);
    try {
      const r = await api.resolverConflicto(conflicto.id, accion);
      if (r.ok) {
        onHecho(conflicto.id);
      } else if (r.error.tipo === 'conflicto_cerrado' || r.error.tipo === 'no_encontrado') {
        onYaCerrado(conflicto.id, 'Ese conflicto ya no está abierto: se resolvió o el turno se canceló.');
      } else {
        setEnviando(false);
        setRechazo(mensajeResolver(r.error));
      }
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      setEnviando(false);
      setRechazo(mensajeResolver({ tipo: 'desconocido' }));
    }
  }

  return (
    <Dialogo
      titulo={`${ETIQUETA_ACCION[accion]}: ${conflicto.tratamiento}`}
      confirmar={ETIQUETA_ACCION[accion]}
      enviando={enviando}
      rechazo={rechazo}
      onVolver={onCerrar}
      onConfirmar={() => void confirmar()}
    >
      <p className="conflicto-horarios">{textoHorarios(conflicto)}</p>
      <p>{EXPLICACION_ACCION[accion]}</p>
    </Dialogo>
  );
}
