import { useState } from 'react';
import { formatoDuracion, formatoPrecio, mensajeDeCatalogo, validarTratamiento } from '../lib/catalogo';
import type { ErrorCatalogo, TratamientoAdmin } from '../lib/tipos';
import { CampoCatalogo } from './CampoCatalogo';
import { ConfirmarCambioCatalogo } from './ConfirmarCambioCatalogo';
import { FilaCatalogo } from './FilaCatalogo';
import { campoDeFormulario, MENSAJE_GUARDADO, reemplazarEn, sacarDe, type PropsPestanaCatalogo } from './pestanaCatalogo';
import { useAccionCatalogo } from './useAccionCatalogo';

type Modo = { readonly tipo: 'ninguno' } | { readonly tipo: 'nuevo' } | { readonly tipo: 'editar'; readonly id: number };
type Dialogo = { readonly tipo: 'desactivar' | 'borrar'; readonly item: TratamientoAdmin };

export function TratamientosCatalogo({ api, datos, cambiar, avisar }: PropsPestanaCatalogo) {
  const [modo, setModo] = useState<Modo>({ tipo: 'ninguno' });
  const [dialogo, setDialogo] = useState<Dialogo | null>(null);
  const { ejecutar } = useAccionCatalogo();

  const editando = modo.tipo === 'editar' ? (datos.tratamientos.find((t) => t.id === modo.id) ?? null) : null;

  function guardado(item: TratamientoAdmin): void {
    cambiar((d) => ({ ...d, tratamientos: reemplazarEn(d.tratamientos, item) }));
    avisar(MENSAJE_GUARDADO);
  }

  async function cambiarActivo(item: TratamientoAdmin, activo: boolean): Promise<boolean> {
    const r = await ejecutar(() => api.actualizarCatalogo('tratamientos', item.id, { activo }));
    if (r === null) return false;
    if (r.ok) {
      guardado(r.valor);
      return true;
    }
    avisar(mensajeDeCatalogo(r.error, 'tratamientos').mensaje);
    return false;
  }

  return (
    <div className="catalogo-pestana">
      {modo.tipo === 'ninguno' && (
        <button
          type="button"
          className="boton boton-primario"
          onClick={() => {
            setModo({ tipo: 'nuevo' });
          }}
        >
          Agregar tratamiento
        </button>
      )}
      {modo.tipo === 'nuevo' && (
        <FormularioTratamiento
          key="nuevo"
          api={api}
          inicial={null}
          alGuardar={(item) => {
            guardado(item);
            setModo({ tipo: 'ninguno' });
          }}
          alCancelar={() => {
            setModo({ tipo: 'ninguno' });
          }}
        />
      )}
      {editando !== null && (
        <FormularioTratamiento
          key={editando.id}
          api={api}
          inicial={editando}
          alGuardar={(item) => {
            guardado(item);
            setModo({ tipo: 'ninguno' });
          }}
          alCancelar={() => {
            setModo({ tipo: 'ninguno' });
          }}
        />
      )}
      {datos.tratamientos.length === 0 ? (
        <p className="vacio">Todavía no cargaste ningún tratamiento. Agregá el primero para que los pacientes puedan reservar.</p>
      ) : (
        <ul className="lista-catalogo">
          {datos.tratamientos.map((t) => (
            <FilaCatalogo
              key={t.id}
              titulo={t.nombre}
              detalle={
                <>
                  <span>{formatoDuracion(t.duracion_minutos)}</span> · <span>{formatoPrecio(t.precio_base)}</span>
                </>
              }
              estado={t.activo ? 'Activo' : 'Inactivo'}
              atenuada={!t.activo}
              notas={[...(t.activo ? [] : ['No se ofrece para reservar']), ...(Number(t.precio_base) === 0 ? ['Sin seña'] : [])]}
              acciones={
                <>
                  <button
                    type="button"
                    className="boton boton-secundario"
                    onClick={() => {
                      setModo({ tipo: 'editar', id: t.id });
                    }}
                  >
                    Editar
                  </button>
                  {t.activo ? (
                    <button
                      type="button"
                      className="boton boton-secundario"
                      onClick={() => {
                        setDialogo({ tipo: 'desactivar', item: t });
                      }}
                    >
                      Desactivar
                    </button>
                  ) : (
                    <button type="button" className="boton boton-secundario" onClick={() => void cambiarActivo(t, true)}>
                      Reactivar
                    </button>
                  )}
                  <button
                    type="button"
                    className="boton boton-secundario"
                    onClick={() => {
                      setDialogo({ tipo: 'borrar', item: t });
                    }}
                  >
                    Borrar
                  </button>
                </>
              }
            />
          ))}
        </ul>
      )}
      {dialogo?.tipo === 'desactivar' && (
        <ConfirmarCambioCatalogo
          api={api}
          recurso="tratamientos"
          id={dialogo.item.id}
          titulo="Desactivar tratamiento"
          donde="en este tratamiento"
          consecuencia="Dejará de ofrecerse para reservar. Podés reactivarlo cuando quieras."
          confirmar="Desactivar"
          alConfirmar={() => api.actualizarCatalogo('tratamientos', dialogo.item.id, { activo: false })}
          alHecho={() => {
            const id = dialogo.item.id;
            cambiar((d) => ({ ...d, tratamientos: d.tratamientos.map((x) => (x.id === id ? { ...x, activo: false } : x)) }));
            avisar(MENSAJE_GUARDADO);
            setDialogo(null);
          }}
          alVolver={() => {
            setDialogo(null);
          }}
        />
      )}
      {dialogo?.tipo === 'borrar' && (
        <ConfirmarCambioCatalogo
          api={api}
          recurso="tratamientos"
          id={dialogo.item.id}
          titulo="Borrar tratamiento"
          donde="en este tratamiento"
          consecuencia="Se borra para siempre. Si ya tiene turnos registrados no se puede borrar: en ese caso desactivalo."
          confirmar="Borrar tratamiento"
          alConfirmar={() => api.borrarCatalogo('tratamientos', dialogo.item.id)}
          alHecho={() => {
            const id = dialogo.item.id;
            cambiar((d) => ({ ...d, tratamientos: sacarDe(d.tratamientos, id) }));
            avisar('Borramos el tratamiento');
            setDialogo(null);
          }}
          alVolver={() => {
            setDialogo(null);
          }}
          alternativa={{
            etiqueta: 'Desactivar',
            alElegir: () => {
              const item = dialogo.item;
              void cambiarActivo(item, false).then((hecho) => {
                if (hecho) setDialogo(null);
              });
            },
          }}
        />
      )}
    </div>
  );
}

