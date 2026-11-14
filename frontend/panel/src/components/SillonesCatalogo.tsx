import { useState } from 'react';
import { mensajeDeCatalogo, validarSillon } from '../lib/catalogo';
import type { DatosSillon, EstadoSillon, SillonAdmin } from '../lib/tipos';
import { CampoCatalogo, SelectorCatalogo } from './CampoCatalogo';
import { ConfirmarCambioCatalogo } from './ConfirmarCambioCatalogo';
import { FilaCatalogo } from './FilaCatalogo';
import { campoDeFormulario, MENSAJE_GUARDADO, reemplazarEn, sacarDe, type PropsPestanaCatalogo } from './pestanaCatalogo';
import { useAccionCatalogo } from './useAccionCatalogo';

const ETIQUETA_ESTADO: Readonly<Record<EstadoSillon, string>> = {
  activo: 'Disponible',
  mantenimiento: 'En mantenimiento',
  inactivo: 'Fuera de uso',
};

const ESTADOS: readonly EstadoSillon[] = ['activo', 'mantenimiento', 'inactivo'];

type Modo = { readonly tipo: 'ninguno' } | { readonly tipo: 'nuevo' } | { readonly tipo: 'editar'; readonly id: number };
type Dialogo =
  | { readonly tipo: 'borrar'; readonly item: SillonAdmin }
  | { readonly tipo: 'estado'; readonly item: SillonAdmin; readonly cambios: DatosSillon };

