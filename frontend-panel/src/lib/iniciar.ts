import { ErrorSesion } from './sesion';

/**
 * Arranca el pedido ya y evita el aviso de rechazo sin manejar: el error lo recoge el ErrorBoundary vía `use()`.
 * Si la sesión terminó, la app ya volvió al ingreso (lo hace el oyente de la sesión): acá no hay nada que mostrar.
 */
export function iniciar<T>(pedido: () => Promise<T>): Promise<T> {
  const promesa = pedido().catch((error: unknown) => {
    if (error instanceof ErrorSesion) return new Promise<T>(() => undefined);
    throw error;
  });
  promesa.catch(() => undefined);
  return promesa;
}

/** "1 ausencia" / "2 ausencias". */
export function cantidad(n: number, singular: string, plural: string): string {
  return `${String(n)} ${n === 1 ? singular : plural}`;
}
