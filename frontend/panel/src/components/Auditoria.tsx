import { Suspense, startTransition, use, useState, type FormEvent } from 'react';
import { ErrorApiPanel, type Api } from '../lib/api';
import { etiquetaActor, TIPOS_AUDITORIA } from '../lib/datos';
import { iniciar } from '../lib/iniciar';
import { ErrorSesion } from '../lib/sesion';
import { fechaCorta, horaClinica } from '../lib/tiempo';
import type { ConsultaAuditoria, PaginaAuditoria, RegistroAuditoria, UsuarioDirectorio } from '../lib/tipos';
import { Cargando } from './Cargando';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';

interface Props {
  readonly api: Api;
}

const SIN_FILTROS: ConsultaAuditoria = { desde: null, hasta: null, usuarioId: null, tipo: null, entidad: null, entidadId: null, cursor: null };

function vacioANulo(valor: string): string | null {
  const limpio = valor.trim();
  return limpio === '' ? null : limpio;
}

/** Auditoría (solo admin): filtros, tarjetas a 360 px y «Ver más» por cursor. Usuarios y primera página, en paralelo (R2). */
export function Auditoria({ api }: Props) {
  // Las dos lecturas arrancan en el mismo render: ninguna espera a la otra.
  const [usuarios] = useState(() => iniciar(() => api.listarUsuarios().catch(() => [] as readonly UsuarioDirectorio[])));
  const [busqueda, setBusqueda] = useState(() => ({
    numero: 0,
    filtros: SIN_FILTROS,
    pendiente: iniciar(() => api.consultarAuditoria(SIN_FILTROS)),
  }));
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [usuarioId, setUsuarioId] = useState('');
  const [tipo, setTipo] = useState('');
  const [entidad, setEntidad] = useState('');
  const [entidadId, setEntidadId] = useState('');

  function buscarCon(filtros: ConsultaAuditoria): void {
    startTransition(() => {
      setBusqueda((previa) => ({ numero: previa.numero + 1, filtros, pendiente: iniciar(() => api.consultarAuditoria(filtros)) }));
    });
  }

  function buscar(evento: FormEvent): void {
    evento.preventDefault();
    buscarCon({
      desde: vacioANulo(desde),
      hasta: vacioANulo(hasta),
      usuarioId: usuarioId === '' ? null : Number(usuarioId),
      tipo: vacioANulo(tipo),
      entidad: vacioANulo(entidad),
      entidadId: vacioANulo(entidadId),
      cursor: null,
    });
  }

  return (
    <section className="auditoria" aria-label="Auditoría">
      <form className="filtros-auditoria" onSubmit={buscar}>
        <div className="filtros">
          <div className="campo">
            <label htmlFor="aud-desde">Desde</label>
            <input id="aud-desde" type="date" value={desde} onChange={(e) => { setDesde(e.target.value); }} />
          </div>
          <div className="campo">
            <label htmlFor="aud-hasta">Hasta</label>
            <input id="aud-hasta" type="date" value={hasta} onChange={(e) => { setHasta(e.target.value); }} />
          </div>
        </div>
        <p className="nota">Sin fechas se muestran los últimos 7 días.</p>
        <div className="campo">
          <label htmlFor="aud-usuario">Usuario</label>
          <select id="aud-usuario" value={usuarioId} onChange={(e) => { setUsuarioId(e.target.value); }}>
            <option value="">Todos</option>
            <Suspense fallback={null}>
              <OpcionesUsuarios pendiente={usuarios} />
            </Suspense>
          </select>
        </div>
        <div className="campo">
          <label htmlFor="aud-tipo">Tipo</label>
          <select id="aud-tipo" value={tipo} onChange={(e) => { setTipo(e.target.value); }}>
            <option value="">Todos</option>
            {TIPOS_AUDITORIA.map((t) => (
              <option key={t.codigo} value={t.codigo}>
                {t.etiqueta}
              </option>
            ))}
          </select>
        </div>
        <div className="filtros">
          <div className="campo">
            <label htmlFor="aud-entidad">Entidad</label>
            <input id="aud-entidad" type="text" maxLength={50} autoComplete="off" value={entidad} onChange={(e) => { setEntidad(e.target.value); }} />
          </div>
          <div className="campo">
            <label htmlFor="aud-entidad-id">ID de la entidad</label>
            <input id="aud-entidad-id" type="text" maxLength={50} autoComplete="off" value={entidadId} onChange={(e) => { setEntidadId(e.target.value); }} />
          </div>
        </div>
        <button type="submit" className="boton boton-primario boton-ancho">
          Buscar
        </button>
      </form>

      <ErrorBoundary
        key={busqueda.numero}
        onReintentar={() => { buscarCon(busqueda.filtros); }}
        fallback={(volver, error) =>
          error instanceof ErrorApiPanel && error.status === 403 ? (
            <div className="aviso aviso-error" role="alert">
              <p>No tenés permiso para ver la auditoría.</p>
            </div>
          ) : (
            <ErrorCarga mensaje="No pudimos cargar la auditoría. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />
          )
        }
      >
        <Suspense fallback={<Cargando texto="Cargando auditoría…" />}>
          <Resultado key={busqueda.numero} api={api} filtros={busqueda.filtros} pendiente={busqueda.pendiente} />
        </Suspense>
      </ErrorBoundary>
    </section>
  );
}

