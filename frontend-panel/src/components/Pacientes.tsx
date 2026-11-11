import { Suspense, startTransition, use, useEffect, useRef, useState, useTransition } from 'react';
import type { Api } from '../lib/api';
import { cantidad, iniciar } from '../lib/iniciar';
import { fechaCorta } from '../lib/tiempo';
import type { ConsultaPacientes, ListadoPacientes } from '../lib/tipos';
import { Cargando } from './Cargando';
import { ErrorBoundary } from './ErrorBoundary';
import { ErrorCarga } from './ErrorCarga';

interface Props {
  readonly api: Api;
  /** Espera tras la última tecla antes de consultar. */
  readonly esperaMs?: number;
}

const POR_PAGINA = 20;
const INICIAL: ConsultaPacientes = { q: null, pagina: 1, porPagina: POR_PAGINA, conAusencias: false };

function normalizar(texto: string): string {
  return texto.replace(/\s+/g, ' ').trim();
}

export function Pacientes({ api, esperaMs = 300 }: Props) {
  const [texto, setTexto] = useState('');
  const [consulta, setConsulta] = useState<ConsultaPacientes>(INICIAL);
  const [pendiente, setPendiente] = useState(() => iniciar(() => api.listarPacientes(INICIAL)));
  const [consultando, iniciarTransicion] = useTransition();
  const ultima = useRef<ConsultaPacientes>(INICIAL);
  const espera = useRef<number | undefined>(undefined);

  useEffect(
    () => () => {
      window.clearTimeout(espera.current);
    },
    [],
  );

  function consultar(cambios: Partial<ConsultaPacientes>): void {
    const nueva = { ...ultima.current, ...cambios };
    ultima.current = nueva;
    iniciarTransicion(() => {
      setConsulta(nueva);
      setPendiente(iniciar(() => api.listarPacientes(nueva)));
    });
  }

  function alEscribir(valor: string): void {
    setTexto(valor);
    window.clearTimeout(espera.current);
    const limpio = normalizar(valor);
    if (limpio.length === 1) return; // el servidor pide al menos 2 letras: se avisa y no se consulta
    espera.current = window.setTimeout(() => {
      consultar({ q: limpio === '' ? null : limpio, pagina: 1 });
    }, esperaMs);
  }

  function reintentar(): void {
    startTransition(() => {
      setPendiente(iniciar(() => api.listarPacientes(ultima.current)));
    });
  }

  return (
    <section className="pacientes" aria-label="Pacientes">
      <div className="barra">
        <div className="campo campo-busqueda">
          <label htmlFor="buscar-paciente">Buscar por nombre, apellido o DNI</label>
          <input
            id="buscar-paciente"
            type="search"
            autoComplete="off"
            value={texto}
            maxLength={60}
            onChange={(e) => {
              alEscribir(e.target.value);
            }}
          />
          {normalizar(texto).length === 1 && <p className="nota">Escribí al menos 2 letras para buscar.</p>}
        </div>
        <button
          type="button"
          className={`selector-boton filtro${consulta.conAusencias ? ' activo' : ''}`}
          aria-pressed={consulta.conAusencias}
          onClick={() => {
            consultar({ conAusencias: !ultima.current.conAusencias, pagina: 1 });
          }}
        >
          Con ausencias
        </button>
      </div>

      <div aria-busy={consultando}>
        <ErrorBoundary
          onReintentar={reintentar}
          fallback={(volver) => <ErrorCarga mensaje="No pudimos cargar los pacientes. Revisá tu conexión e intentá de nuevo." onReintentar={volver} />}
        >
          <Suspense fallback={<Cargando texto="Cargando pacientes…" />}>
            <Resultado
              pendiente={pendiente}
              consulta={consulta}
              onPagina={(pagina) => {
                consultar({ pagina });
              }}
            />
          </Suspense>
        </ErrorBoundary>
      </div>
    </section>
  );
}

interface PropsResultado {
  readonly pendiente: Promise<ListadoPacientes>;
  readonly consulta: ConsultaPacientes;
  readonly onPagina: (pagina: number) => void;
}

function Resultado({ pendiente, consulta, onPagina }: PropsResultado) {
  const datos = use(pendiente);
  const paginas = Math.max(1, Math.ceil(datos.total / datos.por_pagina));

  if (datos.pacientes.length === 0) {
    return consulta.q !== null ? (
      <div className="vacio">
        <p>No encontramos pacientes con «{consulta.q}»</p>
        <p className="nota">Probá con otra parte del nombre o buscá por DNI, solo con números.</p>
      </div>
    ) : (
      <p className="vacio">
        {consulta.conAusencias
          ? 'Nadie tiene ausencias registradas.'
          : 'Todavía no hay pacientes cargados. Se cargan al dar de alta un turno.'}
      </p>
    );
  }

  return (
    <>
      <ul className="lista-pacientes" aria-label="Pacientes">
        {datos.pacientes.map((p) => (
          <li key={p.id} className="paciente">
            <p className="paciente-nombre">
              {p.nombre} {p.apellido}
            </p>
            <p className="nota">
              DNI {p.dni} · {cantidad(p.atendidos, 'atendido', 'atendidos')} · {cantidad(p.ausentes, 'ausencia', 'ausencias')}
            </p>
            <p className="nota">
              {p.obra_social !== null ? `${p.obra_social.nombre} · ` : ''}
              {p.ultimo_turno !== null ? `Último turno: ${fechaCorta(p.ultimo_turno)}` : 'Sin turnos todavía'}
            </p>
          </li>
        ))}
      </ul>
      {paginas > 1 && (
        <nav className="paginacion" aria-label="Páginas de pacientes">
          <button type="button" className="boton boton-secundario" disabled={datos.pagina <= 1} aria-label="Página anterior" onClick={() => { onPagina(datos.pagina - 1); }}>
            ‹
          </button>
          <span>
            Página {datos.pagina} de {paginas}
          </span>
          <button type="button" className="boton boton-secundario" disabled={datos.pagina >= paginas} aria-label="Página siguiente" onClick={() => { onPagina(datos.pagina + 1); }}>
            ›
          </button>
        </nav>
      )}
    </>
  );
}
