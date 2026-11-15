import { useState } from 'react';
import { mensajeDeErrorPresupuesto } from '../lib/presupuestos';
import { ErrorSesion } from '../lib/sesion';
import type { CualquierPresupuesto, ErrorClinico, Presupuesto } from '../lib/tipos';
import { DetallePresupuesto } from './DetallePresupuesto';
import { FormPresupuesto } from './FormPresupuesto';
import type { PropsPestana } from './pestanasPaciente';

interface Props extends PropsPestana<readonly CualquierPresupuesto[]> {
  /** Recepción y admin arman, presentan y cobran; la odontóloga solo ve líneas e importes. */
  readonly puedeGestionar: boolean;
}

type Vista = { readonly tipo: 'lista' } | { readonly tipo: 'form'; readonly existente: Presupuesto | null };

/** El más reciente primero: por fecha de creación y, a igual fecha, por id. */
const masRecientePrimero = (a: CualquierPresupuesto, b: CualquierPresupuesto): number =>
  a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : b.id - a.id;

const RECARGAN: readonly ErrorClinico['tipo'][] = ['transicion_invalida', 'presupuesto_no_editable', 'no_encontrado'];

/** Presupuestos del paciente (RN-PG-04/05/06): lista por rol, armado del borrador, estados y cobros. */
export function Presupuestos({ api, paciente, datos, puedeGestionar, onActualizar, onReemplazar }: Props) {
  const [lista, setLista] = useState(datos);
  const [previo, setPrevio] = useState(datos);
  if (datos !== previo) {
    setPrevio(datos);
    setLista(datos);
  }
  const [vista, setVista] = useState<Vista>({ tipo: 'lista' });
  const [mensaje, setMensaje] = useState<string | null>(null);

  function reemplazar(nuevo: Presupuesto): void {
    const siguiente = lista.some((p) => p.id === nuevo.id) ? lista.map((p) => (p.id === nuevo.id ? nuevo : p)) : [nuevo, ...lista];
    setLista(siguiente);
    onReemplazar(siguiente);
  }

  async function recargar(): Promise<void> {
    try {
      const nueva = await api.presupuestos(paciente.id);
      setLista(nueva);
      onReemplazar(nueva);
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      onActualizar(); // no se pudo refrescar: se vuelve a pedir con el límite de carga
    }
  }

  function alError(error: ErrorClinico): void {
    setMensaje(mensajeDeErrorPresupuesto(error));
    if (RECARGAN.includes(error.tipo)) void recargar();
  }

  if (vista.tipo === 'form') {
    return (
      <FormPresupuesto
        api={api}
        paciente={paciente}
        existente={vista.existente}
        onGuardado={reemplazar}
        onRecargar={() => {
          setVista({ tipo: 'lista' });
          void recargar();
        }}
        onCancelar={() => {
          setVista({ tipo: 'lista' });
        }}
      />
    );
  }

  const ordenada = [...lista].sort(masRecientePrimero);
  return (
    <div className="presupuestos">
      <div className="acciones-seccion">
        <button type="button" className="boton boton-secundario" onClick={onActualizar}>
          Actualizar
        </button>
        {puedeGestionar && lista.length > 0 && (
          <button
            type="button"
            className="boton boton-primario"
            onClick={() => {
              setMensaje(null);
              setVista({ tipo: 'form', existente: null });
            }}
          >
            Nuevo presupuesto
          </button>
        )}
      </div>
      {mensaje !== null && (
        <p className="aviso aviso-error" role="alert">
          {mensaje}
        </p>
      )}
      {lista.length === 0 ? (
        <div className="vacio">
          <p>Este paciente todavía no tiene presupuestos</p>
          {puedeGestionar && (
            <button
              type="button"
              className="boton boton-primario"
              onClick={() => {
                setVista({ tipo: 'form', existente: null });
              }}
            >
              Nuevo presupuesto
            </button>
          )}
        </div>
      ) : (
        ordenada.map((p) => (
          <DetallePresupuesto
            key={p.id}
            api={api}
            pacienteId={paciente.id}
            presupuesto={p}
            puedeGestionar={puedeGestionar}
            onEditar={() => {
              setMensaje(null);
              if ('pagos' in p) setVista({ tipo: 'form', existente: p });
            }}
            onCambio={(nuevo) => {
              setMensaje(null);
              reemplazar(nuevo);
            }}
            onError={alError}
          />
        ))
      )}
    </div>
  );
}
