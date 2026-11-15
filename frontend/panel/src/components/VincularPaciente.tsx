import { useEffect, useId, useRef, useState } from 'react';
import type { Api } from '../lib/api';
import { normalizarDni, separarContacto } from '../lib/pacientes';
import { ErrorSesion } from '../lib/sesion';
import type { ErrorClinico, PacienteDetalle, TurnoAgenda } from '../lib/tipos';
import { FormPaciente } from './FormPaciente';

interface Props {
  readonly api: Api;
  readonly turno: TurnoAgenda;
  /** El turno quedó vinculado: la agenda se vuelve a pedir. */
  readonly onVinculado: () => void;
  readonly onCerrar: () => void;
}

type Paso =
  | { readonly tipo: 'buscar' }
  | { readonly tipo: 'confirmar'; readonly paciente: PacienteDetalle }
  | { readonly tipo: 'alta' }
  /** El alta ya se creó: solo falta vincular (nunca un segundo alta). */
  | { readonly tipo: 'reintento'; readonly pacienteId: number };

type Resultado =
  | { readonly tipo: 'ninguno' }
  | { readonly tipo: 'encontrado'; readonly paciente: PacienteDetalle }
  | { readonly tipo: 'no_registrado' }
  | { readonly tipo: 'mismo' };

const DNI = /^[0-9]{7,8}$/;

function mensajeDeVinculo(error: ErrorClinico): string {
  switch (error.tipo) {
    case 'sin_permiso':
      return 'Tu usuario no puede vincular turnos.';
    case 'no_encontrado':
      return 'Ese turno o ese paciente ya no existe. Cerrá este cuadro y actualizá la agenda.';
    default:
      return 'No pudimos vincular el turno. Revisá tu conexión e intentá de nuevo.';
  }
}

