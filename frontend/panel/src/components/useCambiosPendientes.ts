import { useEffect } from 'react';

/** Qué se perdería al salir de una pestaña: el aviso y cómo se llaman los botones del diálogo. */
export interface AvisoCambios {
  readonly mensaje: string;
  readonly seguir: string;
  readonly descartar: string;
}

export type RegistrarCambios = (aviso: AvisoCambios | null) => void;

/**
 * Le avisa al detalle del paciente que la pestaña tiene cambios sin guardar mientras `aviso` no sea `null`. El detalle
 * pide confirmación al cambiar de pestaña o volver y activa `beforeunload` solo con cambios. Nada se guarda en el
 * navegador (Ley 25.326): al salir, lo escrito se descarta.
 */
export function useCambiosPendientes(registrar: RegistrarCambios, aviso: AvisoCambios | null): void {
  const mensaje = aviso?.mensaje ?? null;
  const seguir = aviso?.seguir ?? '';
  const descartar = aviso?.descartar ?? '';
  useEffect(() => {
    registrar(mensaje === null ? null : { mensaje, seguir, descartar });
    return () => {
      registrar(null);
    };
  }, [registrar, mensaje, seguir, descartar]);
}
