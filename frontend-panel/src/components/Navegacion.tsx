import { irA, SECCIONES, TITULO_SECCION, type Seccion } from '../lib/ruta';

interface Props {
  readonly actual: Seccion;
  /** Secciones a mostrar (por defecto todas): la odontóloga solo ve la agenda y Google Calendar. */
  readonly secciones?: readonly Seccion[];
}

/** Secciones del panel según el rol. Son enlaces al hash: sin recargar y con "atrás" que funciona. */
export function Navegacion({ actual, secciones = SECCIONES }: Props) {
  return (
    <nav className="secciones" aria-label="Secciones del panel">
      <ul>
        {secciones.map((seccion) => (
          <li key={seccion}>
            <a
              href={`#/${seccion}`}
              className={`seccion-enlace${seccion === actual ? ' activa' : ''}`}
              aria-current={seccion === actual ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault();
                irA(seccion);
              }}
            >
              {TITULO_SECCION[seccion]}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