interface PropsFormulario {
  readonly api: PropsPestanaCatalogo['api'];
  readonly inicial: TratamientoAdmin | null;
  readonly alGuardar: (item: TratamientoAdmin) => void;
  readonly alCancelar: () => void;
}

function FormularioTratamiento({ api, inicial, alGuardar, alCancelar }: PropsFormulario) {
  const [nombre, setNombre] = useState(inicial?.nombre ?? '');
  const [duracion, setDuracion] = useState(inicial === null ? '' : String(inicial.duracion_minutos));
  const [precio, setPrecio] = useState(inicial === null ? '' : inicial.precio_base);
  const [errores, setErrores] = useState<Readonly<Record<string, string>>>({});
  const [rechazo, setRechazo] = useState<string | null>(null);
  const { enviando, ejecutar } = useAccionCatalogo();

  async function enviar(): Promise<void> {
    setRechazo(null);
    const validacion = validarTratamiento({ nombre, duracion, precio });
    setErrores(validacion.campos);
    if (validacion.valor === null) return;
    const valor = validacion.valor;
    const r = await ejecutar(() =>
      inicial === null ? api.crearCatalogo('tratamientos', valor) : api.actualizarCatalogo('tratamientos', inicial.id, valor),
    );
    if (r === null) return;
    if (r.ok) {
      alGuardar(r.valor);
      return;
    }
    mostrarError(r.error);
  }

  function mostrarError(error: ErrorCatalogo): void {
    const { campo, mensaje } = mensajeDeCatalogo(error, 'tratamientos');
    const formulario = campoDeFormulario(campo);
    if (formulario !== undefined) setErrores({ [formulario]: mensaje });
    else setRechazo(mensaje);
  }

  const precioCero = precio.trim() !== '' && Number(precio.replace(',', '.')) === 0;

  return (
    <form
      className="formulario-catalogo"
      aria-label={inicial === null ? 'Agregar tratamiento' : 'Editar tratamiento'}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <CampoCatalogo etiqueta="Nombre" valor={nombre} alCambiar={setNombre} error={errores['nombre']} />
      <CampoCatalogo
        etiqueta="Duración (minutos)"
        tipo="number"
        inputMode="numeric"
        paso={5}
        valor={duracion}
        alCambiar={setDuracion}
        error={errores['duracion']}
        ayuda="De 5 a 480 minutos, en múltiplos de 5."
      />
      <CampoCatalogo
        etiqueta="Precio (pesos)"
        inputMode="decimal"
        valor={precio}
        alCambiar={setPrecio}
        error={errores['precio']}
        ayuda="La seña se calcula sobre este precio."
      />
      {precioCero && <p className="aviso aviso-info">Los turnos de este tratamiento no pedirán seña.</p>}
      {inicial !== null && (
        <p className="aviso aviso-info">
          La duración y el precio nuevos valen solo para los turnos que se tomen desde ahora. Los turnos ya tomados no cambian.
        </p>
      )}
      {rechazo !== null && (
        <p className="aviso aviso-error" role="alert">
          {rechazo}
        </p>
      )}
      <div className="acciones">
        <button type="button" className="boton boton-secundario" onClick={alCancelar} disabled={enviando}>
          Cancelar
        </button>
        <button type="submit" className="boton boton-primario" disabled={enviando}>
          {enviando ? 'Guardando…' : inicial === null ? 'Guardar tratamiento' : 'Guardar cambios'}
        </button>
      </div>
    </form>
  );
}
