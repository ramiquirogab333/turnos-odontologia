import { useState } from 'react';
import type { Api } from '../lib/api';
import { mensajeDeExportacion, opcionesSegunRol } from '../lib/datos';
import { guardarArchivo } from '../lib/descarga';
import { ErrorSesion } from '../lib/sesion';
import type { ArchivoExportado, EntidadExportable, Rol } from '../lib/tipos';

interface Props {
  readonly api: Api;
  readonly roles: readonly Rol[];
  /** "Hoy" en la clínica ("YYYY-MM-DD"), para el nombre de respaldo del archivo. */
  readonly hoy: string;
  /** Entrega el archivo al navegador; se inyecta en las pruebas. */
  readonly guardar?: (archivo: ArchivoExportado) => void;
}

type Aviso = { readonly tipo: 'exito'; readonly nombre: string } | { readonly tipo: 'error'; readonly mensaje: string };

/** Descarga de CSV con la sesión vigente: el access viaja en la cabecera, nunca en la URL (C-13, D11). */
export function Exportar({ api, roles, hoy, guardar = guardarArchivo }: Props) {
  const opciones = opcionesSegunRol(roles);
  const [entidad, setEntidad] = useState<EntidadExportable>(opciones[0]?.entidad ?? 'turnos');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [preparando, setPreparando] = useState(false);
  const [aviso, setAviso] = useState<Aviso | null>(null);

  async function descargar(): Promise<void> {
    if (preparando) return;
    if (desde !== '' && hasta !== '' && desde > hasta) {
      setAviso({ tipo: 'error', mensaje: mensajeDeExportacion({ tipo: 'validacion' }) });
      return;
    }
    setPreparando(true);
    setAviso(null);
    try {
      const r = await api.descargarExportacion(
        { entidad, desde: desde === '' ? null : desde, hasta: hasta === '' ? null : hasta, incluirInactivos },
        hoy,
      );
      if (r.ok) {
        guardar(r.valor);
        setAviso({ tipo: 'exito', nombre: r.valor.nombre });
      } else {
        setAviso({ tipo: 'error', mensaje: mensajeDeExportacion(r.error) });
      }
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      setAviso({ tipo: 'error', mensaje: mensajeDeExportacion({ tipo: 'red' }) });
    } finally {
      setPreparando(false);
    }
  }

  return (
    <section className="exportar" aria-label="Exportar datos">
      <p className="nota">
        El archivo CSV contiene datos personales (Ley 25.326): guardalo en un lugar seguro y no lo compartas.
      </p>
      <div className="campo">
        <label htmlFor="exportar-entidad">¿Qué querés exportar?</label>
        <select
          id="exportar-entidad"
          value={entidad}
          onChange={(e) => {
            setEntidad(e.target.value as EntidadExportable);
          }}
        >
          {opciones.map((o) => (
            <option key={o.entidad} value={o.entidad}>
              {o.etiqueta}
            </option>
          ))}
        </select>
      </div>
      <div className="filtros">
        <div className="campo">
          <label htmlFor="exportar-desde">Desde (opcional)</label>
          <input
            id="exportar-desde"
            type="date"
            value={desde}
            onChange={(e) => {
              setDesde(e.target.value);
            }}
          />
        </div>
        <div className="campo">
          <label htmlFor="exportar-hasta">Hasta (opcional)</label>
          <input
            id="exportar-hasta"
            type="date"
            value={hasta}
            onChange={(e) => {
              setHasta(e.target.value);
            }}
          />
        </div>
      </div>
      {entidad === 'pacientes' && (
        <div className="campo campo-casilla">
          <label htmlFor="exportar-inactivos">
            <input
              id="exportar-inactivos"
              type="checkbox"
              checked={incluirInactivos}
              onChange={(e) => {
                setIncluirInactivos(e.target.checked);
              }}
            />{' '}
            Incluir pacientes inactivos
          </label>
        </div>
      )}
      <button
        type="button"
        className="boton boton-primario boton-ancho"
        disabled={preparando}
        onClick={() => {
          void descargar();
        }}
      >
        {preparando ? 'Preparando archivo…' : 'Descargar CSV'}
      </button>
      {aviso?.tipo === 'error' && (
        <div className="aviso aviso-error" role="alert">
          <p>{aviso.mensaje}</p>
        </div>
      )}
      {aviso?.tipo === 'exito' && (
        <div className="aviso aviso-exito" role="status">
          <p>Descargamos {aviso.nombre}.</p>
        </div>
      )}
    </section>
  );
}
