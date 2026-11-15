import { useState } from 'react';
import type { Api } from '../lib/api';
import { etiquetaEstado } from '../lib/odontograma';
import { ErrorSesion } from '../lib/sesion';
import { fechaCorta, horaClinica } from '../lib/tiempo';
import type { RegistroOdontograma } from '../lib/tipos';

interface Props {
  readonly api: Api;
  readonly pacienteId: number;
}

type Fase =
  | { readonly tipo: 'cerrado' }
  | { readonly tipo: 'cargando_primera' }
  | { readonly tipo: 'error_primera' }
  | { readonly tipo: 'listo'; readonly registros: readonly RegistroOdontograma[]; readonly siguiente: number | null; readonly cargandoMas: boolean; readonly errorMas: boolean };

/** Historial del odontograma, del más reciente al más antiguo, en páginas de 50 con «Cargar más». Solo se pide al abrirlo (O7). */
export function HistorialOdontograma({ api, pacienteId }: Props) {
  const [fase, setFase] = useState<Fase>({ tipo: 'cerrado' });

  async function primera(): Promise<void> {
    setFase({ tipo: 'cargando_primera' });
    try {
      const pagina = await api.historialOdontograma(pacienteId, null);
      setFase({ tipo: 'listo', registros: pagina.registros, siguiente: pagina.siguiente_antes_de_id, cargandoMas: false, errorMas: false });
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      setFase({ tipo: 'error_primera' });
    }
  }

  async function mas(actual: Extract<Fase, { tipo: 'listo' }>): Promise<void> {
    if (actual.siguiente === null || actual.cargandoMas) return;
    setFase({ ...actual, cargandoMas: true, errorMas: false });
    try {
      const pagina = await api.historialOdontograma(pacienteId, actual.siguiente);
      const vistos = new Set(actual.registros.map((r) => r.id));
      setFase({
        tipo: 'listo',
        registros: [...actual.registros, ...pagina.registros.filter((r) => !vistos.has(r.id))],
        siguiente: pagina.siguiente_antes_de_id,
        cargandoMas: false,
        errorMas: false,
      });
    } catch (error) {
      if (error instanceof ErrorSesion) return;
      setFase({ ...actual, cargandoMas: false, errorMas: true });
    }
  }

  if (fase.tipo === 'cerrado') {
    return (
      <div className="acciones">
        <button type="button" className="boton boton-secundario" onClick={() => void primera()}>
          Ver historial
        </button>
      </div>
    );
  }
  if (fase.tipo === 'cargando_primera') {
    return (
      <p className="estado-carga" role="status">
        Cargando historial…
      </p>
    );
  }
  if (fase.tipo === 'error_primera') {
    return (
      <div className="aviso aviso-error" role="alert">
        <p>No pudimos cargar el historial</p>
        <button type="button" className="boton boton-secundario" onClick={() => void primera()}>
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <section className="historial-odontograma" aria-label="Historial del odontograma">
      <h3 className="subtitulo">Historial</h3>
      {fase.registros.length === 0 ? (
        <p className="vacio">Todavía no hay hallazgos registrados</p>
      ) : (
        <ul className="lista-historia" aria-label="Historial de hallazgos">
          {fase.registros.map((r) => (
            <li key={r.id} className="item-historia">
              <p>
                {fechaCorta(r.registrado_en)} · {horaClinica(r.registrado_en)} · Pieza {r.pieza}
                {r.cara !== null ? ` · ${r.cara}` : ''} · {etiquetaEstado(r.estado)}
              </p>
              {r.nota !== null && <p className="nota texto-largo">{r.nota}</p>}
            </li>
          ))}
        </ul>
      )}
      {fase.errorMas && (
        <div className="aviso aviso-error" role="alert">
          <p>No pudimos cargar más registros</p>
          <button type="button" className="boton boton-secundario" onClick={() => void mas(fase)}>
            Reintentar
          </button>
        </div>
      )}
      {fase.siguiente !== null && !fase.errorMas && (
        <div className="acciones">
          <button type="button" className="boton boton-secundario" disabled={fase.cargandoMas} onClick={() => void mas(fase)}>
            {fase.cargandoMas ? 'Cargando…' : 'Cargar más'}
          </button>
        </div>
      )}
    </section>
  );
}
