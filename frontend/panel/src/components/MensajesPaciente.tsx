interface PropsSinAcceso {
  /** Hash al que se vuelve (la agenda de la odontóloga). */
  readonly volverA: string;
}

/** 403 `paciente_ajeno` (RN-CL-02): el acceso empieza cuando un turno con la odontóloga se marca atendido. */
export function SinAcceso({ volverA }: PropsSinAcceso) {
  return (
    <div className="aviso aviso-error" role="alert">
      <p>No tenés acceso a esta paciente: el acceso empieza cuando un turno con vos se marca atendido</p>
      <p>Vas a poder ver la ficha cuando marques el turno como atendido.</p>
      <a className="boton boton-secundario" href={volverA}>
        Volver a la agenda
      </a>
    </div>
  );
}

/** 404: el paciente no existe (o el enlace está mal escrito). */
export function SinPaciente() {
  return (
    <div className="aviso aviso-error" role="alert">
      <p>No encontramos ese paciente</p>
      <a className="boton boton-secundario" href="#/pacientes">
        Ir a Pacientes
      </a>
    </div>
  );
}
