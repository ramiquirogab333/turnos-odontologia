import { useId, useState } from 'react';
import type { Api } from '../lib/api';
import { iniciar } from '../lib/iniciar';
import { mensajeDeErrorPaciente, validarPaciente, type CampoPaciente, type FormularioPaciente } from '../lib/pacientes';
import { ErrorSesion } from '../lib/sesion';
import type { PacienteDetalle, Ref } from '../lib/tipos';
import { Carga } from './Carga';

export interface Precargado {
  readonly dni?: string;
  readonly telefono?: string;
  readonly nombre?: string;
  readonly apellido?: string;
}

interface Props {
  readonly api: Api;
  /** El paciente a editar; `null` para un alta. */
  readonly paciente: PacienteDetalle | null;
  readonly precargado?: Precargado | undefined;
  readonly onGuardado: (paciente: PacienteDetalle) => void;
}

function valoresIniciales(paciente: PacienteDetalle | null, precargado: Precargado | undefined): FormularioPaciente {
  return {
    nombre: paciente?.nombre ?? precargado?.nombre ?? '',
    apellido: paciente?.apellido ?? precargado?.apellido ?? '',
    dni: paciente?.dni ?? precargado?.dni ?? '',
    telefono: paciente?.telefono ?? precargado?.telefono ?? '',
    email: paciente?.email ?? '',
    obraSocialId: paciente?.obra_social === null || paciente === null ? '' : String(paciente.obra_social.id),
    numeroAfiliado: paciente?.numero_afiliado ?? '',
  };
}

/** Alta y edición de los datos administrativos del paciente (mismo formulario, C-11 O1; última escritura gana, O13). */
export function FormPaciente({ api, paciente, precargado, onGuardado }: Props) {
  const [obras, setObras] = useState(() => iniciar(() => api.obrasSociales()));
  return (
    <Carga
      pendiente={obras}
      textoCarga="Cargando obras sociales…"
      mensajeError="No pudimos cargar las obras sociales. Revisá tu conexión e intentá de nuevo."
      onReintentar={() => {
        setObras(iniciar(() => api.obrasSociales()));
      }}
    >
      {(lista) => (
        <Formulario
          api={api}
          paciente={paciente}
          precargado={precargado}
          obras={lista}
          onGuardado={onGuardado}
          onRecargarObras={() => {
            setObras(iniciar(() => api.obrasSociales()));
          }}
        />
      )}
    </Carga>
  );
}

interface PropsFormulario extends Props {
  readonly obras: readonly Ref[];
  readonly onRecargarObras: () => void;
}

function Formulario({ api, paciente, precargado, obras, onGuardado, onRecargarObras }: PropsFormulario) {
  const edita = paciente !== null;
  const idBase = useId();
  const [valores, setValores] = useState(() => valoresIniciales(paciente, precargado));
  const [errores, setErrores] = useState<Partial<Record<CampoPaciente, string>>>({});
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [existente, setExistente] = useState<PacienteDetalle | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [guardado, setGuardado] = useState(false);

  function cambiar(campo: CampoPaciente, valor: string): void {
    setValores((v) => ({ ...v, [campo]: valor }));
    setGuardado(false);
  }

  async function enviar(): Promise<void> {
    if (enviando) return;
    const { errores: nuevos, datos } = validarPaciente(valores);
    setErrores(nuevos);
    setRechazo(null);
    setExistente(null);
    setGuardado(false);
    if (datos === null) return;
    setEnviando(true);
    try {
      const resultado = paciente === null ? await api.crearPaciente(datos) : await api.editarPaciente(paciente.id, datos);
      if (resultado.ok) {
        setGuardado(true);
        onGuardado(resultado.valor);
        return;
      }
      setRechazo(mensajeDeErrorPaciente(resultado.error));
      if (resultado.error.tipo === 'obra_social_inactiva') onRecargarObras();
      if (resultado.error.tipo === 'dni_duplicado') {
        const encontrados = await api.buscarPorDni(datos.dni).catch(() => []);
        setExistente(encontrados[0] ?? null);
      }
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    } finally {
      setEnviando(false);
    }
  }

  const campo = (clave: CampoPaciente, etiqueta: string, atributos: { readonly tipo?: string; readonly modo?: 'numeric' | 'tel' | 'email'; readonly max?: number }) => {
    const id = `${idBase}-${clave}`;
    const error = errores[clave];
    return (
      <div className="campo">
        <label htmlFor={id}>{etiqueta}</label>
        <input
          id={id}
          type={atributos.tipo ?? 'text'}
          inputMode={atributos.modo}
          autoComplete="off"
          maxLength={atributos.max}
          value={valores[clave]}
          aria-invalid={error !== undefined}
          aria-describedby={error === undefined ? undefined : `${id}-error`}
          onChange={(e) => {
            cambiar(clave, e.target.value);
          }}
        />
        {error !== undefined && (
          <p className="campo-error" id={`${id}-error`}>
            {error}
          </p>
        )}
      </div>
    );
  };

  const actual = paciente?.obra_social ?? null;
  const faltaActual = actual !== null && !obras.some((o) => o.id === actual.id);

  return (
    <form
      className="form-paciente"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      {campo('nombre', 'Nombre', { max: 100 })}
      {campo('apellido', 'Apellido', { max: 100 })}
      {campo('dni', 'DNI', { modo: 'numeric', max: 12 })}
      {campo('telefono', 'Teléfono', { tipo: 'tel', modo: 'tel', max: 20 })}
      {campo('email', 'Email (opcional)', { tipo: 'email', modo: 'email', max: 120 })}
      <div className="campo">
        <label htmlFor={`${idBase}-obra`}>Obra social</label>
        <select
          id={`${idBase}-obra`}
          value={valores.obraSocialId}
          onChange={(e) => {
            cambiar('obraSocialId', e.target.value);
          }}
        >
          <option value="">Sin obra social</option>
          {faltaActual && <option value={String(actual.id)}>{actual.nombre} (inactiva)</option>}
          {obras.map((o) => (
            <option key={o.id} value={String(o.id)}>
              {o.nombre}
            </option>
          ))}
        </select>
      </div>
      {campo('numeroAfiliado', 'Número de afiliado (opcional)', { max: 40 })}
      {rechazo !== null && (
        <div className="aviso aviso-error" role="alert">
          <p>{rechazo}</p>
          {existente !== null && (
            <a href={`#/pacientes/${String(existente.id)}`}>
              Ver a {existente.nombre} {existente.apellido}
            </a>
          )}
        </div>
      )}
      {guardado && edita && (
        <p className="aviso aviso-exito" role="status">
          Cambios guardados
        </p>
      )}
      <div className="acciones">
        <button type="submit" className="boton boton-primario" disabled={enviando}>
          {enviando ? 'Guardando…' : edita ? 'Guardar cambios' : 'Guardar paciente'}
        </button>
      </div>
    </form>
  );
}
