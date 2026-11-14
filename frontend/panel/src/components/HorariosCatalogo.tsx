import { useId, useState } from 'react';
import { agruparPorDia, horaCorta, mensajeDeCatalogo, validarFranja, type DiaDeFranjas } from '../lib/catalogo';
import type { FranjaAdmin, SillonAdmin } from '../lib/tipos';
import { CampoCatalogo, SelectorCatalogo } from './CampoCatalogo';
import { ConfirmarCambioCatalogo } from './ConfirmarCambioCatalogo';
import { FilaCatalogo } from './FilaCatalogo';
import { campoDeFormulario, MENSAJE_GUARDADO, reemplazarEn, sacarDe, type PropsPestanaCatalogo } from './pestanaCatalogo';
import { useAccionCatalogo } from './useAccionCatalogo';

const SIN_RESERVA_NUEVA = 'Los pacientes nuevos ya no podrán reservar en ese horario.';

type Modo = { readonly tipo: 'ninguno' } | { readonly tipo: 'nueva'; readonly dia: number } | { readonly tipo: 'editar'; readonly id: number };

interface CambiosHorario {
  readonly dia_semana: number;
  readonly hora_inicio: string;
  readonly hora_fin: string;
  readonly sillon_defecto_id: number | null;
}

type Dialogo =
  | { readonly tipo: 'pausar' | 'quitar'; readonly item: FranjaAdmin }
  | { readonly tipo: 'horario'; readonly item: FranjaAdmin; readonly cambios: CambiosHorario };

/** Editor de horarios: la profesional elegida y un bloque por día. Las horas son las de la clínica, sin convertir. */
export function HorariosCatalogo({ api, datos, cambiar, avisar }: PropsPestanaCatalogo) {
  const [elegida, setElegida] = useState<number | null>(null);
  const [modo, setModo] = useState<Modo>({ tipo: 'ninguno' });
  const [dialogo, setDialogo] = useState<Dialogo | null>(null);
  const { ejecutar } = useAccionCatalogo();

  if (datos.profesionales.length === 0) {
    return <p className="vacio">Primero cargá una profesional en la pestaña Profesionales para poder definir sus horarios.</p>;
  }

  const profesionalId = elegida !== null && datos.profesionales.some((p) => p.id === elegida) ? elegida : (datos.profesionales[0]?.id ?? 0);
  const dias = agruparPorDia(datos.franjas.filter((f) => f.profesional_id === profesionalId));
  const sillones = new Map(datos.sillones.map((s) => [s.id, s.nombre]));

  function guardada(item: FranjaAdmin): void {
    cambiar((d) => ({ ...d, franjas: reemplazarEn(d.franjas, item) }));
    avisar(MENSAJE_GUARDADO);
  }

  async function reactivar(item: FranjaAdmin): Promise<void> {
    const r = await ejecutar(() => api.actualizarCatalogo('disponibilidad', item.id, { activo: true }));
    if (r === null) return;
    if (r.ok) guardada(r.valor);
    else avisar(mensajeDeCatalogo(r.error, 'disponibilidad').mensaje);
  }

  return (
    <div className="catalogo-pestana">
      <SelectorCatalogo
        etiqueta="Profesional"
        valor={String(profesionalId)}
        alCambiar={(v) => {
          setElegida(Number(v));
          setModo({ tipo: 'ninguno' });
        }}
      >
        {datos.profesionales.map((p) => (
          <option key={p.id} value={p.id}>
            {p.activo ? p.nombre : `${p.nombre} (inactivo)`}
          </option>
        ))}
      </SelectorCatalogo>
      <div className="dias-atencion">
        {dias.map((d) => (
          <DiaDeAtencion
            key={d.dia}
            dia={d}
            sillones={datos.sillones}
            nombresSillon={sillones}
            profesionalId={profesionalId}
            api={api}
            modo={modo}
            setModo={setModo}
            alGuardar={(item) => {
              guardada(item);
              setModo({ tipo: 'ninguno' });
            }}
            alPedirConfirmacion={(item, cambios) => {
              setDialogo({ tipo: 'horario', item, cambios });
            }}
            alPausar={(item) => {
              setDialogo({ tipo: 'pausar', item });
            }}
            alQuitar={(item) => {
              setDialogo({ tipo: 'quitar', item });
            }}
            alReactivar={(item) => void reactivar(item)}
          />
        ))}
      </div>
      {dialogo?.tipo === 'pausar' && (
        <ConfirmarCambioCatalogo
          api={api}
          recurso="disponibilidad"
          id={dialogo.item.id}
          titulo="Pausar franja"
          donde="en esta franja"
          consecuencia={`${SIN_RESERVA_NUEVA} Podés reactivarla cuando quieras.`}
          confirmar="Pausar franja"
          alConfirmar={() => api.actualizarCatalogo('disponibilidad', dialogo.item.id, { activo: false })}
          alHecho={() => {
            const id = dialogo.item.id;
            cambiar((d) => ({ ...d, franjas: d.franjas.map((f) => (f.id === id ? { ...f, activo: false } : f)) }));
            avisar(MENSAJE_GUARDADO);
            setDialogo(null);
          }}
          alVolver={() => {
            setDialogo(null);
          }}
        />
      )}
      {dialogo?.tipo === 'quitar' && (
        <ConfirmarCambioCatalogo
          api={api}
          recurso="disponibilidad"
          id={dialogo.item.id}
          titulo="Quitar franja"
          donde="en esta franja"
          consecuencia={SIN_RESERVA_NUEVA}
          confirmar="Quitar franja"
          alConfirmar={() => api.borrarCatalogo('disponibilidad', dialogo.item.id)}
          alHecho={() => {
            const id = dialogo.item.id;
            cambiar((d) => ({ ...d, franjas: sacarDe(d.franjas, id) }));
            avisar('Quitamos la franja');
            setDialogo(null);
          }}
          alVolver={() => {
            setDialogo(null);
          }}
        />
      )}
      {dialogo?.tipo === 'horario' && (
        <ConfirmarCambioCatalogo
          api={api}
          recurso="disponibilidad"
          id={dialogo.item.id}
          titulo="Cambiar el horario de la franja"
          donde="en esta franja"
          consecuencia="Los pacientes nuevos reservarán según el horario nuevo."
          confirmar="Confirmar cambio"
          alConfirmar={() => api.actualizarCatalogo('disponibilidad', dialogo.item.id, dialogo.cambios)}
          alHecho={() => {
            const { item, cambios } = dialogo;
            guardada({ ...item, ...cambios });
            setModo({ tipo: 'ninguno' });
            setDialogo(null);
          }}
          alVolver={() => {
            setDialogo(null);
          }}
        />
      )}
    </div>
  );
}

