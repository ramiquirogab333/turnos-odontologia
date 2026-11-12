import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GestionTurno } from './GestionTurno';

const CODIGO = 'CODIGO-SINTETICO-1';

/** Como en App.test.tsx: cada gesto va dentro de `act` para que las promesas de `use` se resuelvan. */
const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

const RESERVADO = {
  estado: 'reservado',
  inicio: '2026-11-16T10:00:00-03:00',
  fin: '2026-11-16T10:30:00-03:00',
  tratamiento: { id: 1, nombre: 'Limpieza', duracion_minutos: 30 },
  profesional: { id: 7, nombre: 'Dra. Sintética' },
  sena: { monto: '3000.00', estado: 'acreditado' },
  limite_cambios: '2026-11-15T10:00:00-03:00',
  puede_cancelar: true,
  puede_reprogramar: true,
  motivo_no_cancelable: null,
  motivo_no_reprogramable: null,
  puede_confirmar: true,
  motivo_no_confirmable: null,
  texto_politica_reembolso: 'Texto sintético.',
};
const FUERA_DE_PLAZO = {
  ...RESERVADO,
  puede_cancelar: false,
  puede_reprogramar: false,
  motivo_no_cancelable: 'fuera_de_plazo',
  motivo_no_reprogramable: 'fuera_de_plazo',
};
const EN_ESPERA = {
  ...RESERVADO,
  estado: 'en_espera',
  sena: { monto: '3000.00', estado: 'pendiente' },
  puede_reprogramar: false,
  motivo_no_reprogramable: 'sena_pendiente',
};
const SLOTS = {
  slots: [
    { inicio: '2026-11-18T11:00:00-03:00', fin: '2026-11-18T11:30:00-03:00', profesional_id: 7, sillon_id: 1 },
    { inicio: '2026-11-18T11:30:00-03:00', fin: '2026-11-18T12:00:00-03:00', profesional_id: 7, sillon_id: 1 },
  ],
};

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

type Ruta = (url: string, init?: RequestInit) => Response | undefined;

