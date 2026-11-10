import { useCallback, useEffect, useRef, useState } from 'react';
import { Agenda } from './components/Agenda';
import { Cargando } from './components/Cargando';
import { ErrorCarga } from './components/ErrorCarga';
import { Ingreso } from './components/Ingreso';
import type { Api } from './lib/api';
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
            <h1>Agenda</h1>
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
          <main>
            <Agenda api={api} hoy={hoy()} />
          </main>
        </div>
      );
  }
}