interface PropsDia {
  readonly dia: DiaDeFranjas;
  readonly sillones: readonly SillonAdmin[];
  readonly nombresSillon: ReadonlyMap<number, string>;
  readonly profesionalId: number;
  readonly api: PropsPestanaCatalogo['api'];
  readonly modo: Modo;
  readonly setModo: (modo: Modo) => void;
  readonly alGuardar: (item: FranjaAdmin) => void;
  readonly alPedirConfirmacion: (item: FranjaAdmin, cambios: CambiosHorario) => void;
  readonly alPausar: (item: FranjaAdmin) => void;
  readonly alQuitar: (item: FranjaAdmin) => void;
  readonly alReactivar: (item: FranjaAdmin) => void;
}

function DiaDeAtencion({
  dia,
  sillones,
  nombresSillon,
  profesionalId,
  api,
  modo,
  setModo,
  alGuardar,
  alPedirConfirmacion,
  alPausar,
  alQuitar,
  alReactivar,
}: PropsDia) {
  const idTitulo = useId();
  const agregando = modo.tipo === 'nueva' && modo.dia === dia.dia;
  const editando = modo.tipo === 'editar' ? (dia.franjas.find((f) => f.id === modo.id) ?? null) : null;
  const cerrar = (): void => {
    setModo({ tipo: 'ninguno' });
  };

  return (
    <section className="dia-atencion" aria-labelledby={idTitulo}>
      <h3 id={idTitulo}>{dia.nombre}</h3>
      {dia.franjas.length === 0 ? (
        <p className="nota">Sin atención este día</p>
      ) : (
        <ul className="lista-catalogo">
          {dia.franjas.map((f) => {
            const sillon = f.sillon_defecto_id === null ? undefined : nombresSillon.get(f.sillon_defecto_id);
            return (
              <FilaCatalogo
                key={f.id}
                titulo={`${horaCorta(f.hora_inicio)} a ${horaCorta(f.hora_fin)}`}
                {...(sillon === undefined ? {} : { detalle: <span>{sillon}</span> })}
                estado={f.activo ? 'Activa' : 'Pausada'}
                atenuada={!f.activo}
                acciones={
                  <>
                    <button
                      type="button"
                      className="boton boton-secundario"
                      onClick={() => {
                        setModo({ tipo: 'editar', id: f.id });
                      }}
                    >
                      Editar
                    </button>
                    {f.activo ? (
                      <button
                        type="button"
                        className="boton boton-secundario"
                        onClick={() => {
                          alPausar(f);
                        }}
                      >
                        Pausar franja
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="boton boton-secundario"
                        onClick={() => {
                          alReactivar(f);
                        }}
                      >
                        Reactivar franja
                      </button>
                    )}
                    <button
                      type="button"
                      className="boton boton-secundario"
                      onClick={() => {
                        alQuitar(f);
                      }}
                    >
                      Quitar franja
                    </button>
                  </>
                }
              />
            );
          })}
        </ul>
      )}
      {agregando && (
        <FormularioFranja
          key="nueva"
          api={api}
          sillones={sillones}
          profesionalId={profesionalId}
          dia={dia.dia}
          inicial={null}
          alGuardar={alGuardar}
          alPedirConfirmacion={alPedirConfirmacion}
          alCancelar={cerrar}
        />
      )}
      {editando !== null && (
        <FormularioFranja
          key={editando.id}
          api={api}
          sillones={sillones}
          profesionalId={profesionalId}
          dia={dia.dia}
          inicial={editando}
          alGuardar={alGuardar}
          alPedirConfirmacion={alPedirConfirmacion}
          alCancelar={cerrar}
        />
      )}
      {!agregando && editando === null && (
        <button
          type="button"
          className="boton boton-secundario"
          onClick={() => {
            setModo({ tipo: 'nueva', dia: dia.dia });
          }}
        >
          Agregar franja
        </button>
      )}
    </section>
  );
}