/** Servidor falso: cada prueba declara qué responde a cada URL. */
function servidor(...rutas: Ruta[]) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url, init) => {
    for (const ruta of rutas) {
      const r = ruta(url, init);
      if (r) return Promise.resolve(r.clone());
    }
    return Promise.resolve(json({ detail: 'sin ruta' }, 500));
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

const gestion = (cuerpo: unknown, status = 200): Ruta => (url, init) =>
  url === '/api/public/gestion' && init?.method === 'GET' ? json(cuerpo, status) : undefined;
const post = (ruta: string, cuerpo: unknown, status = 200): Ruta => (url, init) =>
  url === `/api/public/gestion/${ruta}` && init?.method === 'POST' ? json(cuerpo, status) : undefined;
const disponibilidad = (): Ruta => (url) => (url.startsWith('/api/public/disponibilidad') ? json(SLOTS) : undefined);

async function montar() {
  await act(async () => {
    render(<GestionTurno />);
    await Promise.resolve();
  });
}

function llamadasA(mock: ReturnType<typeof servidor>, fragmento: string) {
  return mock.mock.calls.filter(([url]) => url.includes(fragmento));
}

beforeEach(() => {
  window.history.replaceState(null, '', `/gestionar#${CODIGO}`);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

describe('GestionTurno: acceso por código', () => {
  it('lee el código del hash, lo saca de la URL y lo manda solo en la cabecera', async () => {
    const mock = servidor(gestion(RESERVADO));
    await montar();

    expect(await screen.findByText(/Limpieza/)).toBeInTheDocument();
    expect(window.location.hash).toBe('');
    const [url, init] = mock.mock.calls[0] ?? ['', undefined];
    expect(url).toBe('/api/public/gestion');
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe(CODIGO);
  });

  it('sin hash pide pegar el código y recién entonces consulta', async () => {
    window.history.replaceState(null, '', '/gestionar');
    const mock = servidor(gestion(RESERVADO));
    await montar();

    expect(mock).not.toHaveBeenCalled();
    await usuario.type(screen.getByLabelText(/código de gestión/i), `  ${CODIGO} `);
    await usuario.click(screen.getByRole('button', { name: /ver mi turno/i }));

    expect(await screen.findByText(/Limpieza/)).toBeInTheDocument();
    expect(new Headers(mock.mock.calls[0]?.[1]?.headers).get('X-Codigo-Gestion')).toBe(CODIGO);
  });

  it('un código desconocido muestra "No encontramos un turno con ese código"', async () => {
    servidor(gestion({ detail: 'No encontramos un turno con ese código' }, 404));
    await montar();
    expect(await screen.findByText(/No encontramos un turno con ese código/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /cancelar turno/i })).not.toBeInTheDocument();
  });
});

describe('GestionTurno: datos y plazo', () => {
  it('muestra día, hora de la clínica, tratamiento, profesional, seña y el límite', async () => {
    servidor(gestion(RESERVADO));
    await montar();

    expect(await screen.findByText(/lunes 16 de noviembre/i)).toBeInTheDocument();
    expect(screen.getByText(/10:00 a 10:30/)).toBeInTheDocument();
    expect(screen.getByText(/Limpieza con Dra\. Sintética/)).toBeInTheDocument();
    expect(screen.getByText(/3\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/Podés cancelar o cambiar el horario hasta el domingo 15 de noviembre a las 10:00/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancelar turno/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /cambiar horario/i })).toBeEnabled();
  });

  it('dentro de las 24 h explica por qué y no ofrece acciones', async () => {
    servidor(gestion(FUERA_DE_PLAZO));
    await montar();

    expect(await screen.findByText(/Ya no podés cancelar ni cambiar el turno online/)).toBeInTheDocument();
    expect(screen.getByText(/Comunicate con la clínica/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /cancelar turno/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /cambiar horario/i })).not.toBeInTheDocument();
  });

  it('una pre-reserva se puede cancelar pero no cambiar de horario', async () => {
    servidor(gestion(EN_ESPERA));
    await montar();

    expect(await screen.findByRole('button', { name: /cancelar turno/i })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /cambiar horario/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Cancelalo y reservá otro horario/)).toBeInTheDocument();
  });

  it('no pide la disponibilidad al montar (R2: solo al tocar "Cambiar horario")', async () => {
    const mock = servidor(gestion(RESERVADO), disponibilidad());
    await montar();
    await screen.findByText(/Limpieza/);
    expect(llamadasA(mock, 'disponibilidad')).toHaveLength(0);
  });
});

