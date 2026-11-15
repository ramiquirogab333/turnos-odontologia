import { useState } from 'react';
import { ErrorSesion } from '../lib/sesion';
import type { OdontogramaVigente } from '../lib/tipos';
import { GrillaPiezas } from './GrillaPiezas';
import { HistorialOdontograma } from './HistorialOdontograma';
import { LoteOdontograma } from './LoteOdontograma';
import type { PropsPestana } from './pestanasPaciente';

interface Props extends PropsPestana<OdontogramaVigente> {
  readonly onAccesoVencido: () => void;
}

/** Odontograma FDI: estado vigente por pieza y cara, registro en lote (solo alta) e historial (RN-CL-01, RN-CL-04). */
export function Odontograma({ api, paciente, datos, onActualizar, onReemplazar, onAccesoVencido, registrarCambios }: Props) {
  const [vigente, setVigente] = useState(datos);
  const [previo, setPrevio] = useState(datos);
  if (datos !== previo) {
    setPrevio(datos);
    setVigente(datos);
  }
  const [temporales, setTemporales] = useState(false);
  const [seleccionada, setSeleccionada] = useState<number | null>(null);
  const [claveHistorial, setClaveHistorial] = useState(0);
  // Si el acceso vence al registrar, el lote sigue a la vista para anotarlo aunque ya no se pueda enviar.
  const [vencido, setVencido] = useState(false);
  const puedeEscribir = paciente.acceso_clinico.puede_escribir || vencido;

  async function recargar(): Promise<void> {
    try {
      const nuevo = await api.odontograma(paciente.id);
      setVigente(nuevo);
      onReemplazar(nuevo);
      setClaveHistorial((c) => c + 1);
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      onActualizar(); // no se pudo refrescar: se pide de nuevo con el límite de carga
    }
  }

  return (
    <div className="odontograma">
      <div className="acciones-seccion">
        <div className="selector" role="group" aria-label="Dentición">
          <button
            type="button"
            className={`selector-boton${temporales ? '' : ' activo'}`}
            aria-pressed={!temporales}
            onClick={() => {
              setTemporales(false);
            }}
          >
            Permanentes
          </button>
          <button
            type="button"
            className={`selector-boton${temporales ? ' activo' : ''}`}
            aria-pressed={temporales}
            onClick={() => {
              setTemporales(true);
            }}
          >
            Temporales
          </button>
        </div>
        <button type="button" className="boton boton-secundario" onClick={onActualizar}>
          Actualizar
        </button>
      </div>

      <GrillaPiezas vigentes={vigente.piezas} temporales={temporales} seleccionada={seleccionada} puedeElegir={puedeEscribir} onElegir={setSeleccionada} />

      {puedeEscribir && (
        <LoteOdontograma
          api={api}
          pacienteId={paciente.id}
          pieza={seleccionada}
          onRegistrado={() => void recargar()}
          onAccesoVencido={() => {
            setVencido(true);
            onAccesoVencido();
          }}
          registrarCambios={registrarCambios}
        />
      )}

      <HistorialOdontograma key={claveHistorial} api={api} pacienteId={paciente.id} />
    </div>
  );
}
