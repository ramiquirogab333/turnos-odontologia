import type { PacienteDetalle } from '../lib/tipos';

interface Props {
  readonly paciente: PacienteDetalle;
}

/** Nombre, DNI, obra social y afiliado; teléfono y email solo si el servidor los envió (recepción y admin, O3 de C-11). */
export function CabeceraPaciente({ paciente }: Props) {
  const cobertura =
    paciente.obra_social === null
      ? 'Sin obra social'
      : paciente.numero_afiliado === null
        ? paciente.obra_social.nombre
        : `${paciente.obra_social.nombre} · ${paciente.numero_afiliado}`;
  const soloLectura = !paciente.acceso_clinico.puede_escribir && paciente.acceso_clinico.nivel === 'clinico_lectura';
  return (
    <header className="cabecera-paciente">
      <h2 className="paciente-titulo">
        {paciente.nombre} {paciente.apellido}
      </h2>
      <p className="nota">
        DNI {paciente.dni} · {cobertura}
      </p>
      {paciente.telefono !== null && <p className="nota">{paciente.telefono}</p>}
      {paciente.email !== null && <p className="nota">{paciente.email}</p>}
      {soloLectura && (
        <p className="aviso aviso-info" role="status">
          Solo lectura: tu última atención con esta paciente fue hace más de 12 meses. Para editar, pedí un turno a recepción
        </p>
      )}
    </header>
  );
}
