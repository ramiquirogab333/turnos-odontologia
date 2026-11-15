import { useId, useState } from 'react';
import type { Api } from '../lib/api';
import { iniciar } from '../lib/iniciar';
import { CARAS } from '../lib/odontograma';
import { mensajeDeErrorPresupuesto, pesosCompactos, validarLineas } from '../lib/presupuestos';
import { ErrorSesion } from '../lib/sesion';
import type { Cara, DatosPresupuesto, LineaNueva, Opciones, PacienteDetalle, Presupuesto, Ref } from '../lib/tipos';
import { Carga } from './Carga';
import { LineasPresupuesto } from './LineasPresupuesto';

interface Props {
  readonly api: Api;
  readonly paciente: PacienteDetalle;
  /** El borrador a editar; `null` para uno nuevo. */
  readonly existente: Presupuesto | null;
  readonly onGuardado: (presupuesto: Presupuesto) => void;
  /** El presupuesto cambió en el servidor (409): el padre vuelve a pedir la lista. */
  readonly onRecargar: () => void;
  readonly onCancelar: () => void;
}

interface LineaForm {
  readonly clave: number;
  readonly tratamientoId: string;
  readonly cantidad: string;
  readonly pieza: string;
  readonly cara: Cara | '';
}

const DEL_PACIENTE = '__paciente__';

function lineasIniciales(existente: Presupuesto | null): readonly LineaForm[] {
  return (existente?.lineas ?? []).map((l, i) => ({
    clave: i,
    tratamientoId: String(l.tratamiento.id),
    cantidad: String(l.cantidad),
    pieza: l.pieza === null ? '' : String(l.pieza),
    cara: CARAS.find((c) => c.clave === l.cara)?.clave ?? '',
  }));
}

function aLineaNueva(l: LineaForm): LineaNueva {
  const textoPieza = l.pieza.trim();
  const numeroPieza = Number(textoPieza);
  return {
    tratamiento_id: Number(l.tratamientoId),
    cantidad: l.cantidad.trim() === '' ? 0 : Number(l.cantidad),
    // Una pieza que no es un entero (se rechaza en `validarLineas`) se marca con 0, que no es una pieza FDI.
    pieza: textoPieza === '' ? null : Number.isInteger(numeroPieza) ? numeroPieza : 0,
    cara: l.cara === '' ? null : l.cara,
  };
}

/** Armado de un borrador. Tratamientos y obras sociales salen a la vez al abrir (R2). Los importes son solo los del servidor (O11). */
export function FormPresupuesto({ api, paciente, existente, onGuardado, onRecargar, onCancelar }: Props) {
  const [opciones, setOpciones] = useState(() => iniciar(() => Promise.all([api.opciones(), api.obrasSociales()])));
  return (
    <Carga
      pendiente={opciones}
      textoCarga="Cargando tratamientos y obras sociales…"
      mensajeError="No pudimos cargar los tratamientos y las obras sociales. Revisá tu conexión e intentá de nuevo."
      onReintentar={() => {
        setOpciones(iniciar(() => Promise.all([api.opciones(), api.obrasSociales()])));
      }}
    >
      {([datos, obras]) => (
        <Formulario
          api={api}
          paciente={paciente}
          existente={existente}
          opciones={datos}
          obras={obras}
          onGuardado={onGuardado}
          onRecargar={onRecargar}
          onCancelar={onCancelar}
          onRecargarObras={() => {
            setOpciones(iniciar(() => Promise.all([api.opciones(), api.obrasSociales()])));
          }}
        />
      )}
    </Carga>
  );
}

interface PropsFormulario extends Props {
  readonly opciones: Opciones;
  readonly obras: readonly Ref[];
  readonly onRecargarObras: () => void;
}

