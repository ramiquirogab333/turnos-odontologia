import { useRef, useState } from 'react';
import { ErrorSesion } from '../lib/sesion';
import type { ErrorCatalogo, Resultado } from '../lib/tipos';

/**
 * Un envío del catálogo a la vez: el segundo toque mientras el primero espera no sale (el `ref` corta antes de que React
 * repinte el botón deshabilitado). Si la sesión terminó devuelve `null` (la app vuelve sola al ingreso).
 */
export function useAccionCatalogo() {
  const [enviando, setEnviando] = useState(false);
  const ocupado = useRef(false);

  async function ejecutar<T>(pedido: () => Promise<Resultado<T, ErrorCatalogo>>): Promise<Resultado<T, ErrorCatalogo> | null> {
    if (ocupado.current) return null;
    ocupado.current = true;
    setEnviando(true);
    try {
      return await pedido();
    } catch (error) {
      if (error instanceof ErrorSesion) return null;
      return { ok: false, error: { tipo: 'desconocido' } };
    } finally {
      ocupado.current = false;
      setEnviando(false);
    }
  }

  return { enviando, ejecutar };
}
