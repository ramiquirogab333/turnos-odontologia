import { irA, SECCIONES, TITULO_SECCION, type Seccion } from '../lib/ruta';

interface Props {
  readonly actual: Seccion;
}

/** Secciones del panel para recepción y admin. Son enlaces al hash: sin recargar y con "atrás" que funciona. */
export function Navegacion({ actual }: Props) {
  return (
    <nav className="secciones" aria-label="Secciones del panel">
      <ul>
        {SECCIONES.map((seccion) => (
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
