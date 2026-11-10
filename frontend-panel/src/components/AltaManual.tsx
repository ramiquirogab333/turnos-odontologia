import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import type { Api } from '../lib/api';
import { ErrorSesion } from '../lib/sesion';
import { etiquetaDiaLarga, horaClinica } from '../lib/tiempo';
import type { Alternativa, ErrorAlta, Opciones, Slot, TurnoCreado } from '../lib/tipos';
import { normalizarTelefono, validarNombre, validarTelefono } from '../lib/validacion';

interface Props {
  readonly api: Api;
  readonly opciones: Opciones;
  readonly fechaInicial: string;
  /** El turno ya existe: la agenda se recarga mientras recepción copia el código. */
  readonly onCreado: () => void;
  readonly onCerrar: () => void;
}

type Horarios =
  | { readonly estado: 'sin_elegir' }
  | { readonly estado: 'cargando' }
  | { readonly estado: 'error' }
  | { readonly estado: 'listo'; readonly slots: readonly Slot[] };

/** Lo último que respondió el servidor, atado a la consulta que lo originó. */
interface Respuesta {
  readonly clave: string;
  readonly slots: readonly Slot[] | null;
}

/** Un horario elegido: viene de la grilla de libres o de las alternativas que devolvió el servidor. */
interface Elegido {
  readonly inicio: string;
}

function textoDeRechazo(error: ErrorAlta): string | null {
  switch (error.tipo) {
    case 'conflicto':
      return null; // tiene su propia presentación con alternativas
    case 'fuera_de_disponibilidad':
      return 'Ese horario está fuera de la atención de la profesional. Elegí otro.';
    case 'inicio_pasado':
      return 'Ese horario ya pasó. Elegí uno futuro.';
    case 'validacion':
      return error.mensaje;
    case 'sin_permiso':
      return 'Tu usuario no puede cargar turnos.';
    case 'desconocido':
      return 'No pudimos crear el turno. Probá de nuevo; si sigue igual, avisá a la clínica.';
  }
}

