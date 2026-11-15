import { useCallback, useEffect, useRef, useState } from 'react';
import type { Api } from '../lib/api';
import { iniciar, resuelta } from '../lib/iniciar';
import { hashDePaciente, leerDetallePaciente, type PestanaPaciente } from '../lib/ruta';
import type { CualquierPresupuesto, Ficha, OdontogramaVigente, PacienteDetalle, Rol } from '../lib/tipos';
import { CabeceraPaciente } from './CabeceraPaciente';
import { Carga } from './Carga';
import { Dialogo } from './Dialogo';
import { FichaClinica } from './FichaClinica';
import { FormPaciente } from './FormPaciente';
import { Odontograma } from './Odontograma';
import { Presupuestos } from './Presupuestos';
import type { AvisoCambios } from './useCambiosPendientes';

interface Props {
  readonly api: Api;
  readonly roles: readonly Rol[];
  readonly pacienteId: number;
  readonly pestanaInicial: PestanaPaciente;
}

type PestanaConCarga = Exclude<PestanaPaciente, 'datos'>;

interface Cargas {
  readonly ficha?: Promise<Ficha>;
  readonly odontograma?: Promise<OdontogramaVigente>;
  readonly presupuestos?: Promise<readonly CualquierPresupuesto[]>;
}

const ETIQUETA: Readonly<Record<PestanaPaciente, string>> = {
  ficha: 'Ficha',
  odontograma: 'Odontograma',
  presupuestos: 'Presupuestos',
  datos: 'Datos',
};

const puedeAdministrar = (roles: readonly Rol[]): boolean => roles.includes('recepcion') || roles.includes('admin');

/** La pestaña Datos es solo de recepción y admin: para la odontóloga un enlace directo abre la ficha. */
function pestanaPermitida(pedida: PestanaPaciente, roles: readonly Rol[]): PestanaPaciente {
  return pedida === 'datos' && !puedeAdministrar(roles) ? 'ficha' : pedida;
}

/** Detalle de un paciente (`#/pacientes/{id}`): cabecera y pestañas. Cada pestaña se pide al abrirla y se conserva. */
export function DetallePaciente({ api, roles, pacienteId, pestanaInicial }: Props) {
  const administra = puedeAdministrar(roles);
  const inicial = pestanaPermitida(pestanaInicial, roles);
  const [pestana, setPestana] = useState<PestanaPaciente>(inicial);
  // Todo lo que la pantalla necesita sale a la vez al montar: el paciente y la pestaña activa (R2, O7).
  const [pendientePaciente, setPendientePaciente] = useState(() => iniciar(() => api.paciente(pacienteId)));
  const [cargas, setCargas] = useState<Cargas>(() => (inicial === 'datos' ? {} : cargar(api, pacienteId, inicial)));
  const [confirmar, setConfirmar] = useState<{ readonly aviso: AvisoCambios; readonly continuar: () => void } | null>(null);
  const pendientes = useRef<AvisoCambios | null>(null);
  const registrarCambios = useCallback((aviso: AvisoCambios | null): void => {
    pendientes.current = aviso;
  }, []);

  // Una pestaña nunca vista se pide recién cuando se abre (por el clic o por «atrás»).
  if (pestana !== 'datos' && cargas[pestana] === undefined) {
    setCargas({ ...cargas, ...cargar(api, pacienteId, pestana) });
  }

  useEffect(() => {
    const alCambiarHash = (): void => {
      const d = leerDetallePaciente(window.location.hash);
      if (d?.pacienteId === pacienteId) setPestana(pestanaPermitida(d.pestana, roles));
    };
    const antesDeSalir = (evento: BeforeUnloadEvent): void => {
      if (pendientes.current === null) return;
      evento.preventDefault();
    };
    window.addEventListener('hashchange', alCambiarHash);
    window.addEventListener('beforeunload', antesDeSalir);
    return () => {
      window.removeEventListener('hashchange', alCambiarHash);
      window.removeEventListener('beforeunload', antesDeSalir);
    };
  }, [pacienteId, roles]);

  /** Si la pestaña tiene cambios sin guardar pide confirmación antes de seguir (nada se guarda en el navegador). */
  function conConfirmacion(continuar: () => void): void {
    const aviso = pendientes.current;
    if (aviso === null) {
      continuar();
      return;
    }
    setConfirmar({ aviso, continuar });
  }

  function irAPestana(destino: PestanaPaciente): void {
    if (destino === pestana) return;
    conConfirmacion(() => {
      pendientes.current = null;
      setPestana(destino);
      window.location.hash = hashDePaciente(pacienteId, destino);
    });
  }

  function actualizar(destino: PestanaConCarga): void {
    setCargas((c) => ({ ...c, ...cargar(api, pacienteId, destino) }));
  }

  const volverA = administra ? '#/pacientes' : '#/agenda';
  const pestanas: readonly PestanaPaciente[] = administra ? ['ficha', 'odontograma', 'presupuestos', 'datos'] : ['ficha', 'odontograma', 'presupuestos'];

  return (
    <section className="detalle-paciente" aria-label="Detalle del paciente">
      <a
        className="enlace-volver"
        href={volverA}
        onClick={(e) => {
          if (pendientes.current === null) return;
          e.preventDefault();
          conConfirmacion(() => {
            pendientes.current = null;
            window.location.hash = volverA;
          });
        }}
      >
        ‹ Volver
      </a>
      <Carga
        pendiente={pendientePaciente}
        textoCarga="Cargando paciente…"
        mensajeError="No pudimos cargar al paciente. Revisá tu conexión e intentá de nuevo."
        volverA="#/agenda"
        onReintentar={() => {
          setPendientePaciente(iniciar(() => api.paciente(pacienteId)));
        }}
      >
        {(paciente) => (
          <ContenidoDetalle
            key={paciente.id}
            api={api}
            roles={roles}
            inicial={paciente}
            pestana={pestana}
            pestanas={pestanas}
            cargas={cargas}
            onPestana={irAPestana}
            onActualizar={actualizar}
            onReemplazar={(destino, valor) => {
              setCargas((c) => ({ ...c, [destino]: resuelta(valor) }));
            }}
            registrarCambios={registrarCambios}
          />
        )}
      </Carga>
      {confirmar !== null && (
        <Dialogo
          titulo={confirmar.aviso.mensaje}
          confirmar={confirmar.aviso.descartar}
          volver={confirmar.aviso.seguir}
          enviando={false}
          rechazo={null}
          onVolver={() => {
            setConfirmar(null);
          }}
          onConfirmar={() => {
            const siguiente = confirmar.continuar;
            setConfirmar(null);
            siguiente();
          }}
        />
      )}
    </section>
  );
}

