import type { Api } from '../lib/api';
import type { CatalogoAdmin } from '../lib/tipos';

/** Lo que cada pestaña del catálogo recibe: los datos ya cargados y cómo avisar de un cambio. */
export interface PropsPestanaCatalogo {
  readonly api: Api;
  readonly datos: CatalogoAdmin;
  readonly cambiar: (actualizar: (actuales: CatalogoAdmin) => CatalogoAdmin) => void;
  readonly avisar: (texto: string) => void;
}

/** Reemplaza la fila con el mismo `id` o, si es nueva, la agrega al final. */
export function reemplazarEn<T extends { readonly id: number }>(lista: readonly T[], item: T): readonly T[] {
  return lista.some((x) => x.id === item.id) ? lista.map((x) => (x.id === item.id ? item : x)) : [...lista, item];
}

export function sacarDe<T extends { readonly id: number }>(lista: readonly T[], id: number): readonly T[] {
  return lista.filter((x) => x.id !== id);
}

/** Campo del formulario al que apunta un error del servidor (el servidor habla en nombres de columna). */
export function campoDeFormulario(campo: string | undefined): string | undefined {
  if (campo === 'duracion_minutos') return 'duracion';
  if (campo === 'precio_base') return 'precio';
  if (campo === 'hora_inicio') return 'inicio';
  if (campo === 'hora_fin') return 'fin';
  return campo;
}

export const MENSAJE_GUARDADO = 'Guardamos los cambios';
