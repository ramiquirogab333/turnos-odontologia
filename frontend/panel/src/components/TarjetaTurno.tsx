import type { Api } from '../lib/api';
import { ETIQUETA_ESTADO, textoSena } from '../lib/presentacion';
import { horaClinica } from '../lib/tiempo';
import type { TurnoAgenda } from '../lib/tipos';
import { AccionesTurno } from './AccionesTurno';

interface Props {
  readonly turno: TurnoAgenda;
  readonly api: Api;
  readonly onCambio: () => void;
  /** Muestra la profesional (útil cuando la agenda mezcla varias). */
  readonly conProfesional: boolean;
  /** Versión compacta para las celdas de la grilla semanal. */
  readonly compacto?: boolean;
}

/** Un turno de la agenda. El estado es texto; el color y el borde solo lo refuerzan. */
export function TarjetaTurno({ turno, api, onCambio, conProfesional, compacto = false }: Props) {
  const sena = textoSena(turno);
  const pendiente = !turno.bloquea_agenda && turno.estado === 'en_espera';
  return (
    <li className={`turno estado-${turno.estado}${pendiente ? ' pre-reserva' : ''}${compacto ? ' turno-compacto' : ''}`}>
      <div className="turno-cabecera">
        <p className="turno-hora">
          {horaClinica(turno.inicio)} a {horaClinica(turno.fin)}
        </p>
        <span className={`insignia insignia-${turno.estado}`}>{ETIQUETA_ESTADO[turno.estado]}</span>
      </div>
      <p className="turno-paciente">{turno.paciente_nombre ?? 'Sin datos del paciente'}</p>
      {turno.paciente_telefono !== null && <p className="turno-detalle">{turno.paciente_telefono}</p>}
      <p className="turno-detalle">
        {turno.tratamiento.nombre} · {turno.sillon.nombre}
        {conProfesional ? ` · ${turno.profesional.nombre}` : ''}
      </p>
      {sena !== null && <p className="turno-detalle">{sena}</p>}
      {pendiente && <p className="turno-detalle">No ocupa el horario.</p>}
      {turno.calendario.conflicto_abierto && (
        <p className="turno-conflicto">
          <span>Conflicto con Google Calendar</span> <a href="#/google-calendar">Ver conflicto</a>
        </p>
      )}
      <AccionesTurno turno={turno} api={api} onCambio={onCambio} />
    </li>
  );
}