function cargar(api: Api, pacienteId: number, pestana: PestanaConCarga): Cargas {
  switch (pestana) {
    case 'ficha':
      return { ficha: iniciar(() => api.ficha(pacienteId)) };
    case 'odontograma':
      return { odontograma: iniciar(() => api.odontograma(pacienteId)) };
    case 'presupuestos':
      return { presupuestos: iniciar(() => api.presupuestos(pacienteId)) };
  }
}

interface PropsContenido {
  readonly api: Api;
  readonly roles: readonly Rol[];
  readonly inicial: PacienteDetalle;
  readonly pestana: PestanaPaciente;
  readonly pestanas: readonly PestanaPaciente[];
  readonly cargas: Cargas;
  readonly onPestana: (destino: PestanaPaciente) => void;
  readonly onActualizar: (destino: PestanaConCarga) => void;
  readonly onReemplazar: <P extends PestanaConCarga>(destino: P, valor: Awaited<NonNullable<Cargas[P]>>) => void;
  readonly registrarCambios: (aviso: AvisoCambios | null) => void;
}

function ContenidoDetalle({ api, roles, inicial, pestana, pestanas, cargas, onPestana, onActualizar, onReemplazar, registrarCambios }: PropsContenido) {
  // El paciente cambia cuando se editan sus datos o vence el acceso clínico: se conserva lo último que se supo.
  const [paciente, setPaciente] = useState(inicial);
  const comunes = { api, paciente, registrarCambios } as const;

  return (
    <>
      <CabeceraPaciente paciente={paciente} />
      <div className="selector selector-pestanas" role="tablist" aria-label="Secciones del paciente">
        {pestanas.map((p) => (
          <button
            key={p}
            type="button"
            role="tab"
            id={`pestana-paciente-${p}`}
            aria-selected={pestana === p}
            aria-controls="panel-paciente"
            className={`selector-boton${pestana === p ? ' activo' : ''}`}
            onClick={() => {
              onPestana(p);
            }}
          >
            {ETIQUETA[p]}
          </button>
        ))}
      </div>
      <div id="panel-paciente" role="tabpanel" aria-labelledby={`pestana-paciente-${pestana}`}>
        {pestana === 'ficha' && cargas.ficha !== undefined && (
          <Carga
            pendiente={cargas.ficha}
            textoCarga="Cargando ficha…"
            mensajeError="No pudimos cargar la ficha. Revisá tu conexión e intentá de nuevo."
            onReintentar={() => {
              onActualizar('ficha');
            }}
          >
            {(ficha) => (
              <FichaClinica
                {...comunes}
                datos={ficha}
                onActualizar={() => {
                  onActualizar('ficha');
                }}
                onReemplazar={(f) => {
                  onReemplazar('ficha', f);
                }}
                onAccesoVencido={() => {
                  setPaciente((p) => ({ ...p, acceso_clinico: { nivel: 'clinico_lectura', puede_escribir: false } }));
                }}
              />
            )}
          </Carga>
        )}
        {pestana === 'odontograma' && cargas.odontograma !== undefined && (
          <Carga
            pendiente={cargas.odontograma}
            textoCarga="Cargando odontograma…"
            mensajeError="No pudimos cargar el odontograma. Revisá tu conexión e intentá de nuevo."
            onReintentar={() => {
              onActualizar('odontograma');
            }}
          >
            {(odontograma) => (
              <Odontograma
                {...comunes}
                datos={odontograma}
                onActualizar={() => {
                  onActualizar('odontograma');
                }}
                onReemplazar={(o) => {
                  onReemplazar('odontograma', o);
                }}
                onAccesoVencido={() => {
                  setPaciente((p) => ({ ...p, acceso_clinico: { nivel: 'clinico_lectura', puede_escribir: false } }));
                }}
              />
            )}
          </Carga>
        )}
        {pestana === 'presupuestos' && cargas.presupuestos !== undefined && (
          <Carga
            pendiente={cargas.presupuestos}
            textoCarga="Cargando presupuestos…"
            mensajeError="No pudimos cargar los presupuestos. Revisá tu conexión e intentá de nuevo."
            onReintentar={() => {
              onActualizar('presupuestos');
            }}
          >
            {(lista) => (
              <Presupuestos
                {...comunes}
                datos={lista}
                puedeGestionar={puedeAdministrar(roles)}
                onActualizar={() => {
                  onActualizar('presupuestos');
                }}
                onReemplazar={(lista) => {
                  onReemplazar('presupuestos', lista);
                }}
              />
            )}
          </Carga>
        )}
        {pestana === 'datos' && <FormPaciente api={api} paciente={paciente} onGuardado={setPaciente} />}
      </div>
    </>
  );
}