export function AltaManual({ api, opciones, fechaInicial, onCreado, onCerrar }: Props) {
  const id = useId();
  const tituloRef = useRef<HTMLHeadingElement>(null);
  const [tratamientoId, setTratamientoId] = useState<number | null>(null);
  const [profesionalId, setProfesionalId] = useState<number | null>(null);
  const [dia, setDia] = useState(fechaInicial);
  const [respuesta, setRespuesta] = useState<Respuesta | null>(null);
  const [reintento, setReintento] = useState(0);
  const [elegido, setElegido] = useState<Elegido | null>(null);
  const [nombre, setNombre] = useState('');
  const [telefono, setTelefono] = useState('');
  const [errores, setErrores] = useState<{ nombre?: string; telefono?: string; general?: string }>({});
  const [conflicto, setConflicto] = useState<readonly Alternativa[] | null>(null);
  const [rechazo, setRechazo] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [creado, setCreado] = useState<TurnoCreado | null>(null);

  useEffect(() => {
    tituloRef.current?.focus();
  }, [creado]);

  // La disponibilidad se pide solo cuando ya hay tratamiento y profesional (y se repite si cambia el día).
  const clave =
    tratamientoId === null || profesionalId === null || dia === ''
      ? null
      : `${String(profesionalId)}|${String(tratamientoId)}|${dia}|${String(reintento)}`;
  const horarios: Horarios =
    clave === null
      ? { estado: 'sin_elegir' }
      : respuesta?.clave !== clave
        ? { estado: 'cargando' }
        : respuesta.slots === null
          ? { estado: 'error' }
          : { estado: 'listo', slots: respuesta.slots };

  useEffect(() => {
    if (clave === null || tratamientoId === null || profesionalId === null) return;
    let vigente = true;
    api
      .disponibilidad(profesionalId, tratamientoId, dia)
      .then((slots) => {
        if (vigente) setRespuesta({ clave, slots });
      })
      .catch(() => {
        if (vigente) setRespuesta({ clave, slots: null });
      });
    return () => {
      vigente = false;
    };
  }, [api, clave, tratamientoId, profesionalId, dia]);

  async function enviar(evento: FormEvent<HTMLFormElement>): Promise<void> {
    evento.preventDefault();
    if (enviando || tratamientoId === null || profesionalId === null) return;
    const nuevos = {
      ...(validarNombre(nombre) ? { nombre: validarNombre(nombre) ?? '' } : {}),
      ...(validarTelefono(telefono) ? { telefono: validarTelefono(telefono) ?? '' } : {}),
      ...(elegido === null ? { general: 'Elegí un horario libre.' } : {}),
    };
    setErrores(nuevos);
    setConflicto(null);
    setRechazo(null);
    if (Object.keys(nuevos).length > 0 || elegido === null) return;
    setEnviando(true);
    let resultado;
    try {
      resultado = await api.crearTurno({
        profesionalId,
        tratamientoId,
        inicio: elegido.inicio,
        nombre: nombre.trim(),
        telefono: normalizarTelefono(telefono),
      });
    } catch (error) {
      if (error instanceof ErrorSesion) return; // la app vuelve sola al ingreso
      throw error;
    }
    setEnviando(false);
    if (resultado.ok) {
      setCreado(resultado.valor);
      onCreado();
      return;
    }
    if (resultado.error.tipo === 'conflicto') {
      setElegido(null);
      setConflicto(resultado.error.alternativas);
      return;
    }
    setRechazo(textoDeRechazo(resultado.error));
  }

  if (creado !== null) {
    return (
      <div className="velo">
        <section role="dialog" aria-modal="true" aria-labelledby={`${id}-titulo`} className="dialogo">
          <h2 id={`${id}-titulo`} ref={tituloRef} tabIndex={-1}>
            Turno creado
          </h2>
          <p>
            {etiquetaDiaLarga(creado.inicio.slice(0, 10))}, de {horaClinica(creado.inicio)} a {horaClinica(creado.fin)}.
          </p>
          <p className="nota">Código de gestión para compartir con la persona:</p>
          <p className="codigo">{creado.codigo_gestion}</p>
          <p className="aviso aviso-info">
            Este código se muestra una sola vez. Copialo y compartilo ahora: no se vuelve a ver en el panel.
          </p>
          <div className="acciones">
            <button
              type="button"
              className="boton boton-primario"
              onClick={() => {
                setCreado(null);
                onCerrar();
              }}
            >
              Listo
            </button>
          </div>
        </section>
      </div>
    );
  }

  const horariosDelDia = horarios.estado === 'listo' ? horarios.slots : [];

  return (
    <div className="velo">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-titulo`}
        className="dialogo dialogo-ancho"
        onKeyDown={(e) => {
          if (e.key === 'Escape' && !enviando) onCerrar();
        }}
      >
        <h2 id={`${id}-titulo`} ref={tituloRef} tabIndex={-1}>
          Nuevo turno
        </h2>
        <form onSubmit={(e) => void enviar(e)} noValidate>
          <div className="campo">
            <label htmlFor={`${id}-tratamiento`}>Tratamiento</label>
            <select
              id={`${id}-tratamiento`}
              value={tratamientoId ?? ''}
              onChange={(e) => {
                setTratamientoId(e.target.value === '' ? null : Number(e.target.value));
                setElegido(null);
              }}
            >
              <option value="">Elegí un tratamiento</option>
              {opciones.tratamientos.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="campo">
            <label htmlFor="alta-profesional">Profesional</label>
            <select
              id="alta-profesional"
              value={profesionalId ?? ''}
              onChange={(e) => {
                setProfesionalId(e.target.value === '' ? null : Number(e.target.value));
                setElegido(null);
              }}
            >
              <option value="">Elegí una profesional</option>
              {opciones.profesionales.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </select>
          </div>
          <div className="campo">
            <label htmlFor={`${id}-dia`}>Día</label>
            <input
              id={`${id}-dia`}
              type="date"
              value={dia}
              onChange={(e) => {
                setDia(e.target.value);
                setElegido(null);
              }}
            />
          </div>

          <fieldset className="grupo">
            <legend>Horario</legend>
            {horarios.estado === 'sin_elegir' && <p className="nota">Elegí tratamiento y profesional para ver los horarios libres.</p>}
            {horarios.estado === 'cargando' && (
              <p className="estado-carga" role="status">
                Buscando horarios…
              </p>
            )}
            {horarios.estado === 'error' && (
              <div className="aviso aviso-error" role="alert">
                <p>No pudimos consultar los horarios.</p>
                <button
                  type="button"
                  className="boton boton-secundario"
                  onClick={() => {
                    setReintento((n) => n + 1);
                  }}
                >
                  Reintentar
                </button>
              </div>
            )}
            {horarios.estado === 'listo' && horariosDelDia.length === 0 && (
              <p className="nota">No hay horarios libres ese día. Probá con otro día.</p>
            )}
            <div className="horarios">
              {horariosDelDia.map((slot) => (
                <button
                  key={slot.inicio}
                  type="button"
                  className={`horario${elegido?.inicio === slot.inicio ? ' seleccionado' : ''}`}
                  aria-pressed={elegido?.inicio === slot.inicio}
                  onClick={() => {
                    setElegido({ inicio: slot.inicio });
                    setConflicto(null);
                  }}
                >
                  {horaClinica(slot.inicio)}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="campo">
            <label htmlFor={`${id}-nombre`}>Nombre completo</label>
            <input
              id={`${id}-nombre`}
              type="text"
              autoComplete="off"
              value={nombre}
              aria-invalid={errores.nombre ? 'true' : undefined}
              aria-describedby={errores.nombre ? `${id}-nombre-error` : undefined}
              onChange={(e) => {
                setNombre(e.target.value);
              }}
            />
            {errores.nombre && (
              <p id={`${id}-nombre-error`} className="campo-error">
                {errores.nombre}
              </p>
            )}
          </div>
          <div className="campo">
            <label htmlFor={`${id}-telefono`}>Teléfono (WhatsApp)</label>
            <input
              id={`${id}-telefono`}
              type="tel"
              autoComplete="off"
              value={telefono}
              aria-invalid={errores.telefono ? 'true' : undefined}
              aria-describedby={errores.telefono ? `${id}-telefono-error` : undefined}
              onChange={(e) => {
                setTelefono(e.target.value);
              }}
            />
            {errores.telefono && (
              <p id={`${id}-telefono-error`} className="campo-error">
                {errores.telefono}
              </p>
            )}
          </div>

          {conflicto !== null && (
            <div className="aviso aviso-error" role="alert">
              <p>
                Ese horario ya no está disponible.{' '}
                {conflicto.length > 0 ? 'Elegí otro de estos, tus datos siguen cargados:' : 'No quedan horarios cercanos. Probá con otro día.'}
              </p>
              <div className="horarios">
                {conflicto.map((alt) => (
                  <button
                    key={alt.inicio}
                    type="button"
                    className="horario"
                    onClick={() => {
                      setElegido({ inicio: alt.inicio });
                      setConflicto(null);
                    }}
                  >
                    {horaClinica(alt.inicio)}
                  </button>
                ))}
              </div>
            </div>
          )}
          {errores.general && (
            <p className="aviso aviso-error" role="alert">
              {errores.general}
            </p>
          )}
          {rechazo !== null && (
            <p className="aviso aviso-error" role="alert">
              {rechazo}
            </p>
          )}

          <div className="acciones">
            <button type="button" className="boton boton-secundario" onClick={onCerrar} disabled={enviando}>
              Cancelar
            </button>
            <button type="submit" className="boton boton-primario" disabled={enviando}>
              {enviando ? 'Creando…' : 'Crear turno'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