describe('GestionTurno: cancelar', () => {
  it('con seña acreditada avisa que se devuelve, y al confirmar muestra "Turno cancelado"', async () => {
    const mock = servidor(gestion(RESERVADO), post('cancelar', { estado: 'cancelado', estado_sena: 'a_reembolsar' }));
    await montar();

    await usuario.click(await screen.findByRole('button', { name: /cancelar turno/i }));
    const dialogo = screen.getByRole('alertdialog');
    expect(within(dialogo).getByText(/La clínica te va a devolver la seña de \$\s?3\.000,00/)).toBeInTheDocument();
    expect(llamadasA(mock, '/cancelar')).toHaveLength(0);

    await usuario.click(within(dialogo).getByRole('button', { name: /sí, cancelar el turno/i }));
    expect(await screen.findByRole('heading', { name: 'Turno cancelado' })).toBeInTheDocument();
    expect(llamadasA(mock, '/cancelar')).toHaveLength(1);
  });

  it('una pre-reserva dice "No se te cobra nada"', async () => {
    servidor(gestion(EN_ESPERA), post('cancelar', { estado: 'cancelado', estado_sena: 'vencido' }));
    await montar();

    await usuario.click(await screen.findByRole('button', { name: /cancelar turno/i }));
    expect(within(screen.getByRole('alertdialog')).getByText(/No se te cobra nada/)).toBeInTheDocument();
  });

  it('"Mantener el turno" cierra el diálogo sin llamar al servidor', async () => {
    const mock = servidor(gestion(RESERVADO));
    await montar();

    await usuario.click(await screen.findByRole('button', { name: /cancelar turno/i }));
    await usuario.click(screen.getByRole('button', { name: /mantener el turno/i }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(llamadasA(mock, '/cancelar')).toHaveLength(0);
  });

  it('si el servidor dice fuera_de_plazo muestra el aviso de 24 h y el turno no se da por cancelado', async () => {
    servidor(
      gestion(RESERVADO),
      post('cancelar', { detail: 'x', motivo: 'fuera_de_plazo', limite_cambios: '2026-11-15T10:00:00-03:00' }, 409),
    );
    await montar();

    await usuario.click(await screen.findByRole('button', { name: /cancelar turno/i }));
    await usuario.click(screen.getByRole('button', { name: /sí, cancelar el turno/i }));
    expect(await screen.findByText(/Ya no podés cancelar ni cambiar el turno online/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Turno cancelado' })).not.toBeInTheDocument();
  });
});

describe('GestionTurno: cambiar horario', () => {
  it('pide la disponibilidad al tocar, confirma y muestra "Turno reprogramado"', async () => {
    const mock = servidor(
      gestion(RESERVADO),
      disponibilidad(),
      post('reprogramar', { estado: 'reservado', inicio: SLOTS.slots[0]?.inicio, fin: SLOTS.slots[0]?.fin, estado_sena: 'acreditado' }),
    );
    await montar();

    await usuario.click(await screen.findByRole('button', { name: /cambiar horario/i }));
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await usuario.click(screen.getByRole('button', { name: /continuar/i }));
    await usuario.click(screen.getByRole('button', { name: /confirmar cambio/i }));

    expect(await screen.findByRole('heading', { name: 'Turno reprogramado' })).toBeInTheDocument();
    expect(screen.getByText(/miércoles 18 de noviembre/i)).toBeInTheDocument();
    const [, init] = llamadasA(mock, '/reprogramar')[0] ?? ['', undefined];
    expect(JSON.parse(typeof init?.body === 'string' ? init.body : '')).toEqual({ inicio: '2026-11-18T11:00:00-03:00' });
    const url = String(llamadasA(mock, 'disponibilidad')[0]?.[0]);
    expect(url).toContain('profesional_id=7');
    expect(url).toContain('tratamiento_id=1');
  });

  it('ante un horario ocupado avisa y ofrece las alternativas; elegir una funciona', async () => {
    const alt = { inicio: '2026-11-18T12:00:00-03:00', fin: '2026-11-18T12:30:00-03:00', sillon_id: 1 };
    let intento = 0;
    const reprogramar: Ruta = (url, init) => {
      if (url !== '/api/public/gestion/reprogramar' || init?.method !== 'POST') return undefined;
      intento += 1;
      return intento === 1
        ? json({ detail: 'x', motivo: 'profesional', alternativas: [alt] }, 409)
        : json({ estado: 'reservado', inicio: alt.inicio, fin: alt.fin, estado_sena: 'acreditado' });
    };
    const mock = servidor(gestion(RESERVADO), disponibilidad(), reprogramar);
    await montar();

    await usuario.click(await screen.findByRole('button', { name: /cambiar horario/i }));
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await usuario.click(screen.getByRole('button', { name: /continuar/i }));
    await usuario.click(screen.getByRole('button', { name: /confirmar cambio/i }));

    expect(await screen.findByText(/Ese horario ya no está disponible/)).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: /12:00/ }));
    await usuario.click(screen.getByRole('button', { name: /confirmar cambio/i }));

    expect(await screen.findByRole('heading', { name: 'Turno reprogramado' })).toBeInTheDocument();
    expect(llamadasA(mock, '/reprogramar')).toHaveLength(2);
  });

  it('un 409 fuera_de_plazo al reprogramar muestra el aviso de 24 h', async () => {
    servidor(
      gestion(RESERVADO),
      disponibilidad(),
      post('reprogramar', { detail: 'x', motivo: 'fuera_de_plazo', limite_cambios: '2026-11-15T10:00:00-03:00' }, 409),
    );
    await montar();

    await usuario.click(await screen.findByRole('button', { name: /cambiar horario/i }));
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await usuario.click(screen.getByRole('button', { name: /continuar/i }));
    await usuario.click(screen.getByRole('button', { name: /confirmar cambio/i }));

    expect(await screen.findByText(/Ya no podés cancelar ni cambiar el turno online/)).toBeInTheDocument();
  });
});
