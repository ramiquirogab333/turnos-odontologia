import { useState } from 'react';
import { mensajeDeCaja, RECARGAN_CAJA, type ObjetoDeCaja } from '../lib/presentacion';
import { ErrorSesion } from '../lib/sesion';
import type { ErrorCaja, Resultado } from '../lib/tipos';

/** Estado de un envío con confirmación: evita el doble envío y traduce el rechazo del servidor a una frase. */
export function useEnvio(objeto: ObjetoDeCaja, alRecargar: () => void) {
  const [enviando, setEnviando] = useState(false);
  const [rechazo, setRechazo] = useState<string | null>(null);

  async function ejecutar<T>(pedido: () => Promise<Resultado<T, ErrorCaja>>, alExito: () => void): Promise<void> {
    if (enviando) return;
    setEnviando(true);
    setRechazo(null);
    let resultado: Resultado<T, ErrorCaja>;
    try {
      resultado = await pedido();
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    }
    setEnviando(false);
    if (resultado.ok) {
      alExito();
      return;
    }
    setRechazo(mensajeDeCaja(resultado.error, objeto));
    if (RECARGAN_CAJA.includes(resultado.error.tipo)) alRecargar();
  }

  return { enviando, rechazo, setRechazo, ejecutar };
}
