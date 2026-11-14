import { useEffect, useState } from 'react';
import type { Api } from '../lib/api';
import { mensajeDeCatalogo, textoDeImpacto } from '../lib/catalogo';
import { ErrorSesion } from '../lib/sesion';
import type { ErrorCatalogo, Impacto, RecursoCatalogo, Resultado } from '../lib/tipos';
import { Dialogo } from './Dialogo';
import { useAccionCatalogo } from './useAccionCatalogo';

interface Props {
  readonly api: Api;
  readonly recurso: RecursoCatalogo;
  readonly id: number;
  readonly titulo: string;
  /** Dónde se cuentan los turnos, con su preposición: "en esta franja", "con esta profesional"… */
  readonly donde: string;
  /** Qué pasa con las reservas nuevas (los turnos ya tomados no se tocan). */
  readonly consecuencia: string;
  readonly confirmar: string;
  readonly alConfirmar: () => Promise<Resultado<unknown, ErrorCatalogo>>;
  readonly alHecho: () => void;
  readonly alVolver: () => void;
  /** Si el servidor responde «en uso» se ofrece esta salida (desactivar en vez de borrar). */
  readonly alternativa?: { readonly etiqueta: string; readonly alElegir: () => void };
}

type Consulta = { readonly estado: 'cargando' } | { readonly estado: 'listo'; readonly impacto: Impacto | null };

/** Confirmación de un cambio que quita algo del catálogo: dice cuántos turnos tomados alcanza y que no se cancelan. */
export function ConfirmarCambioCatalogo({
  api,
  recurso,
  id,
  titulo,
  donde,
  consecuencia,
  confirmar,
  alConfirmar,
  alHecho,
  alVolver,
  alternativa,
}: Props) {
  const [consulta, setConsulta] = useState<Consulta>({ estado: 'cargando' });
  const [rechazo, setRechazo] = useState<ErrorCatalogo | null>(null);
  const { enviando, ejecutar } = useAccionCatalogo();

  useEffect(() => {
    let vigente = true;
    api
      .impactoCatalogo(recurso, id)
      .then((impacto) => ({ estado: 'listo', impacto }) as const)
      .catch((error: unknown) => {
        // Si la sesión terminó la app vuelve sola al ingreso; cualquier otra falla del impacto no bloquea el cambio.
        if (error instanceof ErrorSesion) return null;
        return { estado: 'listo', impacto: null } as const;
      })
      .then((resultado) => {
        if (vigente && resultado !== null) setConsulta(resultado);
      })
      .catch(() => undefined);
    return () => {
      vigente = false;
    };
  }, [api, recurso, id]);

  async function confirmarCambio(): Promise<void> {
    setRechazo(null);
    const resultado = await ejecutar(alConfirmar);
    if (resultado === null) return;
    if (resultado.ok) alHecho();
    else setRechazo(resultado.error);
  }

  const mensaje = rechazo === null ? null : mensajeDeCatalogo(rechazo, recurso).mensaje;

  return (
    <Dialogo
      titulo={titulo}
      confirmar={confirmar}
      enviando={enviando || consulta.estado === 'cargando'}
      rechazo={mensaje}
      onConfirmar={() => void confirmarCambio()}
      onVolver={alVolver}
    >
      {consulta.estado === 'cargando' ? (
        <p role="status">Revisando los turnos tomados…</p>
      ) : (
        <>
          <p>{textoDeImpacto(consulta.impacto, donde)}</p>
          <p>{consecuencia}</p>
        </>
      )}
      {rechazo?.tipo === 'en_uso' && alternativa !== undefined && (
        <button type="button" className="boton boton-secundario" onClick={alternativa.alElegir}>
          {alternativa.etiqueta}
        </button>
      )}
    </Dialogo>
  );
}
