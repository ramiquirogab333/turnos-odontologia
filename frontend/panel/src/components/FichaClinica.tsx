import { useId, useState } from 'react';
import { camposCambiados, CAMPOS_FICHA, contador, cuerpoDeFicha, MAX_ANTECEDENTE, mensajeDeFicha } from '../lib/ficha';
import { ETIQUETA_ESTADO } from '../lib/presentacion';
import { ErrorSesion } from '../lib/sesion';
import { fechaCorta, horaClinica } from '../lib/tiempo';
import type { Antecedentes, EstadoTurno, Ficha } from '../lib/tipos';
import type { PropsPestana } from './pestanasPaciente';
import { useCambiosPendientes } from './useCambiosPendientes';

interface Props extends PropsPestana<Ficha> {
  /** El servidor dijo 403 `acceso_clinico_vencido` al guardar: el detalle actualiza la cabecera. */
  readonly onAccesoVencido: () => void;
}

const AVISO_SIN_GUARDAR = {
  mensaje: 'Tenés cambios sin guardar en la ficha',
  seguir: 'Seguir editando',
  descartar: 'Descartar cambios',
} as const;

const antecedentesDe = (f: Ficha): Antecedentes => ({
  alergias: f.alergias,
  medicacion: f.medicacion,
  antecedentes_medicos: f.antecedentes_medicos,
  observaciones: f.observaciones,
});

const etiquetaEstado = (estado: string): string => ETIQUETA_ESTADO[estado as EstadoTurno] ?? estado;

/** Ficha clínica: antecedentes con control de versión (RN-CL-04, O10) e historia de turnos. */
export function FichaClinica({ api, paciente, datos, onActualizar, onReemplazar, onAccesoVencido, registrarCambios }: Props) {
  const idBase = useId();
  const [actual, setActual] = useState(datos);
  const [previo, setPrevio] = useState(datos);
  if (datos !== previo) {
    setPrevio(datos);
    setActual(datos);
  }
  const [editando, setEditando] = useState(false);
  const [borrador, setBorrador] = useState<Antecedentes>(() => antecedentesDe(datos));
  const [enviando, setEnviando] = useState(false);
  const [guardada, setGuardada] = useState(false);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [propio, setPropio] = useState<Antecedentes | null>(null);
  const [vencido, setVencido] = useState(false);

  const puedeEscribir = paciente.acceso_clinico.puede_escribir && !vencido;
  const sinCambios = camposCambiados(actual, borrador).length === 0;
  useCambiosPendientes(registrarCambios, editando && !sinCambios ? AVISO_SIN_GUARDAR : null);

  const nuncaEditada =
    actual.version === 0 && CAMPOS_FICHA.every(({ clave }) => actual[clave] === '');

  function empezar(): void {
    setBorrador(antecedentesDe(actual));
    setPropio(null);
    setRechazo(null);
    setGuardada(false);
    setEditando(true);
  }

  async function guardar(): Promise<void> {
    if (enviando) return;
    setEnviando(true);
    setRechazo(null);
    try {
      const r = await api.guardarFicha(paciente.id, cuerpoDeFicha(borrador, actual.version));
      if (r.ok) {
        setActual(r.valor);
        onReemplazar(r.valor);
        setEditando(false);
        setGuardada(true);
        return;
      }
      setRechazo(mensajeDeFicha(r.error));
      switch (r.error.tipo) {
        case 'version_desactualizada': {
          // Se muestra la versión vigente y lo escrito queda aparte: nunca se reintenta solo ni se pisa a la otra persona.
          setPropio(borrador);
          setEditando(false);
          const vigente = await api.ficha(paciente.id).catch(() => null);
          if (vigente !== null) {
            setActual(vigente);
            onReemplazar(vigente);
          }
          break;
        }
        case 'acceso_vencido':
          setPropio(borrador);
          setEditando(false);
          setVencido(true);
          onAccesoVencido();
          break;
        default:
          break;
      }
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    } finally {
      setEnviando(false);
    }
  }

  const escritos = propio === null ? [] : camposCambiados(actual, propio);

  return (
    <div className="ficha">
      <div className="acciones-seccion">
        <button type="button" className="boton boton-secundario" onClick={onActualizar}>
          Actualizar
        </button>
        {puedeEscribir && !editando && (
          <button type="button" className="boton boton-primario" onClick={empezar}>
            {nuncaEditada ? 'Completar ficha' : 'Editar ficha'}
          </button>
        )}
      </div>

      {guardada && (
        <p className="aviso aviso-exito" role="status">
          Ficha guardada
        </p>
      )}
      {rechazo !== null && (
        <p className="aviso aviso-error" role="alert">
          {rechazo}
        </p>
      )}
      {propio !== null && escritos.length > 0 && (
        <section className="bloque-propio" aria-label="Lo que escribiste">
          <h3>Lo que escribiste</h3>
          <p className="nota">Esto no se guardó. Copialo si querés conservarlo.</p>
          {CAMPOS_FICHA.filter(({ clave }) => escritos.includes(clave)).map(({ clave, etiqueta }) => (
            <div key={clave} className="campo-propio">
              <p className="etiqueta">{etiqueta}</p>
              <p className="texto-largo">{propio[clave]}</p>
              <button
                type="button"
                className="boton boton-secundario"
                aria-label={`Copiar ${etiqueta}`}
                onClick={() => {
                  void navigator.clipboard.writeText(propio[clave]).catch(() => undefined);
                }}
              >
                Copiar
              </button>
            </div>
          ))}
        </section>
      )}

      {editando ? (
        <form
          className="form-ficha"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void guardar();
          }}
        >
          {CAMPOS_FICHA.map(({ clave, etiqueta }) => (
            <div key={clave} className="campo">
              <label htmlFor={`${idBase}-${clave}`}>{etiqueta}</label>
              <textarea
                id={`${idBase}-${clave}`}
                rows={4}
                maxLength={MAX_ANTECEDENTE}
                value={borrador[clave]}
                onChange={(e) => {
                  setBorrador((b) => ({ ...b, [clave]: e.target.value }));
                }}
              />
              <p className="contador">{contador(borrador[clave])}</p>
            </div>
          ))}
          <div className="acciones">
            <button type="submit" className="boton boton-primario" disabled={enviando}>
              {enviando ? 'Guardando…' : 'Guardar ficha'}
            </button>
          </div>
        </form>
      ) : nuncaEditada ? (
        <p className="vacio">Todavía no hay antecedentes cargados</p>
      ) : (
        <dl className="antecedentes">
          {CAMPOS_FICHA.map(({ clave, etiqueta }) => (
            <div key={clave} className="antecedente">
              <dt>{etiqueta}</dt>
              <dd className="texto-largo">{actual[clave] === '' ? 'Sin datos' : actual[clave]}</dd>
            </div>
          ))}
        </dl>
      )}

      <h3 className="subtitulo">Historia de turnos</h3>
      {actual.historia.length === 0 ? (
        <p className="vacio">Sin turnos registrados</p>
      ) : (
        <ul className="lista-historia" aria-label="Historia de turnos">
          {actual.historia.map((t) => (
            <li key={t.turno_id} className="item-historia">
              <p>
                {fechaCorta(t.inicio)} · {horaClinica(t.inicio)} · {etiquetaEstado(t.estado)}
              </p>
              <p className="nota">
                {t.profesional.nombre} · {t.tratamiento.nombre}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