export function SillonesCatalogo({ api, datos, cambiar, avisar }: PropsPestanaCatalogo) {
  const [modo, setModo] = useState<Modo>({ tipo: 'ninguno' });
  const [dialogo, setDialogo] = useState<Dialogo | null>(null);
  const { ejecutar } = useAccionCatalogo();

  const editando = modo.tipo === 'editar' ? (datos.sillones.find((s) => s.id === modo.id) ?? null) : null;

  function guardado(item: SillonAdmin): void {
    cambiar((d) => ({ ...d, sillones: reemplazarEn(d.sillones, item) }));
    avisar(MENSAJE_GUARDADO);
  }

  async function ponerEstado(item: SillonAdmin): Promise<boolean> {
    const r = await ejecutar(() => api.actualizarCatalogo('sillones', item.id, { estado: 'inactivo' }));
    if (r === null) return false;
    if (r.ok) {
      guardado(r.valor);
      return true;
    }
    avisar(mensajeDeCatalogo(r.error, 'sillones').mensaje);
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
          Agregar sillón
        </button>
      )}
      {modo.tipo !== 'ninguno' && (modo.tipo === 'nuevo' || editando !== null) && (
        <FormularioSillon
          key={editando?.id ?? 'nuevo'}
          api={api}
          inicial={editando}
          alGuardar={(item) => {
            guardado(item);
            setModo({ tipo: 'ninguno' });
          }}
          alConfirmarEstado={(item, cambios) => {
            setDialogo({ tipo: 'estado', item, cambios });
          }}
          alCancelar={() => {
            setModo({ tipo: 'ninguno' });
          }}
        />
      )}
      {datos.sillones.length === 0 ? (
        <p className="vacio">Todavía no cargaste ningún sillón. Agregá el primero para poder ofrecer turnos.</p>
      ) : (
        <ul className="lista-catalogo">
          {datos.sillones.map((s) => (
            <FilaCatalogo
              key={s.id}
              titulo={s.nombre}
              estado={ETIQUETA_ESTADO[s.estado]}
              atenuada={s.estado !== 'activo'}
              notas={s.estado === 'activo' ? [] : ['No se ofrece para reservar']}
              acciones={
                <>
                  <button
                    type="button"
                    className="boton boton-secundario"
                    onClick={() => {
                      setModo({ tipo: 'editar', id: s.id });
                    }}
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    className="boton boton-secundario"
                    onClick={() => {
                      setDialogo({ tipo: 'borrar', item: s });
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
      {dialogo?.tipo === 'estado' && (
        <ConfirmarCambioCatalogo
          api={api}
          recurso="sillones"
          id={dialogo.item.id}
          titulo="Cambiar el estado del sillón"
          donde="en este sillón"
          consecuencia="Dejará de ofrecerse para turnos nuevos. Podés volver a ponerlo como disponible cuando quieras."
          confirmar="Confirmar cambio"
          alConfirmar={() => api.actualizarCatalogo('sillones', dialogo.item.id, dialogo.cambios)}
          alHecho={() => {
            const { item, cambios } = dialogo;
            guardado({ ...item, ...cambios });
            setModo({ tipo: 'ninguno' });
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
          recurso="sillones"
          id={dialogo.item.id}
          titulo="Borrar sillón"
          donde="en este sillón"
          consecuencia="Se borra para siempre. Si ya tiene turnos registrados no se puede borrar: en ese caso ponelo fuera de uso."
          confirmar="Borrar sillón"
          alConfirmar={() => api.borrarCatalogo('sillones', dialogo.item.id)}
          alHecho={() => {
            const id = dialogo.item.id;
            cambiar((d) => ({ ...d, sillones: sacarDe(d.sillones, id) }));
            avisar('Borramos el sillón');
            setDialogo(null);
          }}
          alVolver={() => {
            setDialogo(null);
          }}
          alternativa={{
            etiqueta: 'Poner fuera de uso',
            alElegir: () => {
              void ponerEstado(dialogo.item).then((hecho) => {
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
  readonly inicial: SillonAdmin | null;
  readonly alGuardar: (item: SillonAdmin) => void;
  /** Sacar un sillón de servicio pasa por la confirmación con el impacto en los turnos tomados. */
  readonly alConfirmarEstado: (item: SillonAdmin, cambios: DatosSillon) => void;
  readonly alCancelar: () => void;
}

function FormularioSillon({ api, inicial, alGuardar, alConfirmarEstado, alCancelar }: PropsFormulario) {
  const [nombre, setNombre] = useState(inicial?.nombre ?? '');
  const [estado, setEstado] = useState<EstadoSillon>(inicial?.estado ?? 'activo');
  const [errores, setErrores] = useState<Readonly<Record<string, string>>>({});
  const [rechazo, setRechazo] = useState<string | null>(null);
  const { enviando, ejecutar } = useAccionCatalogo();

  async function enviar(): Promise<void> {
    setRechazo(null);
    const validacion = validarSillon({ nombre, estado });
    setErrores(validacion.campos);
    if (validacion.valor === null) return;
    const valor = validacion.valor;
    if (inicial !== null && inicial.estado === 'activo' && valor.estado !== 'activo') {
      alConfirmarEstado(inicial, valor);
      return;
    }
    const r = await ejecutar(() =>
      inicial === null ? api.crearCatalogo('sillones', valor) : api.actualizarCatalogo('sillones', inicial.id, valor),
    );
    if (r === null) return;
    if (r.ok) {
      alGuardar(r.valor);
      return;
    }
    const { campo, mensaje } = mensajeDeCatalogo(r.error, 'sillones');
    const formulario = campoDeFormulario(campo);
    if (formulario !== undefined) setErrores({ [formulario]: mensaje });
    else setRechazo(mensaje);
  }

  return (
    <form
      className="formulario-catalogo"
      aria-label={inicial === null ? 'Agregar sillón' : 'Editar sillón'}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <CampoCatalogo etiqueta="Nombre" valor={nombre} alCambiar={setNombre} error={errores['nombre']} />
      <SelectorCatalogo
        etiqueta="Estado"
        valor={estado}
        alCambiar={(v) => {
          setEstado(ESTADOS.find((e) => e === v) ?? 'activo');
        }}
      >
        {ESTADOS.map((e) => (
          <option key={e} value={e}>
            {ETIQUETA_ESTADO[e]}
          </option>
        ))}
      </SelectorCatalogo>
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
          {enviando ? 'Guardando…' : inicial === null ? 'Guardar sillón' : 'Guardar cambios'}
        </button>
      </div>
    </form>
  );
}
