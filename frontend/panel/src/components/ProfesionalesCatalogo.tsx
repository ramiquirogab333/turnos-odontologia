import { useState } from 'react';
import { mensajeDeCatalogo, validarProfesional } from '../lib/catalogo';
import type { ProfesionalAdmin } from '../lib/tipos';
import { CampoCatalogo } from './CampoCatalogo';
import { ConfirmarCambioCatalogo } from './ConfirmarCambioCatalogo';
import { FilaCatalogo } from './FilaCatalogo';
import { campoDeFormulario, MENSAJE_GUARDADO, reemplazarEn, sacarDe, type PropsPestanaCatalogo } from './pestanaCatalogo';
import { useAccionCatalogo } from './useAccionCatalogo';

type Modo = { readonly tipo: 'ninguno' } | { readonly tipo: 'nuevo' } | { readonly tipo: 'editar'; readonly id: number };
type Dialogo = { readonly tipo: 'desactivar' | 'borrar'; readonly item: ProfesionalAdmin };

export function ProfesionalesCatalogo({ api, datos, cambiar, avisar }: PropsPestanaCatalogo) {
  const [modo, setModo] = useState<Modo>({ tipo: 'ninguno' });
  const [dialogo, setDialogo] = useState<Dialogo | null>(null);
  const { ejecutar } = useAccionCatalogo();

  const editando = modo.tipo === 'editar' ? (datos.profesionales.find((p) => p.id === modo.id) ?? null) : null;

  function guardado(item: ProfesionalAdmin): void {
    cambiar((d) => ({ ...d, profesionales: reemplazarEn(d.profesionales, item) }));
    avisar(MENSAJE_GUARDADO);
  }

  async function cambiarActivo(item: ProfesionalAdmin, activo: boolean): Promise<boolean> {
    const r = await ejecutar(() => api.actualizarCatalogo('profesionales', item.id, { activo }));
    if (r === null) return false;
    if (r.ok) {
      guardado(r.valor);
      return true;
    }
    avisar(mensajeDeCatalogo(r.error, 'profesionales').mensaje);
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
          Agregar profesional
        </button>
      )}
      {modo.tipo !== 'ninguno' && (modo.tipo === 'nuevo' || editando !== null) && (
        <FormularioProfesional
          key={editando?.id ?? 'nuevo'}
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
      {datos.profesionales.length === 0 ? (
        <p className="vacio">Todavía no cargaste ninguna profesional. Agregá la primera para poder cargar sus horarios.</p>
      ) : (
        <ul className="lista-catalogo">
          {datos.profesionales.map((p) => (
            <FilaCatalogo
              key={p.id}
              titulo={p.nombre}
              detalle={
                <>
                  <span>{p.especialidad === '' ? 'Sin especialidad' : p.especialidad}</span> · <span>{`Matrícula ${p.matricula}`}</span>
                </>
              }
              estado={p.activo ? 'Activo' : 'Inactivo'}
              atenuada={!p.activo}
              notas={p.activo ? [] : ['No se ofrece para reservar']}
              acciones={
                <>
                  <button
                    type="button"
                    className="boton boton-secundario"
                    onClick={() => {
                      setModo({ tipo: 'editar', id: p.id });
                    }}
                  >
                    Editar
                  </button>
                  {p.activo ? (
                    <button
                      type="button"
                      className="boton boton-secundario"
                      onClick={() => {
                        setDialogo({ tipo: 'desactivar', item: p });
                      }}
                    >
                      Desactivar
                    </button>
                  ) : (
                    <button type="button" className="boton boton-secundario" onClick={() => void cambiarActivo(p, true)}>
                      Reactivar
                    </button>
                  )}
                  <button
                    type="button"
                    className="boton boton-secundario"
                    onClick={() => {
                      setDialogo({ tipo: 'borrar', item: p });
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
          recurso="profesionales"
          id={dialogo.item.id}
          titulo="Desactivar profesional"
          donde="con esta profesional"
          consecuencia="Dejará de ofrecerse para reservar. Podés reactivarla cuando quieras."
          confirmar="Desactivar"
          alConfirmar={() => api.actualizarCatalogo('profesionales', dialogo.item.id, { activo: false })}
          alHecho={() => {
            const id = dialogo.item.id;
            cambiar((d) => ({ ...d, profesionales: d.profesionales.map((x) => (x.id === id ? { ...x, activo: false } : x)) }));
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
          recurso="profesionales"
          id={dialogo.item.id}
          titulo="Borrar profesional"
          donde="con esta profesional"
          consecuencia="Se borra para siempre, junto con sus horarios. Si ya tiene turnos registrados no se puede borrar: en ese caso desactivala."
          confirmar="Borrar profesional"
          alConfirmar={() => api.borrarCatalogo('profesionales', dialogo.item.id)}
          alHecho={() => {
            const id = dialogo.item.id;
            cambiar((d) => ({
              ...d,
              profesionales: sacarDe(d.profesionales, id),
              franjas: d.franjas.filter((f) => f.profesional_id !== id),
            }));
            avisar('Borramos la profesional');
            setDialogo(null);
          }}
          alVolver={() => {
            setDialogo(null);
          }}
          alternativa={{
            etiqueta: 'Desactivar',
            alElegir: () => {
              void cambiarActivo(dialogo.item, false).then((hecho) => {
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
  readonly inicial: ProfesionalAdmin | null;
  readonly alGuardar: (item: ProfesionalAdmin) => void;
  readonly alCancelar: () => void;
}

function FormularioProfesional({ api, inicial, alGuardar, alCancelar }: PropsFormulario) {
  const [nombre, setNombre] = useState(inicial?.nombre ?? '');
  const [matricula, setMatricula] = useState(inicial?.matricula ?? '');
  const [especialidad, setEspecialidad] = useState(inicial?.especialidad ?? '');
  const [errores, setErrores] = useState<Readonly<Record<string, string>>>({});
  const [rechazo, setRechazo] = useState<string | null>(null);
  const { enviando, ejecutar } = useAccionCatalogo();

  async function enviar(): Promise<void> {
    setRechazo(null);
    const validacion = validarProfesional({ nombre, matricula, especialidad });
    setErrores(validacion.campos);
    if (validacion.valor === null) return;
    const valor = validacion.valor;
    const r = await ejecutar(() =>
      inicial === null ? api.crearCatalogo('profesionales', valor) : api.actualizarCatalogo('profesionales', inicial.id, valor),
    );
    if (r === null) return;
    if (r.ok) {
      alGuardar(r.valor);
      return;
    }
    const { campo, mensaje } = mensajeDeCatalogo(r.error, 'profesionales');
    const formulario = campoDeFormulario(campo);
    if (formulario !== undefined) setErrores({ [formulario]: mensaje });
    else setRechazo(mensaje);
  }

  return (
    <form
      className="formulario-catalogo"
      aria-label={inicial === null ? 'Agregar profesional' : 'Editar profesional'}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <CampoCatalogo etiqueta="Nombre" valor={nombre} alCambiar={setNombre} error={errores['nombre']} />
      <CampoCatalogo etiqueta="Matrícula" valor={matricula} alCambiar={setMatricula} error={errores['matricula']} />
      <CampoCatalogo
        etiqueta="Especialidad"
        valor={especialidad}
        alCambiar={setEspecialidad}
        error={errores['especialidad']}
        ayuda="Opcional."
      />
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
          {enviando ? 'Guardando…' : inicial === null ? 'Guardar profesional' : 'Guardar cambios'}
        </button>
      </div>
    </form>
  );
}
