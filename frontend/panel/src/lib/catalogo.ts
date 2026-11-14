import type {
  DatosProfesional,
  DatosSillon,
  DatosTratamiento,
  ErrorCatalogo,
  FranjaAdmin,
  Impacto,
  RecursoCatalogo,
} from './tipos';

/** Mismos topes que el backend (`app/catalogo/schemas.py`, O12): cambiar uno exige cambiar el otro. */
export const DURACION_MIN = 5;
export const DURACION_MAX = 480;
export const DURACION_PASO = 5;
export const PRECIO_MAX = '99999999.99';

export const NOMBRES_DIA: readonly string[] = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

export interface DiaDeFranjas {
  readonly dia: number;
  readonly nombre: string;
  readonly franjas: readonly FranjaAdmin[];
}

/** Siete bloques, de lunes a domingo, con las franjas de cada día por hora de inicio (los días vacíos también). */
export function agruparPorDia(franjas: readonly FranjaAdmin[]): readonly DiaDeFranjas[] {
  return NOMBRES_DIA.map((nombre, dia) => ({
    dia,
    nombre,
    franjas: franjas.filter((f) => f.dia_semana === dia).sort((a, b) => a.hora_inicio.localeCompare(b.hora_inicio)),
  }));
}

/** "09:00:00" → "09:00". */
export function horaCorta(hora: string): string {
  return hora.slice(0, 5);
}

export function formatoDuracion(minutos: number): string {
  return `${String(minutos)} min`;
}

const DECIMAL = /^(\d+)(?:\.(\d+))?$/;

/** "18500.00" → "$ 18.500"; con centavos distintos de cero, "$ 1.234.567,50". Solo presentación. */
export function formatoPrecio(precio: string): string {
  const partes = DECIMAL.exec(precio);
  if (partes === null) return '—';
  const enteros = (partes[1] ?? '0').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const centavos = (partes[2] ?? '').padEnd(2, '0').slice(0, 2);
  return centavos === '00' ? `$ ${enteros}` : `$ ${enteros},${centavos}`;
}

export interface Validacion<T> {
  /** Mensaje por campo del formulario; vacío si todo está bien. */
  readonly campos: Readonly<Record<string, string>>;
  readonly valor: T | null;
}

const MENSAJE_DURACION = `La duración va de ${String(DURACION_MIN)} a ${String(DURACION_MAX)} minutos, en múltiplos de ${String(DURACION_PASO)}`;

function validarDuracion(texto: string): number | null {
  const limpio = texto.trim();
  if (!/^\d+$/.test(limpio)) return null;
  const minutos = Number(limpio);
  return minutos >= DURACION_MIN && minutos <= DURACION_MAX && minutos % DURACION_PASO === 0 ? minutos : null;
}

/** Precio como texto decimal con dos cifras ("18500" → "18500.00"), o `null` si no es válido. */
function normalizarPrecio(texto: string): string | null {
  const partes = DECIMAL.exec(texto.trim().replace(',', '.'));
  if (partes === null) return null;
  const decimales = partes[2] ?? '';
  if (decimales.length > 2) return null;
  const enteros = (partes[1] ?? '0').replace(/^0+(?=\d)/, '');
  const normal = `${enteros}.${decimales.padEnd(2, '0')}`;
  return enteros.length > 8 || (enteros.length === 8 && normal > PRECIO_MAX) ? null : normal;
}

function validarLargo(texto: string, maximo: number, vacio: string): string | null {
  const largo = texto.trim().length;
  if (largo === 0) return vacio;
  return largo > maximo ? `Admite hasta ${String(maximo)} caracteres.` : null;
}

function resultado<T>(campos: Record<string, string>, valor: T): Validacion<T> {
  return Object.keys(campos).length === 0 ? { campos, valor } : { campos, valor: null };
}

export function validarTratamiento(form: {
  readonly nombre: string;
  readonly duracion: string;
  readonly precio: string;
}): Validacion<DatosTratamiento> {
  const campos: Record<string, string> = {};
  const errorNombre = validarLargo(form.nombre, 120, 'Ingresá el nombre.');
  if (errorNombre !== null) campos['nombre'] = errorNombre;
  const duracion = validarDuracion(form.duracion);
  if (duracion === null) campos['duracion'] = MENSAJE_DURACION;
  const precio = normalizarPrecio(form.precio);
  if (precio === null) campos['precio'] = `El precio va de 0 a ${formatoPrecio(PRECIO_MAX)}, con hasta dos decimales`;
  return resultado(campos, {
    nombre: form.nombre.trim(),
    duracion_minutos: duracion ?? 0,
    precio_base: precio ?? '0.00',
  });
}

