import type { Paso } from '../lib/validacion';

const ETAPAS: readonly { readonly paso: Paso; readonly nombre: string }[] = [
  { paso: 1, nombre: 'Tratamiento' },
  { paso: 2, nombre: 'Horario' },
  { paso: 3, nombre: 'Tus datos' },
];

export function Progreso({ actual }: { readonly actual: Paso }) {
  return (
    <ol className="progreso" aria-label="Progreso de la reserva">
      {ETAPAS.map(({ paso, nombre }) => (
        <li
          key={paso}
          className={paso === actual ? 'progreso-item activo' : paso < actual ? 'progreso-item hecho' : 'progreso-item'}
          aria-current={paso === actual ? 'step' : undefined}
        >
          <span className="progreso-numero" aria-hidden="true">
            {paso}
          </span>
          <span>{nombre}</span>
        </li>
      ))}
    </ol>
  );
}
