import { useId, useState } from 'react';
import type { Api } from '../lib/api';
import { accionesDe, ETIQUETA_PRESUPUESTO, mensajeDeErrorPresupuesto, pesosCompactos, validarMotivo } from '../lib/presupuestos';
import { ErrorSesion } from '../lib/sesion';
import { fechaCorta } from '../lib/tiempo';
import type { AccionPresupuesto, CualquierPresupuesto, ErrorClinico, Presupuesto } from '../lib/tipos';
import { CobrosPresupuesto } from './CobrosPresupuesto';
import { Dialogo } from './Dialogo';
import { LineasPresupuesto } from './LineasPresupuesto';

interface Props {
  readonly api: Api;
  readonly pacienteId: number;
  readonly presupuesto: CualquierPresupuesto;
  /** Recepción y admin gestionan estados y cobros; la odontóloga solo lee. */
  readonly puedeGestionar: boolean;
  readonly onEditar: () => void;
  /** Un cambio de estado o de cobros devolvió el presupuesto nuevo. */
  readonly onCambio: (presupuesto: Presupuesto) => void;
  /** Un rechazo del servidor que el padre muestra (y, si hace falta, recarga la lista). */
  readonly onError: (error: ErrorClinico) => void;
}

type Pregunta = 'presentar' | 'aceptar' | 'rechazar' | 'anular';

const TITULO: Readonly<Record<Pregunta, string>> = {
  presentar: '¿Presentar el presupuesto?',
  aceptar: '¿Marcar el presupuesto como aceptado?',
  rechazar: '¿Marcar el presupuesto como rechazado?',
  anular: '¿Anular el presupuesto?',
};

const CONFIRMAR: Readonly<Record<Pregunta, string>> = {
  presentar: 'Sí, presentar',
  aceptar: 'Sí, aceptar',
  rechazar: 'Sí, rechazar',
  anular: 'Anular presupuesto',
};

const BOTON: Readonly<Record<Pregunta, string>> = { presentar: 'Presentar', aceptar: 'Aceptar', rechazar: 'Rechazar', anular: 'Anular' };

/** Un presupuesto: estado en texto, líneas con importes del servidor, acciones válidas para su estado (RN-PG-05) y cobros. */
export function DetallePresupuesto({ api, pacienteId, presupuesto, puedeGestionar, onEditar, onCambio, onError }: Props) {
  const idMotivo = useId();
  const [pregunta, setPregunta] = useState<Pregunta | null>(null);
  const [motivo, setMotivo] = useState('');
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const completo: Presupuesto | null = 'pagos' in presupuesto ? presupuesto : null;
  const acciones = puedeGestionar ? accionesDe(presupuesto.estado) : [];

  async function confirmar(accion: Pregunta): Promise<void> {
    if (enviando) return;
    setEnviando(true);
    setRechazo(null);
    try {
      const r =
        accion === 'anular'
          ? await api.anularPresupuesto(pacienteId, presupuesto.id, motivo.trim())
          : await api.transicionarPresupuesto(pacienteId, presupuesto.id, accion satisfies AccionPresupuesto);
      if (r.ok) {
        setPregunta(null);
        setMotivo('');
        onCambio(r.valor);
        return;
      }
      if (r.error.tipo === 'transicion_invalida' || r.error.tipo === 'no_encontrado') {
        setPregunta(null);
        onError(r.error);
        return;
      }
      setRechazo(mensajeDeErrorPresupuesto(r.error));
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    } finally {
      setEnviando(false);
    }
  }

  return (
    <article className="presupuesto" aria-label={`Presupuesto del ${fechaCorta(presupuesto.created_at)}`}>
      <header className="presupuesto-cabecera">
        <p className="presupuesto-fecha">{fechaCorta(presupuesto.created_at)}</p>
        <span className={`insignia insignia-presupuesto-${presupuesto.estado}`}>{ETIQUETA_PRESUPUESTO[presupuesto.estado]}</span>
      </header>
      <p className="nota">{presupuesto.obra_social === null ? 'Sin obra social' : presupuesto.obra_social.nombre}</p>
      <LineasPresupuesto lineas={presupuesto.lineas} />
      <p className="total-paciente">A cargo del paciente {pesosCompactos(presupuesto.total_paciente)}</p>
      {presupuesto.notas !== '' && <p className="nota texto-largo">{presupuesto.notas}</p>}
      {presupuesto.estado === 'anulado' && presupuesto.anulado_motivo !== null && <p className="nota texto-largo">Anulado · {presupuesto.anulado_motivo}</p>}

      {completo !== null && (
        <CobrosPresupuesto
          api={api}
          pacienteId={pacienteId}
          presupuesto={completo}
          puedeRegistrar={puedeGestionar}
          onCambio={onCambio}
        />
      )}

      {acciones.length > 0 && (
        <div className="acciones-presupuesto">
          {acciones.map((a) =>
            a === 'editar' ? (
              <button key={a} type="button" className="boton boton-secundario" onClick={onEditar}>
                Editar
              </button>
            ) : a === 'registrar_cobro' ? null : (
              <button
                key={a}
                type="button"
                className="boton boton-secundario"
                onClick={() => {
                  setRechazo(null);
                  setMotivo('');
                  setPregunta(a);
                }}
              >
                {BOTON[a]}
              </button>
            ),
          )}
        </div>
      )}

      {pregunta !== null && (
        <Dialogo
          titulo={TITULO[pregunta]}
          confirmar={CONFIRMAR[pregunta]}
          enviando={enviando}
          confirmarDeshabilitado={pregunta === 'anular' && validarMotivo(motivo) !== null}
          rechazo={rechazo}
          onVolver={() => {
            setPregunta(null);
          }}
          onConfirmar={() => void confirmar(pregunta)}
        >
          {pregunta === 'presentar' && <p>Los importes quedan fijos desde ahora</p>}
          {pregunta === 'aceptar' && <p>Desde este momento se pueden registrar cobros.</p>}
          {pregunta === 'rechazar' && <p>El presupuesto queda cerrado como rechazado.</p>}
          {pregunta === 'anular' && (
            <div className="campo">
              <label htmlFor={idMotivo}>Motivo</label>
              <textarea
                id={idMotivo}
                rows={3}
                value={motivo}
                onChange={(e) => {
                  setMotivo(e.target.value);
                }}
              />
              {motivo !== '' && validarMotivo(motivo) !== null && <p className="campo-error">{validarMotivo(motivo)}</p>}
            </div>
          )}
        </Dialogo>
      )}
    </article>
  );
}