export function validarProfesional(form: DatosProfesional): Validacion<DatosProfesional> {
  const campos: Record<string, string> = {};
  const errorNombre = validarLargo(form.nombre, 120, 'Ingresá el nombre.');
  if (errorNombre !== null) campos['nombre'] = errorNombre;
  const errorMatricula = validarLargo(form.matricula, 40, 'Ingresá la matrícula.');
  if (errorMatricula !== null) campos['matricula'] = errorMatricula;
  if (form.especialidad.trim().length > 120) campos['especialidad'] = 'Admite hasta 120 caracteres.';
  return resultado(campos, {
    nombre: form.nombre.trim(),
    matricula: form.matricula.trim(),
    especialidad: form.especialidad.trim(),
  });
}

export function validarSillon(form: DatosSillon): Validacion<DatosSillon> {
  const campos: Record<string, string> = {};
  const errorNombre = validarLargo(form.nombre, 60, 'Ingresá el nombre.');
  if (errorNombre !== null) campos['nombre'] = errorNombre;
  return resultado(campos, { nombre: form.nombre.trim(), estado: form.estado });
}

export function validarFranja(form: { readonly inicio: string; readonly fin: string }): Validacion<{
  readonly inicio: string;
  readonly fin: string;
}> {
  const campos: Record<string, string> = {};
  if (form.inicio === '') campos['inicio'] = 'Elegí la hora de inicio.';
  if (form.fin === '') campos['fin'] = 'Elegí la hora de fin.';
  else if (form.inicio !== '' && form.fin <= form.inicio) campos['fin'] = 'La hora de fin tiene que ser posterior a la de inicio';
  return resultado(campos, { inicio: form.inicio, fin: form.fin });
}

export interface MensajeCatalogo {
  readonly mensaje: string;
  /** Campo del formulario al que pertenece el error, si lo hay. */
  readonly campo?: string;
}

const LEYENDA_DUPLICADO: Readonly<Record<string, string>> = {
  'profesionales:matricula': 'Ya hay una profesional con esa matrícula',
  'profesionales:nombre': 'Ya hay una profesional con ese nombre',
  'tratamientos:nombre': 'Ya hay un tratamiento con ese nombre',
  'sillones:nombre': 'Ya hay un sillón con ese nombre',
};

/** Traduce el rechazo del servidor a una frase que explica qué pasó y cómo seguir. */
export function mensajeDeCatalogo(error: ErrorCatalogo, recurso: RecursoCatalogo): MensajeCatalogo {
  switch (error.tipo) {
    case 'en_uso':
      return {
        mensaje: 'No se puede borrar porque tiene turnos registrados. Podés desactivarlo para que no se ofrezca más.',
      };
    case 'duplicado': {
      const campo = error.campo ?? 'nombre';
      const frase = LEYENDA_DUPLICADO[`${recurso}:${campo}`] ?? 'Ya existe un registro con ese dato';
      return { campo, mensaje: frase };
    }
    case 'franja_superpuesta': {
      if (error.franja === null) return { mensaje: 'Se superpone con otra franja activa de este día' };
      const dia = (NOMBRES_DIA[error.franja.dia_semana] ?? '').toLowerCase();
      return {
        mensaje: `Se superpone con la franja de ${horaCorta(error.franja.hora_inicio)} a ${horaCorta(error.franja.hora_fin)} del ${dia}`,
      };
    }
    case 'no_reservable':
      return { mensaje: 'Ese elemento no se ofrece para reservar. Reactivalo o elegí otro.' };
    case 'validacion':
      return error.campo === null ? { mensaje: error.mensaje } : { campo: error.campo, mensaje: error.mensaje };
    case 'sin_permiso':
      return { mensaje: 'No tenés permiso para hacer este cambio. Pedile acceso a la clínica.' };
    case 'no_encontrado':
      return { mensaje: 'Eso ya no existe. Recargá la pantalla para ver la lista actualizada.' };
    case 'desconocido':
      return { mensaje: 'No pudimos guardar el cambio. Intentá de nuevo en unos minutos.' };
  }
}

/** Frase del diálogo de confirmación; `null` = no se pudo consultar el impacto (se puede seguir igual). */
export function textoDeImpacto(impacto: Impacto | null, donde: string): string {
  if (impacto === null) {
    return 'No pudimos revisar los turnos tomados; los turnos existentes no se cancelan igual.';
  }
  const n = impacto.turnos_futuros;
  if (n === 0) return `No hay turnos tomados ${donde}.`;
  if (n === 1) return `Hay 1 turno tomado ${donde}. No se cancela: sigue en la agenda.`;
  return `Hay ${String(n)} turnos tomados ${donde}. No se cancelan: siguen en la agenda.`;
}
