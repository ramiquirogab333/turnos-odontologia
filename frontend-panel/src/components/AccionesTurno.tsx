import { useEffect, useId, useRef, useState } from 'react';
import type { Api } from '../lib/api';
import { montoExacto } from '../lib/formato';
import { textoSena } from '../lib/presentacion';
import { ErrorSesion } from '../lib/sesion';
import { fechaCorta, horaClinica } from '../lib/tiempo';
import type { Accion, ErrorEstado, MotivoDeshacer, TurnoAgenda } from '../lib/tipos';

interface Props {
  readonly turno: TurnoAgenda;
  readonly api: Api;
  /** Algo cambió (o conviene recargar): la agenda se vuelve a pedir. */
  readonly onCambio: () => void;
}

const BOTON: Readonly<Record<Accion, string>> = {
  atendido: 'Marcar atendido',
  ausente: 'Marcar ausente',
  cancelar: 'Cancelar turno',
  deshacer_atendido: 'Deshacer atendido',
};

const MOTIVOS: readonly { readonly clave: MotivoDeshacer; readonly etiqueta: string }[] = [
  { clave: 'turno_equivocado', etiqueta: 'Marqué el turno equivocado' },
  { clave: 'paciente_no_asistio', etiqueta: 'La persona no vino' },
  { clave: 'otro', etiqueta: 'Otro motivo' },
];

const CONFIRMAR: Readonly<Record<Accion, string>> = {
  atendido: 'Sí, marcar atendido',
  ausente: 'Sí, marcar ausente',
  cancelar: 'Sí, cancelar el turno',
  deshacer_atendido: 'Sí, deshacer el atendido',
};

function titulo(accion: Accion, turno: TurnoAgenda): string {
  const quien = turno.paciente_nombre;
  switch (accion) {
    case 'atendido':
      return quien ? `¿Marcar a ${quien} como atendido?` : '¿Marcar este turno como atendido?';
    case 'ausente':
      return quien ? `¿Marcar a ${quien} como ausente?` : '¿Marcar este turno como ausente?';
    case 'cancelar':
      return quien ? `¿Cancelar el turno de ${quien}?` : '¿Cancelar este turno?';
    case 'deshacer_atendido':
      return quien ? `¿Deshacer el atendido de ${quien}?` : '¿Deshacer el atendido de este turno?';
  }
}

/** Qué pasa con la seña y por qué el cambio es serio: se dice antes de confirmar, no después. */
function consecuencias(accion: Accion, turno: TurnoAgenda): string[] {
  const acreditada = turno.sena?.estado === 'acreditado' ? montoExacto(turno.sena.monto) : null;
  switch (accion) {
    case 'ausente':
      return [
        acreditada !== null ? `La seña de ${acreditada} no se devuelve.` : 'El turno no tiene seña acreditada.',
        'Este cambio no se puede deshacer.',
      ];
    case 'atendido':
      return [
        'Si te equivocás, recepción puede corregirlo hasta 7 días después del turno.',
        'El horario sigue ocupado hasta que termine el turno.',
      ];
    case 'deshacer_atendido':
      return [
        'El turno vuelve a reservado y se puede marcar de nuevo como atendido o ausente.',
        'La odontóloga puede perder el acceso a la ficha de esta persona.',
      ];
    case 'cancelar':
      if (turno.estado === 'en_espera') {
        return ['La persona todavía no pagó la seña: se cancela la pre-reserva y no hay nada que devolver.'];
      }
      return [
        acreditada !== null
          ? `La seña de ${acreditada} queda a devolver a la persona.`
          : `${textoSena(turno) ?? 'El turno no tiene seña'}: no hay nada que devolver.`,
        'El horario queda libre para reservar.',
      ];
  }
}