interface PropsFormulario {
  readonly api: PropsPestanaCatalogo['api'];
  readonly sillones: readonly SillonAdmin[];
  readonly profesionalId: number;
  readonly dia: number;
  readonly inicial: FranjaAdmin | null;
  readonly alGuardar: (item: FranjaAdmin) => void;
  readonly alPedirConfirmacion: (item: FranjaAdmin, cambios: CambiosHorario) => void;
  readonly alCancelar: () => void;
}

function FormularioFranja({ api, sillones, profesionalId, dia, inicial, alGuardar, alPedirConfirmacion, alCancelar }: PropsFormulario) {
  const [inicio, setInicio] = useState(inicial === null ? '' : horaCorta(inicial.hora_inicio));
  const [fin, setFin] = useState(inicial === null ? '' : horaCorta(inicial.hora_fin));
  const [sillon, setSillon] = useState(inicial?.sillon_defecto_id === null || inicial === null ? '' : String(inicial.sillon_defecto_id));
  const [errores, setErrores] = useState<Readonly<Record<string, string>>>({});
  const [rechazo, setRechazo] = useState<string | null>(null);
  const { enviando, ejecutar } = useAccionCatalogo();

  async function enviar(): Promise<void> {
    setRechazo(null);
    const validacion = validarFranja({ inicio, fin });
    setErrores(validacion.campos);
    if (validacion.valor === null) return;
    const sillonId = sillon === '' ? null : Number(sillon);
    if (inicial === null) {
      const r = await ejecutar(() =>
        api.crearCatalogo('disponibilidad', {
          profesional_id: profesionalId,
          dia_semana: dia,
          hora_inicio: inicio,
          hora_fin: fin,
          sillon_defecto_id: sillonId,
        }),
      );
      if (r === null) return;
      if (r.ok) alGuardar(r.valor);
      else mostrarRechazo(r.error);
      return;
    }
    const cambios: CambiosHorario = { dia_semana: inicial.dia_semana, hora_inicio: inicio, hora_fin: fin, sillon_defecto_id: sillonId };
    // Mover el horario puede dejar turnos tomados fuera de la franja: se confirma con el impacto. Cambiar solo el sillón, no.
    if (horaCorta(inicial.hora_inicio) !== inicio || horaCorta(inicial.hora_fin) !== fin) {
      alPedirConfirmacion(inicial, cambios);
      return;
    }
    const r = await ejecutar(() => api.actualizarCatalogo('disponibilidad', inicial.id, cambios));
    if (r === null) return;
    if (r.ok) alGuardar(r.valor);
    else mostrarRechazo(r.error);
  }

  function mostrarRechazo(error: Parameters<typeof mensajeDeCatalogo>[0]): void {
    const { campo, mensaje } = mensajeDeCatalogo(error, 'disponibilidad');
    const formulario = campoDeFormulario(campo);
    if (formulario !== undefined) setErrores({ [formulario]: mensaje });
    else setRechazo(mensaje);
  }

  return (
    <form
      className="formulario-catalogo"
      aria-label={inicial === null ? 'Agregar franja' : 'Editar franja'}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <CampoCatalogo etiqueta="Desde" tipo="time" paso={300} valor={inicio} alCambiar={setInicio} error={errores['inicio']} />
      <CampoCatalogo etiqueta="Hasta" tipo="time" paso={300} valor={fin} alCambiar={setFin} error={errores['fin']} />
      <SelectorCatalogo etiqueta="Sillón preferido" valor={sillon} alCambiar={setSillon}>
        <option value="">Sin sillón preferido</option>
        {sillones.map((s) => (
          <option key={s.id} value={s.id}>
            {s.nombre}
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
          {enviando ? 'Guardando…' : inicial === null ? 'Guardar franja' : 'Guardar cambios'}
        </button>
      </div>
    </form>
  );
}
