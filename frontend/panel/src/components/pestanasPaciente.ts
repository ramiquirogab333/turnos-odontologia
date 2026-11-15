import type { Api } from '../lib/api';
import type { PacienteDetalle } from '../lib/tipos';
import type { RegistrarCambios } from './useCambiosPendientes';

/** Lo que el detalle le pasa a cada pestaña que lee un recurso del paciente (ficha, odontograma o presupuestos). */
export interface PropsPestana<T> {
  readonly api: Api;
  readonly paciente: PacienteDetalle;
  /** Lo cargado (el pedido salió al abrir la pestaña, R2). */
  readonly datos: T;
  /** Vuelve a pedir el recurso («Actualizar» o «Reintentar»). */
  readonly onActualizar: () => void;
  /** Reemplaza lo cargado con la respuesta de una escritura (sin otro pedido). */
  readonly onReemplazar: (valor: T) => void;
  readonly registrarCambios: RegistrarCambios;
}