function OpcionesUsuarios({ pendiente }: { readonly pendiente: Promise<readonly UsuarioDirectorio[]> }) {
  return use(pendiente).map((u) => (
    <option key={u.id} value={String(u.id)}>
      {u.nombre_completo}
      {u.activo ? '' : ' (inactivo)'}
    </option>
  ));
}

interface PropsResultado {
  readonly api: Api;
  readonly filtros: ConsultaAuditoria;
  readonly pendiente: Promise<PaginaAuditoria>;
}

function Resultado({ api, filtros, pendiente }: PropsResultado) {
  const primera = use(pendiente);
  const [mas, setMas] = useState<{ readonly items: readonly RegistroAuditoria[]; readonly siguiente: string | null } | null>(null);
  const [cargando, setCargando] = useState(false);
  const [falla, setFalla] = useState(false);
  const items = [...primera.items, ...(mas?.items ?? [])];
  const siguiente = mas === null ? primera.siguiente : mas.siguiente;

  async function verMas(): Promise<void> {
    if (siguiente === null || cargando) return;
    setCargando(true);
    setFalla(false);
    try {
      const pagina = await api.consultarAuditoria({ ...filtros, cursor: siguiente });
      setMas({ items: [...(mas?.items ?? []), ...pagina.items], siguiente: pagina.siguiente });
    } catch (error) {
      if (!(error instanceof ErrorSesion)) setFalla(true); // con la sesión terminada la app vuelve sola al ingreso
    } finally {
      setCargando(false);
    }
  }

  if (items.length === 0) return <p className="vacio">No hay registros para estos filtros</p>;
  return (
    <>
      <ul className="lista-auditoria" aria-label="Registros de auditoría">
        {items.map((r) => (
          <li key={r.id} className="registro-auditoria">
            <p className="registro-titulo">{r.tipo_etiqueta}</p>
            <p className="nota">
              <span>{`${fechaCorta(r.fecha_hora)} ${horaClinica(r.fecha_hora)}`}</span> · <span>{etiquetaActor(r.usuario)}</span>
            </p>
            <p className="nota">
              {r.entidad}
              {r.entidad_id !== null ? ` #${r.entidad_id}` : ''} · {r.ip !== null ? `IP ${r.ip}` : 'Sin IP'}
            </p>
            {(r.datos_antes !== null || r.datos_despues !== null) && (
              <details className="auditoria-datos">
                <summary>Ver datos</summary>
                <pre>{JSON.stringify({ antes: r.datos_antes, despues: r.datos_despues }, null, 2)}</pre>
              </details>
            )}
          </li>
        ))}
      </ul>
      {falla && (
        <div className="aviso aviso-error" role="alert">
          <p>No pudimos cargar más registros. Probá de nuevo.</p>
        </div>
      )}
      {siguiente !== null && (
        <button
          type="button"
          className="boton boton-secundario boton-ancho"
          disabled={cargando}
          onClick={() => {
            void verMas();
          }}
        >
          {cargando ? 'Cargando…' : 'Ver más'}
        </button>
      )}
    </>
  );
}
