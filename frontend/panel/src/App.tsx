import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Agenda } from './components/Agenda';
import { Caja } from './components/Caja';
import { GoogleCalendar } from './components/GoogleCalendar';
import { Cargando } from './components/Cargando';
import { Datos } from './components/Datos';
import { ErrorCarga } from './components/ErrorCarga';
import { Indicadores } from './components/Indicadores';
import { Ingreso } from './components/Ingreso';
import { Navegacion } from './components/Navegacion';
import { Pacientes } from './components/Pacientes';
import { Recordatorios } from './components/Recordatorios';
import type { Api } from './lib/api';
import { leerSeccion, pestanaDeDatos, resultadoDeGoogle, SECCIONES, SECCIONES_ODONTOLOGA, TITULO_SECCION, type Seccion } from './lib/ruta';
import { ErrorSesion, type MotivoCierre, type Sesion } from './lib/sesion';
import type { Usuario } from './lib/tipos';

interface Props {
  readonly sesion: Sesion;
  readonly api: Api;
  /** "Hoy" en la clínica, "YYYY-MM-DD". */
  readonly hoy: () => string;
}

type Fase =
  | { readonly nombre: 'restaurando' }
  | { readonly nombre: 'error_apertura' }
  | { readonly nombre: 'ingreso'; readonly aviso: MotivoCierre | null }
  | { readonly nombre: 'sin_acceso'; readonly usuario: Usuario }
  | { readonly nombre: 'panel'; readonly usuario: Usuario };

const ROLES_DEL_PANEL = ['admin', 'odontologo', 'recepcion'] as const;

function tieneAcceso(usuario: Usuario): boolean {
  return usuario.roles.some((rol) => ROLES_DEL_PANEL.includes(rol));
}

/** Pacientes, indicadores y caja son de recepción y admin; la odontóloga solo ve la agenda. */
function puedeVerSecciones(usuario: Usuario): boolean {
  return usuario.roles.includes('recepcion') || usuario.roles.includes('admin');
}

function suscribirHash(avisar: () => void): () => void {
  window.addEventListener('hashchange', avisar);
  return () => {
    window.removeEventListener('hashchange', avisar);
  };
}

const hashActual = (): string => window.location.hash;

interface PropsPanel {
  readonly usuario: Usuario;
  readonly api: Api;
  readonly hoy: string;
}

/** La sección sale del hash; sin permiso, un hash de otra sección se ignora y queda la agenda. */
function Secciones({ usuario, api, hoy }: PropsPanel) {
  const ve = puedeVerSecciones(usuario);
  const hash = useSyncExternalStore(suscribirHash, hashActual);
  const permitidas: readonly Seccion[] = ve ? SECCIONES : SECCIONES_ODONTOLOGA;
  const leida = leerSeccion(hash);
  const seccion: Seccion = permitidas.includes(leida) ? leida : 'agenda';

  return (
    <>
      <h1 className="titulo-seccion">{TITULO_SECCION[seccion]}</h1>
      <Navegacion actual={seccion} secciones={permitidas} />
      <main>
        {seccion === 'agenda' && <Agenda api={api} hoy={hoy} />}
        {seccion === 'pacientes' && <Pacientes api={api} />}
        {seccion === 'indicadores' && <Indicadores api={api} hoy={hoy} />}
        {seccion === 'recordatorios' && <Recordatorios api={api} />}
        {seccion === 'caja' && <Caja api={api} hoy={hoy} esAdmin={usuario.roles.includes('admin')} />}
        {seccion === 'datos' && (
          // Se remonta si el hash cambia de pestaña (un enlace directo `#/datos?pestana=auditoria` en la misma página).
          <Datos key={pestanaDeDatos(hash)} api={api} roles={usuario.roles} hoy={hoy} pestanaInicial={pestanaDeDatos(hash)} />
        )}
        {seccion === 'google-calendar' && (
          <GoogleCalendar
            api={api}
            puedeResolver={ve}
            esAdmin={usuario.roles.includes('admin')}
            esOdontologa={usuario.roles.includes('odontologo')}
            resultado={resultadoDeGoogle(hash)}
          />
        )}
      </main>
    </>
  );
}

