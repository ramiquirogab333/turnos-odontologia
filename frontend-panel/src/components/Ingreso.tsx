import { useId, useState, type FormEvent } from 'react';
import type { MotivoCierre, ResultadoIngreso } from '../lib/sesion';

interface Props {
  readonly aviso: MotivoCierre | null;
  readonly onIngresar: (email: string, password: string) => Promise<ResultadoIngreso>;
}

const AVISOS: Readonly<Record<MotivoCierre, string>> = {
  vencida: 'Tu sesión venció. Ingresá de nuevo para seguir.',
  otra_pestana: 'Cerraste la sesión en otra pestaña. Ingresá de nuevo para seguir.',
  salida: 'Saliste del panel.',
};

const ERRORES: Readonly<Record<'credenciales' | 'red' | 'servidor', string>> = {
  // Un solo mensaje para correo inexistente y contraseña errónea: no revela qué usuarios existen.
  credenciales: 'El correo o la contraseña no son correctos. Revisalos e intentá de nuevo.',
  red: 'No pudimos conectarnos. Revisá tu conexión e intentá de nuevo.',
  servidor: 'El servidor no pudo procesar el ingreso. Intentá de nuevo en unos minutos.',
};

export function Ingreso({ aviso, onIngresar }: Props) {
  const idEmail = useId();
  const idClave = useId();
  const [email, setEmail] = useState('');
  const [clave, setClave] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento: FormEvent<HTMLFormElement>): Promise<void> {
    evento.preventDefault();
    if (enviando) return;
    if (email.trim() === '' || clave === '') {
      setError('Completá el correo y la contraseña.');
      return;
    }
    setError(null);
    setEnviando(true);
    const resultado = await onIngresar(email.trim(), clave);
    setEnviando(false);
    if (!resultado.ok) setError(ERRORES[resultado.motivo]);
  }

  return (
    <main className="ingreso">
      <h1>Ingresá al panel</h1>
      <p className="nota">Panel de la clínica: agenda, turnos y seguimiento del día.</p>
      {aviso !== null && (
        <p className="aviso aviso-info" role="status">
          {AVISOS[aviso]}
        </p>
      )}
      <form onSubmit={(e) => void enviar(e)} noValidate>
        <div className="campo">
          <label htmlFor={idEmail}>Correo electrónico</label>
          <input
            id={idEmail}
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
            }}
          />
        </div>
        <div className="campo">
          <label htmlFor={idClave}>Contraseña</label>
          <input
            id={idClave}
            type="password"
            autoComplete="current-password"
            value={clave}
            onChange={(e) => {
              setClave(e.target.value);
            }}
          />
        </div>
        {error !== null && (
          <p className="aviso aviso-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="boton boton-primario boton-ancho" disabled={enviando}>
          {enviando ? 'Ingresando…' : 'Ingresar al panel'}
        </button>
      </form>
    </main>
  );
}