function Formulario({ api, paciente, existente, opciones, obras, onGuardado, onRecargar, onCancelar, onRecargarObras }: PropsFormulario) {
  const idBase = useId();
  const [lineas, setLineas] = useState<readonly LineaForm[]>(() => lineasIniciales(existente));
  const [siguiente, setSiguiente] = useState(() => lineasIniciales(existente).length);
  const [obraSocial, setObraSocial] = useState(existente === null ? DEL_PACIENTE : existente.obra_social === null ? '' : String(existente.obra_social.id));
  const [notas, setNotas] = useState(existente?.notas ?? '');
  const [errores, setErrores] = useState<{ readonly general: string | null; readonly porLinea: readonly (string | null)[] }>({ general: null, porLinea: [] });
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [guardado, setGuardado] = useState<Presupuesto | null>(null);

  const activos = opciones.tratamientos.filter((t) => t.activo);
  const inactivosEnUso = new Set(opciones.tratamientos.filter((t) => !t.activo).map((t) => t.id));
  const actual = existente?.obra_social ?? null;
  const faltaObra = existente !== null && actual !== null && !obras.some((o) => o.id === actual.id);

  function cambiarLinea(clave: number, cambios: Partial<LineaForm>): void {
    setLineas((ls) => ls.map((l) => (l.clave === clave ? { ...l, ...cambios } : l)));
    setGuardado(null);
  }

  async function guardar(): Promise<void> {
    if (enviando) return;
    const nuevas = lineas.map(aLineaNueva);
    const validacion = validarLineas(nuevas);
    setErrores(validacion);
    setRechazo(null);
    if (validacion.general !== null || validacion.porLinea.some((e) => e !== null) || nuevas.some((l) => !Number.isInteger(l.tratamiento_id) || l.tratamiento_id <= 0)) {
      if (validacion.general === null && validacion.porLinea.every((e) => e === null)) setRechazo('Elegí el tratamiento de cada línea');
      return;
    }
    const datos: DatosPresupuesto = {
      lineas: nuevas,
      ...(obraSocial === DEL_PACIENTE ? {} : { obra_social_id: obraSocial === '' ? null : Number(obraSocial) }),
      notas,
    };
    setEnviando(true);
    try {
      const r = existente === null ? await api.crearPresupuesto(paciente.id, datos) : await api.editarPresupuesto(paciente.id, existente.id, datos);
      if (r.ok) {
        setGuardado(r.valor);
        onGuardado(r.valor);
        return;
      }
      setRechazo(mensajeDeErrorPresupuesto(r.error));
      if (r.error.tipo === 'obra_social_inactiva') onRecargarObras();
      if (r.error.tipo === 'presupuesto_no_editable' || r.error.tipo === 'transicion_invalida') onRecargar();
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    } finally {
      setEnviando(false);
    }
  }

  const cobertura = paciente.obra_social?.nombre ?? 'Sin obra social';

  return (
    <form
      className="form-presupuesto"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void guardar();
      }}
    >
      <h3 className="subtitulo">{existente === null ? 'Nuevo presupuesto' : 'Editar borrador'}</h3>
      <div className="campo">
        <label htmlFor={`${idBase}-obra`}>Obra social</label>
        <select
          id={`${idBase}-obra`}
          value={obraSocial}
          onChange={(e) => {
            setObraSocial(e.target.value);
            setGuardado(null);
          }}
        >
          {existente === null && <option value={DEL_PACIENTE}>La del paciente ({cobertura})</option>}
          <option value="">Sin obra social</option>
          {faltaObra && <option value={String(actual.id)}>{actual.nombre} (inactiva)</option>}
          {obras.map((o) => (
            <option key={o.id} value={String(o.id)}>
              {o.nombre}
            </option>
          ))}
        </select>
      </div>

      {lineas.map((l, i) => {
        const id = `${idBase}-${String(l.clave)}`;
        const error = errores.porLinea[i] ?? null;
        const enExistente = existente?.lineas.find((x) => String(x.tratamiento.id) === l.tratamientoId);
        return (
          <div key={l.clave} role="group" aria-label={`Línea ${String(i + 1)}`} className="linea-form">
            <div className="campo">
              <label htmlFor={`${id}-trat`}>Tratamiento</label>
              <select
                id={`${id}-trat`}
                value={l.tratamientoId}
                onChange={(e) => {
                  cambiarLinea(l.clave, { tratamientoId: e.target.value });
                }}
              >
                <option value="">Elegí un tratamiento</option>
                {enExistente !== undefined && inactivosEnUso.has(enExistente.tratamiento.id) && (
                  <option value={String(enExistente.tratamiento.id)}>{enExistente.tratamiento.nombre} (inactivo)</option>
                )}
                {activos.map((t) => (
                  <option key={t.id} value={String(t.id)}>
                    {t.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div className="campo">
              <label htmlFor={`${id}-cant`}>Cantidad</label>
              <input
                id={`${id}-cant`}
                type="text"
                inputMode="numeric"
                value={l.cantidad}
                onChange={(e) => {
                  cambiarLinea(l.clave, { cantidad: e.target.value });
                }}
              />
            </div>
            <div className="campo">
              <label htmlFor={`${id}-pieza`}>Pieza (opcional)</label>
              <input
                id={`${id}-pieza`}
                type="text"
                inputMode="numeric"
                maxLength={2}
                value={l.pieza}
                onChange={(e) => {
                  cambiarLinea(l.clave, { pieza: e.target.value });
                }}
              />
            </div>
            <div className="campo">
              <label htmlFor={`${id}-cara`}>Cara (opcional)</label>
              <select
                id={`${id}-cara`}
                value={l.cara}
                onChange={(e) => {
                  cambiarLinea(l.clave, { cara: CARAS.find((c) => c.clave === e.target.value)?.clave ?? '' });
                }}
              >
                <option value="">Sin cara</option>
                {CARAS.map((c) => (
                  <option key={c.clave} value={c.clave}>
                    {c.etiqueta}
                  </option>
                ))}
              </select>
            </div>
            {error !== null && <p className="campo-error">{error}</p>}
            <button
              type="button"
              className="boton boton-secundario"
              aria-label={`Quitar línea ${String(i + 1)}`}
              onClick={() => {
                setLineas((ls) => ls.filter((x) => x.clave !== l.clave));
                setGuardado(null);
              }}
            >
              Quitar
            </button>
          </div>
        );
      })}
      {errores.general !== null && <p className="campo-error">{errores.general}</p>}
      <div className="acciones">
        <button
          type="button"
          className="boton boton-secundario"
          onClick={() => {
            setLineas((ls) => [...ls, { clave: siguiente, tratamientoId: '', cantidad: '1', pieza: '', cara: '' }]);
            setSiguiente((n) => n + 1);
            setGuardado(null);
          }}
        >
          Agregar línea
        </button>
      </div>

      <div className="campo">
        <label htmlFor={`${idBase}-notas`}>Notas</label>
        <textarea
          id={`${idBase}-notas`}
          rows={3}
          maxLength={1000}
          value={notas}
          onChange={(e) => {
            setNotas(e.target.value);
            setGuardado(null);
          }}
        />
      </div>

      {guardado === null ? (
        <p className="nota">Guardá el borrador para ver los importes</p>
      ) : (
        <section className="importes-guardados" aria-label="Importes calculados">
          <p className="aviso aviso-exito" role="status">
            Borrador guardado
          </p>
          <LineasPresupuesto lineas={guardado.lineas} />
          <p className="total-paciente">A cargo del paciente {pesosCompactos(guardado.total_paciente)}</p>
        </section>
      )}
      {rechazo !== null && (
        <p className="aviso aviso-error" role="alert">
          {rechazo}
        </p>
      )}
      <div className="acciones">
        <button type="button" className="boton boton-secundario" onClick={onCancelar}>
          {guardado === null ? 'Cancelar' : 'Cerrar'}
        </button>
        <button type="submit" className="boton boton-primario" disabled={enviando}>
          {enviando ? 'Guardando…' : 'Guardar borrador'}
        </button>
      </div>
    </form>
  );
}