/** Diálogo para vincular (o corregir el vínculo de) un turno con su paciente: DNI exacto, vincular o dar de alta y vincular. */
export function VincularPaciente({ api, turno, onVinculado, onCerrar }: Props) {
  const idTitulo = useId();
  const idDni = useId();
  const tituloRef = useRef<HTMLHeadingElement>(null);
  const [paso, setPaso] = useState<Paso>({ tipo: 'buscar' });
  const [dni, setDni] = useState('');
  const [errorDni, setErrorDni] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado>({ tipo: 'ninguno' });
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const corrige = turno.paciente_id !== null;

  useEffect(() => {
    tituloRef.current?.focus();
  }, []);

  async function ejecutar<T>(accion: () => Promise<T>): Promise<T | null> {
    if (ocupado) return null;
    setOcupado(true);
    setRechazo(null);
    try {
      return await accion();
    } catch (error) {
      if (error instanceof ErrorSesion) return null; // la app vuelve sola al ingreso
      throw error;
    } finally {
      setOcupado(false);
    }
  }

  async function buscar(): Promise<void> {
    const normalizado = normalizarDni(dni);
    if (!DNI.test(normalizado)) {
      setErrorDni('El DNI tiene 7 u 8 números, sin puntos');
      return;
    }
    setErrorDni(null);
    const encontrados = await ejecutar(() => api.buscarPorDni(normalizado).catch(() => null));
    if (encontrados === null) {
      setRechazo('No pudimos buscar el DNI. Revisá tu conexión e intentá de nuevo.');
      return;
    }
    const paciente = encontrados[0];
    if (paciente === undefined) setResultado({ tipo: 'no_registrado' });
    else if (paciente.id === turno.paciente_id) setResultado({ tipo: 'mismo' });
    else setResultado({ tipo: 'encontrado', paciente });
  }

  async function vincular(pacienteId: number, tras: 'alta' | 'busqueda'): Promise<void> {
    const r = await ejecutar(() => api.vincularTurno(turno.id, pacienteId).catch((): null => null));
    if (r === null || !r.ok) {
      if (tras === 'alta') {
        setPaso({ tipo: 'reintento', pacienteId });
        setRechazo(r === null ? null : mensajeDeVinculo(r.error));
      } else {
        setRechazo(r === null ? mensajeDeVinculo({ tipo: 'desconocido' }) : mensajeDeVinculo(r.error));
      }
      return;
    }
    onVinculado();
  }

  const contacto = separarContacto(turno.paciente_nombre);

  return (
    <div className="velo">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        className="dialogo dialogo-ancho"
        onKeyDown={(e) => {
          if (e.key === 'Escape' && !ocupado) onCerrar();
        }}
      >
        <h2 id={idTitulo} ref={tituloRef} tabIndex={-1}>
          {corrige ? 'Cambiar paciente del turno' : 'Vincular paciente'}
        </h2>
        <p className="nota">
          {turno.paciente_nombre ?? 'Turno sin nombre'} · {turno.tratamiento.nombre}
        </p>

        {paso.tipo === 'buscar' && (
          <>
            <div className="campo">
              <label htmlFor={idDni}>DNI del paciente</label>
              <input
                id={idDni}
                type="text"
                inputMode="numeric"
                autoComplete="off"
                value={dni}
                aria-invalid={errorDni !== null}
                onChange={(e) => {
                  setDni(e.target.value);
                  setResultado({ tipo: 'ninguno' });
                  setErrorDni(null);
                }}
              />
              {errorDni !== null && <p className="campo-error">{errorDni}</p>}
            </div>
            {resultado.tipo === 'encontrado' && (
              <div className="aviso aviso-info" role="status">
                <p>
                  {resultado.paciente.nombre} {resultado.paciente.apellido} · DNI {resultado.paciente.dni}
                </p>
                <button
                  type="button"
                  className="boton boton-primario"
                  disabled={ocupado}
                  onClick={() => {
                    if (corrige) setPaso({ tipo: 'confirmar', paciente: resultado.paciente });
                    else void vincular(resultado.paciente.id, 'busqueda');
                  }}
                >
                  Vincular a {resultado.paciente.nombre} {resultado.paciente.apellido}
                </button>
              </div>
            )}
            {resultado.tipo === 'mismo' && (
              <p className="aviso aviso-info" role="status">
                El turno ya está vinculado con esta paciente
              </p>
            )}
            {resultado.tipo === 'no_registrado' && (
              <div className="aviso aviso-info" role="status">
                <p>No hay ningún paciente con ese DNI</p>
                <button
                  type="button"
                  className="boton boton-primario"
                  onClick={() => {
                    setPaso({ tipo: 'alta' });
                  }}
                >
                  Dar de alta y vincular
                </button>
              </div>
            )}
          </>
        )}

        {paso.tipo === 'confirmar' && (
          <div className="aviso aviso-info" role="status">
            <p>
              Vas a vincular este turno con {paso.paciente.nombre} {paso.paciente.apellido}. La profesional del turno puede ganar o perder acceso clínico a cada paciente con este cambio.
            </p>
          </div>
        )}

        {paso.tipo === 'alta' && (
          <FormPaciente
            api={api}
            paciente={null}
            precargado={{ dni: normalizarDni(dni), telefono: turno.paciente_telefono ?? '', nombre: contacto.nombre, apellido: contacto.apellido }}
            onGuardado={(creado) => {
              void vincular(creado.id, 'alta');
            }}
          />
        )}

        {paso.tipo === 'reintento' && (
          <div className="aviso aviso-error" role="alert">
            <p>Creamos el paciente pero no pudimos vincular el turno</p>
            <button
              type="button"
              className="boton boton-primario"
              disabled={ocupado}
              onClick={() => {
                void vincular(paso.pacienteId, 'alta');
              }}
            >
              Reintentar vínculo
            </button>
          </div>
        )}

        {rechazo !== null && (
          <p className="aviso aviso-error" role="alert">
            {rechazo}
          </p>
        )}

        <div className="acciones">
          {paso.tipo === 'confirmar' ? (
            <>
              <button
                type="button"
                className="boton boton-secundario"
                disabled={ocupado}
                onClick={() => {
                  setPaso({ tipo: 'buscar' });
                }}
              >
                Volver
              </button>
              <button type="button" className="boton boton-primario" disabled={ocupado} onClick={() => void vincular(paso.paciente.id, 'busqueda')}>
                {ocupado ? 'Guardando…' : 'Confirmar el cambio'}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="boton boton-secundario" disabled={ocupado} onClick={onCerrar}>
                Cancelar
              </button>
              {paso.tipo === 'buscar' && (
                <button type="button" className="boton boton-primario" disabled={ocupado} onClick={() => void buscar()}>
                  Buscar
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
