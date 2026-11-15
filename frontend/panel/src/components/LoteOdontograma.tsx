import { useId, useState } from 'react';
import type { Api } from '../lib/api';
import { agregarAlLote, CARAS, combinacionValida, ESTADOS_HALLAZGO, etiquetaHallazgo, requisitoDeCara } from '../lib/odontograma';
import { ErrorSesion } from '../lib/sesion';
import type { Cara, HallazgoNuevo } from '../lib/tipos';
import { useCambiosPendientes, type RegistrarCambios } from './useCambiosPendientes';

interface Props {
  readonly api: Api;
  readonly pacienteId: number;
  /** Pieza elegida en la grilla. */
  readonly pieza: number | null;
  /** El lote se registró: el padre vuelve a pedir el estado vigente. */
  readonly onRegistrado: () => void;
  readonly onAccesoVencido: () => void;
  readonly registrarCambios: RegistrarCambios;
}

const plural = (n: number): string => `${String(n)} ${n === 1 ? 'hallazgo' : 'hallazgos'}`;

/**
 * Armado y registro de hallazgos en lote (1 a 64, todo o nada en el servidor). El registro es solo de alta (RN-CL-01):
 * corregir es registrar un hallazgo nuevo. El lote vive solo en memoria (Ley 25.326).
 */
export function LoteOdontograma({ api, pacienteId, pieza, onRegistrado, onAccesoVencido, registrarCambios }: Props) {
  const idBase = useId();
  const [estado, setEstado] = useState('caries');
  const [cara, setCara] = useState<Cara | ''>('');
  const [nota, setNota] = useState('');
  const [lote, setLote] = useState<readonly HallazgoNuevo[]>([]);
  const [aviso, setAviso] = useState<string | null>(null);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [registrado, setRegistrado] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useCambiosPendientes(
    registrarCambios,
    lote.length === 0 ? null : { mensaje: `Tenés ${plural(lote.length)} sin registrar`, seguir: 'Seguir', descartar: 'Descartar' },
  );

  const requisito = requisitoDeCara(estado);
  const caraEfectiva: Cara | null = requisito === 'no' || cara === '' ? null : cara;
  const falta = pieza === null ? null : requisito === 'exige' && caraEfectiva === null ? 'Elegí la cara afectada' : null;
  const valido = pieza !== null && combinacionValida(pieza, caraEfectiva, estado);

  function cambiarEstado(nuevo: string): void {
    setEstado(nuevo);
    if (requisitoDeCara(nuevo) === 'no') setCara('');
  }

  function agregar(): void {
    if (pieza === null || !valido) return;
    const texto = nota.trim();
    const resultado = agregarAlLote(lote, { pieza, cara: caraEfectiva, estado, nota: texto === '' ? null : texto });
    setLote(resultado.lote);
    setAviso(resultado.error);
    setRegistrado(null);
    if (resultado.error === null) setNota('');
  }

  async function registrar(): Promise<void> {
    if (enviando || lote.length === 0) return;
    setEnviando(true);
    setRechazo(null);
    setRegistrado(null);
    try {
      const r = await api.registrarOdontograma(pacienteId, lote);
      if (r.ok) {
        setRegistrado(`Registramos ${plural(lote.length)}`);
        setLote([]);
        setAviso(null);
        onRegistrado();
        return;
      }
      if (r.error.tipo === 'acceso_vencido') {
        setRechazo('Tu acceso para editar venció. Para editar, pedí un turno a recepción');
        onAccesoVencido();
      } else if (r.error.tipo === 'paciente_ajeno') {
        setRechazo('No tenés acceso a esta paciente: el acceso empieza cuando un turno con vos se marca atendido');
      } else if (r.error.tipo === 'validacion') {
        setRechazo(r.error.mensaje);
      } else {
        setRechazo('No pudimos registrar los hallazgos. Revisá tu conexión e intentá de nuevo: el lote se conserva.');
      }
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="lote-odontograma" aria-label="Registrar hallazgos">
      <h3 className="subtitulo">Registrar hallazgos</h3>
      <p className="pieza-actual">{pieza === null ? 'Elegí una pieza en la grilla' : `Pieza ${String(pieza)}`}</p>
      <p className="nota">Para corregir un hallazgo, registrá uno nuevo: el historial no se edita ni se borra.</p>
      <div className="campo">
        <label htmlFor={`${idBase}-estado`}>Estado</label>
        <select
          id={`${idBase}-estado`}
          value={estado}
          onChange={(e) => {
            cambiarEstado(e.target.value);
          }}
        >
          {ESTADOS_HALLAZGO.map((e) => (
            <option key={e.clave} value={e.clave}>
              {e.etiqueta}
            </option>
          ))}
        </select>
      </div>
      {requisito !== 'no' && (
        <div className="campo">
          <label htmlFor={`${idBase}-cara`}>Cara</label>
          <select
            id={`${idBase}-cara`}
            value={cara}
            onChange={(e) => {
              setCara(CARAS.find((c) => c.clave === e.target.value)?.clave ?? '');
            }}
          >
            <option value="">{requisito === 'exige' ? 'Elegí la cara' : 'Toda la pieza'}</option>
            {CARAS.map((c) => (
              <option key={c.clave} value={c.clave}>
                {c.etiqueta}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="campo">
        <label htmlFor={`${idBase}-nota`}>Nota (opcional)</label>
        <textarea
          id={`${idBase}-nota`}
          rows={2}
          maxLength={500}
          value={nota}
          onChange={(e) => {
            setNota(e.target.value);
          }}
        />
      </div>
      {falta !== null && <p className="campo-error">{falta}</p>}
      {aviso !== null && (
        <p className="aviso aviso-info" role="status">
          {aviso}
        </p>
      )}
      <div className="acciones">
        <button type="button" className="boton boton-secundario" disabled={!valido} onClick={agregar}>
          Agregar al lote
        </button>
      </div>

      {lote.length > 0 && (
        <>
          <ul className="lista-lote" aria-label="Lote de hallazgos">
            {lote.map((h, i) => (
              <li key={`${etiquetaHallazgo(h)}-${String(i)}`} className="item-lote">
                <span>
                  {etiquetaHallazgo(h)}
                  {h.nota !== null && <span className="nota"> · {h.nota}</span>}
                </span>
                <button
                  type="button"
                  className="boton boton-secundario"
                  aria-label={`Quitar ${etiquetaHallazgo(h)}`}
                  onClick={() => {
                    setLote((l) => l.filter((_, j) => j !== i));
                    setAviso(null);
                  }}
                >
                  Quitar
                </button>
              </li>
            ))}
          </ul>
          <div className="acciones">
            <button type="button" className="boton boton-primario" disabled={enviando} onClick={() => void registrar()}>
              {enviando ? 'Registrando…' : `Registrar ${plural(lote.length)}`}
            </button>
          </div>
        </>
      )}
      {registrado !== null && (
        <p className="aviso aviso-exito" role="status">
          {registrado}
        </p>
      )}
      {rechazo !== null && (
        <p className="aviso aviso-error" role="alert">
          {rechazo}
        </p>
      )}
    </section>
  );
}