export function App({ sesion, api, hoy }: Props) {
  const [fase, setFase] = useState<Fase>({ nombre: 'restaurando' });
  const [errorAlSalir, setErrorAlSalir] = useState<string | null>(null);
  const saliendo = useRef(false);

  const aplicar = useCallback((siguiente: Fase | null): void => {
    // `null`: la sesión terminó mientras tanto y el oyente de la sesión ya llevó a la pantalla de ingreso.
    if (siguiente !== null) setFase(siguiente);
  }, []);

  /** Quién es la persona y si puede usar el panel. */
  const faseDelUsuario = useCallback(async (): Promise<Fase | null> => {
    try {
      const usuario = await api.me();
      return tieneAcceso(usuario) ? { nombre: 'panel', usuario } : { nombre: 'sin_acceso', usuario };
    } catch (error) {
      return error instanceof ErrorSesion ? null : { nombre: 'error_apertura' };
    }
  }, [api]);

  // Al abrir: renovar con la cookie → quién es. Es secuencial porque `me` depende del access que devuelve el refresh.
  const abrir = useCallback(async (): Promise<Fase | null> => {
    try {
      const token = await sesion.renovar();
      if (token === null) return { nombre: 'ingreso', aviso: null };
    } catch {
      return { nombre: 'error_apertura' };
    }
    return faseDelUsuario();
  }, [sesion, faseDelUsuario]);

  useEffect(() => {
    void abrir().then(aplicar); // la fase inicial ya es "restaurando"
  }, [abrir, aplicar]);

  const reabrir = useCallback((): void => {
    setFase({ nombre: 'restaurando' });
    void abrir().then(aplicar);
  }, [abrir, aplicar]);

  // Si la sesión termina (venció, otra pestaña salió) se vuelve al ingreso y nada de la agenda queda a la vista.
  useEffect(
    () =>
      sesion.alCambiar((token, motivo) => {
        if (token !== null) return;
        saliendo.current = false;
        setErrorAlSalir(null);
        setFase({ nombre: 'ingreso', aviso: motivo ?? 'vencida' });
      }),
    [sesion],
  );

  // Volver con "atrás" puede restaurar la página desde la memoria del navegador: se vuelve a comprobar la sesión.
  useEffect(() => {
    const alMostrar = (evento: Event): void => {
      if ((evento as PageTransitionEvent).persisted) reabrir();
    };
    window.addEventListener('pageshow', alMostrar);
    return () => {
      window.removeEventListener('pageshow', alMostrar);
    };
  }, [reabrir]);

  async function ingresar(email: string, password: string) {
    const resultado = await sesion.ingresar(email, password);
    if (resultado.ok) aplicar(await faseDelUsuario());
    return resultado;
  }

  async function salir(): Promise<void> {
    if (saliendo.current) return;
    saliendo.current = true;
    setErrorAlSalir(null);
    const resultado = await sesion.salir();
    saliendo.current = false;
    if (resultado === 'sin_red') {
      setErrorAlSalir(
        'No pudimos cerrar tu sesión porque no hay conexión. Tu sesión sigue abierta en este dispositivo: reintentá cuando vuelva la conexión.',
      );
    }
  }

  switch (fase.nombre) {
    case 'restaurando':
      return (
        <main className="app">
          <Cargando texto="Abriendo el panel…" />
        </main>
      );
    case 'error_apertura':
      return (
        <main className="app">
          <ErrorCarga
            mensaje="No pudimos abrir el panel. Revisá tu conexión e intentá de nuevo."
            onReintentar={reabrir}
          />
        </main>
      );
    case 'ingreso':
      return (
        <div className="app app-ingreso">
          <Ingreso aviso={fase.aviso} onIngresar={ingresar} />
        </div>
      );
    case 'sin_acceso':
      return (
        <main className="app app-ingreso">
          <h1>Tu usuario no tiene acceso al panel</h1>
          <p>
            {fase.usuario.email} no tiene un rol asignado para usar el panel. Pedile a la clínica que te lo asigne y volvé a
            ingresar.
          </p>
          <button type="button" className="boton boton-secundario" onClick={() => void salir()}>
            Salir
          </button>
        </main>
      );
    case 'panel':
      return (
        <div className="app app-panel">
          <header className="cabecera-panel">
            <p className="marca">Panel de la clínica</p>
            <div className="sesion">
              <span className="sesion-nombre">{fase.usuario.nombre_completo}</span>
              <button type="button" className="boton boton-secundario" onClick={() => void salir()}>
                Salir
              </button>
            </div>
          </header>
          {errorAlSalir !== null && (
            <p className="aviso aviso-error" role="alert">
              {errorAlSalir}
            </p>
          )}
          <Secciones usuario={fase.usuario} api={api} hoy={hoy()} />
        </div>
      );
  }
}
