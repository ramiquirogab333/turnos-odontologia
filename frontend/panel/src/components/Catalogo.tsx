import { Suspense, use, useState } from 'react';
import type { Api } from '../lib/api';
import { iniciar } from '../lib/iniciar';
import type { PestanaCatalogo } from '../lib/ruta';
import type { CatalogoAdmin } from '../lib/tipos';
import { Cargando } from './Cargando';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';
import { HorariosCatalogo } from './HorariosCatalogo';
import { ProfesionalesCatalogo } from './ProfesionalesCatalogo';
import { SillonesCatalogo } from './SillonesCatalogo';
import { TratamientosCatalogo } from './TratamientosCatalogo';

interface Props {
  readonly api: Api;
  /** Pestaña con la que abre (sale del hash `#/catalogo?pestana=horarios`). */
  readonly pestanaInicial?: PestanaCatalogo;
}

const PESTANAS: readonly { readonly id: PestanaCatalogo; readonly etiqueta: string }[] = [
  { id: 'tratamientos', etiqueta: 'Tratamientos' },
  { id: 'profesionales', etiqueta: 'Profesionales' },
  { id: 'sillones', etiqueta: 'Sillones' },
  { id: 'horarios', etiqueta: 'Horarios' },
];

/** «Catálogo» (C-14): tratamientos, profesionales, sillones y horarios. Las cuatro listas se piden juntas (R2). */
export function Catalogo({ api, pestanaInicial = 'tratamientos' }: Props) {
  const [lectura, setLectura] = useState(() => iniciar(() => api.catalogo()));
  const [ronda, setRonda] = useState(0);

  function recargar(): void {
    setLectura(iniciar(() => api.catalogo()));
    setRonda((r) => r + 1);
  }

  return (
    <section className="catalogo" aria-label="Catálogo">
      <ErrorBoundary
        onReintentar={recargar}
        fallback={(volver) => (
          <ErrorCarga mensaje="No pudimos cargar el catálogo. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />
        )}
      >
        <Suspense fallback={<Cargando texto="Cargando el catálogo…" />}>
          <Contenido key={ronda} api={api} lectura={lectura} pestanaInicial={pestanaInicial} />
        </Suspense>
      </ErrorBoundary>
    </section>
  );
}

interface PropsContenido {
  readonly api: Api;
  readonly lectura: Promise<CatalogoAdmin>;
  readonly pestanaInicial: PestanaCatalogo;
}

function Contenido({ api, lectura, pestanaInicial }: PropsContenido) {
  const [datos, setDatos] = useState(use(lectura));
  const [pestana, setPestana] = useState<PestanaCatalogo>(pestanaInicial);
  const [aviso, setAviso] = useState('');

  const propsPestana = { api, datos, cambiar: setDatos, avisar: setAviso };

  return (
    <>
      <div className="selector selector-periodo selector-catalogo" role="tablist" aria-label="Catálogo">
        {PESTANAS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            id={`pestana-catalogo-${p.id}`}
            aria-selected={pestana === p.id}
            aria-controls="panel-catalogo"
            className={`selector-boton${pestana === p.id ? ' activo' : ''}`}
            onClick={() => {
              setPestana(p.id);
              setAviso('');
            }}
          >
            {p.etiqueta}
          </button>
        ))}
      </div>
      {aviso !== '' && (
        <p className="aviso aviso-exito" role="status">
          {aviso}
        </p>
      )}
      <div id="panel-catalogo" role="tabpanel" aria-labelledby={`pestana-catalogo-${pestana}`}>
        {pestana === 'tratamientos' && <TratamientosCatalogo {...propsPestana} />}
        {pestana === 'profesionales' && <ProfesionalesCatalogo {...propsPestana} />}
        {pestana === 'sillones' && <SillonesCatalogo {...propsPestana} />}
        {pestana === 'horarios' && <HorariosCatalogo {...propsPestana} />}
      </div>
    </>
  );
}
