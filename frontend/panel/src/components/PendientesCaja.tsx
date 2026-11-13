import { useState } from 'react';
import type { Api } from '../lib/api';
import { pesos } from '../lib/formato';
import { ETIQUETA_ESTADO, textoMedio } from '../lib/presentacion';
import { fechaCorta } from '../lib/tiempo';
import type { Pendiente } from '../lib/tipos';
import { Dialogo } from './Dialogo';
import { useEnvio } from './useEnvio';

interface Props {
  readonly pendientes: readonly Pendiente[];
  readonly api: Api;
  /** Algo cambió: la caja y los pendientes se vuelven a pedir. */
  readonly onCambio: () => void;
}

type Accion = 'acreditar' | 'rechazar' | 'devolver';
interface Abierta {
  readonly accion: Accion;
  readonly item: Pendiente;
}

const CONFIRMAR: Readonly<Record<Accion, string>> = {
  acreditar: 'Sí, acreditar el pago',
  rechazar: 'Sí, rechazar el pago',
  devolver: 'Sí, registrar la devolución',
};

const FALTA_REFERENCIA = 'Escribí la referencia de la devolución (el número de operación).';

function importeTexto(item: Pendiente): string {
  return item.importe !== null ? pesos(item.importe) : 'importe a verificar';
}

function descripcion(item: Pendiente): string {
  const importe = importeTexto(item);
  switch (item.tipo) {
    case 'revision':
      return `Pago en revisión: ${importe} · ${textoMedio(item.medio)}`;
    case 'sena':
      return `Seña a devolver: ${importe} · ${textoMedio(item.medio)}`;
    case 'excedente_mp':
      return `Pago de más a devolver: ${importe} · ${textoMedio(item.medio)}`;
  }
}

function titulo({ accion, item }: Abierta): string {
  const de = item.importe !== null ? ` de ${pesos(item.importe)}` : '';
  switch (accion) {
    case 'acreditar':
      return `¿Acreditar el pago${de}?`;
    case 'rechazar':
      return `¿Rechazar el pago${de}?`;
    case 'devolver':
      return `¿Registrar la devolución${de}?`;
  }
}

/** Qué pasa con el dinero y con el turno: se dice antes de confirmar, no después. */
function consecuencias({ accion, item }: Abierta): string[] {
  switch (accion) {
    case 'acreditar':
      return ['El pago se acepta como seña. Si el horario sigue libre, el turno pasa a reservado; si ya no, el dinero queda a devolver.'];
    case 'rechazar':
      return ['El dinero queda a devolver a la persona. El turno no cambia.'];
    case 'devolver':
      return [
        'Anotá el número de operación de la devolución que ya hiciste.',
        item.tipo === 'excedente_mp'
          ? 'Es un pago de más: no mueve la caja.'
          : 'La seña pasa a «Seña devuelta» y queda como egreso de la caja de hoy.',
      ];
  }
}

export function PendientesCaja({ pendientes, api, onCambio }: Props) {
  const [abierta, setAbierta] = useState<Abierta | null>(null);
  const [referencia, setReferencia] = useState('');
  const { enviando, rechazo, setRechazo, ejecutar } = useEnvio('pago', onCambio);

  function cerrar(): void {
    setAbierta(null);
    setReferencia('');
    setRechazo(null);
  }

  function abrir(accion: Accion, item: Pendiente): void {
    setRechazo(null);
    setReferencia('');
    setAbierta({ accion, item });
  }

  function exito(): void {
    cerrar();
    onCambio();
  }

  async function confirmar({ accion, item }: Abierta): Promise<void> {
    if (accion === 'acreditar') return ejecutar(() => api.acreditarRevision(item.pago_id), exito);
    if (accion === 'rechazar') return ejecutar(() => api.rechazarRevision(item.pago_id), exito);
    const limpia = referencia.trim();
    if (limpia.length < 3) {
      setRechazo(FALTA_REFERENCIA);
      return;
    }
    return ejecutar(
      () => (item.tipo === 'excedente_mp' ? api.registrarDevolucionExcedente(item.id, limpia) : api.registrarDevolucion(item.pago_id, limpia)),
      exito,
    );
  }

  return (
    <section className="pendientes" aria-labelledby="titulo-pendientes">
      <h3 id="titulo-pendientes">Pagos por resolver</h3>
      {pendientes.length === 0 ? (
        <p className="vacio">No hay pagos por resolver</p>
      ) : (
        <ul className="lista-pendientes">
          {pendientes.map((item) => (
            <li key={`${item.tipo}-${String(item.id)}`} className="pendiente">
              <p className="pendiente-titulo">{descripcion(item)}</p>
              <p className="nota">
                Turno {item.turno_id} · {ETIQUETA_ESTADO[item.estado_turno as keyof typeof ETIQUETA_ESTADO] ?? item.estado_turno} · desde el{' '}
                {fechaCorta(item.pendiente_desde)}
              </p>
              <div className="acciones-turno">
                {item.tipo === 'revision' ? (
                  <>
                    <button type="button" className="boton boton-secundario" onClick={() => { abrir('acreditar', item); }}>
                      Acreditar
                    </button>
                    <button type="button" className="boton boton-secundario" onClick={() => { abrir('rechazar', item); }}>
                      Rechazar
                    </button>
                  </>
                ) : (
                  <button type="button" className="boton boton-secundario" onClick={() => { abrir('devolver', item); }}>
                    Registrar devolución
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {abierta !== null && (
        <Dialogo
          titulo={titulo(abierta)}
          confirmar={CONFIRMAR[abierta.accion]}
          enviando={enviando}
          rechazo={rechazo}
          onVolver={cerrar}
          onConfirmar={() => void confirmar(abierta)}
        >
          {consecuencias(abierta).map((linea) => (
            <p key={linea}>{linea}</p>
          ))}
          {abierta.accion === 'devolver' && (
            <div className="campo">
              <label htmlFor="referencia-devolucion">Referencia de la devolución</label>
              <input
                id="referencia-devolucion"
                type="text"
                autoComplete="off"
                maxLength={64}
                value={referencia}
                onChange={(e) => {
                  setReferencia(e.target.value);
                }}
              />
            </div>
          )}
        </Dialogo>
      )}
    </section>
  );
}
