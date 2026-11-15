import type { DatosPaciente, ErrorClinico } from './tipos';

/** Lo que se escribe en el formulario del paciente (todo texto, como lo entrega un `input`). */
export interface FormularioPaciente {
  readonly nombre: string;
  readonly apellido: string;
  readonly dni: string;
  readonly telefono: string;
  readonly email: string;
  /** Id de la obra social elegida, o '' para «Sin obra social». */
  readonly obraSocialId: string;
  readonly numeroAfiliado: string;
}

export type CampoPaciente = keyof FormularioPaciente;

export interface ResultadoValidacion {
  readonly errores: Partial<Record<CampoPaciente, string>>;
  /** `null` si hay algún error: no se envía nada. */
  readonly datos: DatosPaciente | null;
}

const DNI = /^[0-9]{7,8}$/;
const E164 = /^\+[1-9]\d{1,14}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** El DNI se escribe a veces con puntos o espacios: el servidor pide solo los 7 u 8 números. */
export function normalizarDni(texto: string): string {
  return texto.replace(/[.\s]/g, '');
}

/** Igual que `PacienteCreate` del servidor; el servidor sigue siendo la barrera. */
export function validarPaciente(f: FormularioPaciente): ResultadoValidacion {
  const errores: { -readonly [C in CampoPaciente]?: string } = {};
  const nombre = f.nombre.trim();
  const apellido = f.apellido.trim();
  const dni = normalizarDni(f.dni);
  const telefono = f.telefono.trim();
  const email = f.email.trim();
  const afiliado = f.numeroAfiliado.trim();

  if (nombre.length < 1 || nombre.length > 100) errores.nombre = 'Escribí el nombre (hasta 100 caracteres)';
  if (apellido.length < 1 || apellido.length > 100) errores.apellido = 'Escribí el apellido (hasta 100 caracteres)';
  if (!DNI.test(dni)) errores.dni = 'El DNI tiene 7 u 8 números, sin puntos';
  if (!E164.test(telefono)) errores.telefono = 'Escribí el teléfono con código de país, por ejemplo +5491100000002';
  if (email !== '' && (email.length > 120 || !EMAIL.test(email))) errores.email = 'El email no parece válido';
  if (afiliado.length > 40) errores.numeroAfiliado = 'El número de afiliado admite hasta 40 caracteres';

  if (Object.keys(errores).length > 0) return { errores, datos: null };
  return {
    errores,
    datos: {
      nombre,
      apellido,
      dni,
      telefono,
      email: email === '' ? null : email,
      obra_social_id: f.obraSocialId === '' ? null : Number(f.obraSocialId),
      numero_afiliado: afiliado === '' ? null : afiliado,
    },
  };
}

/** Sugerencia editable: la última palabra es el apellido y el resto el nombre. */
export function separarContacto(contacto: string | null): { readonly nombre: string; readonly apellido: string } {
  const palabras = (contacto ?? '').trim().split(/\s+/).filter((p) => p !== '');
  if (palabras.length === 0) return { nombre: '', apellido: '' };
  if (palabras.length === 1) return { nombre: palabras[0] ?? '', apellido: '' };
  return { nombre: palabras.slice(0, -1).join(' '), apellido: palabras[palabras.length - 1] ?? '' };
}

export function mensajeDeErrorPaciente(error: ErrorClinico): string {
  switch (error.tipo) {
    case 'dni_duplicado':
      return 'Ya hay un paciente con ese DNI';
    case 'obra_social_inactiva':
      return 'Esa obra social ya no está activa. Elegí otra o «Sin obra social»';
    case 'sin_permiso':
      return 'Tu usuario no puede hacer este cambio.';
    case 'validacion':
      return error.mensaje;
    case 'no_encontrado':
      return 'No encontramos ese paciente.';
    default:
      return 'No pudimos guardar el paciente. Revisá tu conexión e intentá de nuevo.';
  }
}