function mensajeDeRechazo(error: ErrorEstado): string {
  switch (error.tipo) {
    case 'marcado_no_habilitado':
      return error.habilitadoDesde
        ? `Todavía no se puede marcar este turno. Podés hacerlo desde las ${horaClinica(error.habilitadoDesde)}.`
        : 'Todavía no se puede marcar este turno.';
    case 'fuera_de_plazo':
      return error.limiteCambios
        ? `Faltan menos de 24 horas para el turno, así que ya no se puede cancelar desde el panel. El límite era el ${fechaCorta(error.limiteCambios)} a las ${horaClinica(error.limiteCambios)}.`
        : 'Faltan menos de 24 horas para el turno, así que ya no se puede cancelar desde el panel.';
    case 'plazo_vencido':
      return 'Ya pasaron 7 días: este turno no se puede corregir.';
    case 'transicion_invalida':
      return 'Este turno ya cambió de estado. Actualizamos la agenda.';
    case 'no_encontrado':
      return 'Ese turno ya no existe. Actualizamos la agenda.';
    case 'sin_permiso':
      return 'Tu usuario no puede hacer este cambio.';
    case 'reintentar':
      return 'El servidor está ocupado. Probá de nuevo en unos segundos.';
    case 'desconocido':
      return 'No pudimos guardar el cambio. Probá de nuevo; si sigue igual, avisá a la clínica.';
  }
}

/** Rechazos tras los cuales los datos en pantalla quedaron viejos. */
const RECARGAN: readonly ErrorEstado['tipo'][] = ['transicion_invalida', 'no_encontrado', 'plazo_vencido'];

export function AccionesTurno({ turno, api, onCambio }: Props) {
  const [abierta, setAbierta] = useState<Accion | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [motivo, setMotivo] = useState<MotivoDeshacer | ''>('');
  const idTitulo = useId();
  const idMotivo = useId();
  const tituloRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (abierta !== null) tituloRef.current?.focus();
  }, [abierta]);

  if (turno.acciones.length === 0) return null;

  function cerrar(): void {
    setAbierta(null);
    setRechazo(null);
    setMotivo('');
  }

  async function confirmar(accion: Accion): Promise<void> {
    if (enviando) return;
    if (accion === 'deshacer_atendido' && motivo === '') {
      setRechazo('Elegí el motivo para deshacer el atendido.');
      return;
    }
    setEnviando(true);
    setRechazo(null);
    let resultado;
    try {
      resultado = accion === 'deshacer_atendido' ? await api.deshacerAtendido(turno.id, motivo as MotivoDeshacer) : await api.marcar(turno.id, accion);
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    }
    setEnviando(false);
    if (resultado.ok) {
      cerrar();
      onCambio();
      return;
    }
    setRechazo(mensajeDeRechazo(resultado.error));
    if (RECARGAN.includes(resultado.error.tipo)) onCambio();
  }

  return (
    <>
      <div className="acciones-turno">
        {turno.acciones.map((accion) => (
          <button
            key={accion}
            type="button"
            className="boton boton-secundario"
            onClick={() => {
              setRechazo(null);
              setAbierta(accion);
            }}
          >
            {BOTON[accion]}
          </button>
        ))}
      </div>
      {abierta !== null && (
        <div className="velo">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={idTitulo}
            className="dialogo"
            onKeyDown={(e) => {
              if (e.key === 'Escape' && !enviando) cerrar();
            }}
          >
            <h2 id={idTitulo} ref={tituloRef} tabIndex={-1}>
              {titulo(abierta, turno)}
            </h2>
            {consecuencias(abierta, turno).map((linea) => (
              <p key={linea}>{linea}</p>
            ))}
            {abierta === 'deshacer_atendido' && (
              <div className="campo">
                <label htmlFor={idMotivo}>Motivo</label>
                <select
                  id={idMotivo}
                  value={motivo}
                  onChange={(e) => {
                    setMotivo(MOTIVOS.find((m) => m.clave === e.target.value)?.clave ?? '');
                  }}
                >
                  <option value="">Elegí un motivo</option>
                  {MOTIVOS.map((m) => (
                    <option key={m.clave} value={m.clave}>
                      {m.etiqueta}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {rechazo !== null && (
              <p className="aviso aviso-error" role="alert">
                {rechazo}
              </p>
            )}
            <div className="acciones">
              <button type="button" className="boton boton-secundario" onClick={cerrar} disabled={enviando}>
                Volver
              </button>
              <button
                type="button"
                className="boton boton-primario"
                disabled={enviando}
                onClick={() => void confirmar(abierta)}
              >
                {enviando ? 'Guardando…' : CONFIRMAR[abierta]}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
