import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfirmarTurno } from './ConfirmarTurno';

const CODIGO = 'CODIGO-SINTETICO-150';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

const RESERVADO = {
  estado: 'reservado',
  inicio: '2026-11-17T10:30:00-03:00',
  fin: '2026-11-17T11:00:00-03:00',
  tratamiento: { id: 1, nombre: 'Limpieza', duracion_minutos: 30 },
  profesional: { id: 7, nombre: 'Dra. Ficticia' },
  sena: { monto: '3000.00', estado: 'acreditado' },
  limite_cambios: '2026-11-16T10:30:00-03:00',
  puede_cancelar: true,
  puede_reprogramar: true,
  motivo_no_cancelable: null,
  motivo_no_reprogramable: null,
  puede_confirmar: true,
  motivo_no_confirmable: null,
  texto_politica_reembolso: 'Texto sintético.',
};
const CANCELADO = {
  ...RESERVADO,
  estado: 'cancelado',
  puede_cancelar: false,
  puede_reprogramar: false,
  puede_confirmar: false,
  motivo_no_confirmable: 'turno_no_modificable',
};
const CONFIRMADO_YA = { ...RESERVADO, estado: 'confirmado', puede_confirmar: false, motivo_no_confirmable: 'ya_confirmado' };
const EN_ESPERA = { ...RESERVADO, estado: 'en_espera', puede_confirmar: false, motivo_no_confirmable: 'sena_pendiente' };
const CONFIRMADO = { estado: 'confirmado', inicio: RESERVADO.inicio, fin: RESERVADO.fin };

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

/** Servidor falso: GET de la consulta y POST de la confirmación. */
function servidor(consulta: Response, confirmacion: Response = json(CONFIRMADO)) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url, init) => {
    if (url === '/api/public/gestion' && init?.method === 'GET') return Promise.resolve(consulta.clone());
    if (url === '/api/public/gestion/confirmar' && init?.method === 'POST') return Promise.resolve(confirmacion.clone());
    return Promise.resolve(json({ detail: 'sin ruta' }, 500));
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

async function montar() {
  await act(async () => {
    render(<ConfirmarTurno />);
    await Promise.resolve();
  });
}

const posts = (mock: ReturnType<typeof servidor>) => mock.mock.calls.filter(([, init]) => init?.method === 'POST');

beforeEach(() => {
  window.history.replaceState(null, '', `/confirmar#${CODIGO}`);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

describe('ConfirmarTurno: abrir el enlace nunca confirma', () => {
  it('muestra día, hora, profesional y tratamiento y NO envía ninguna confirmación', async () => {
    const mock = servidor(json(RESERVADO));
    await montar();

    expect(await screen.findByText(/martes 17 de noviembre/i)).toBeInTheDocument();
    expect(screen.getByText(/10:30/)).toBeInTheDocument();
    expect(screen.getByText(/Limpieza con Dra\. Ficticia/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar asistencia' })).toBeEnabled();
    expect(posts(mock)).toHaveLength(0);
  });

  it('lee el código del fragmento, lo saca de la URL y lo manda solo en la cabecera', async () => {
    const mock = servidor(json(RESERVADO));
    await montar();
    await screen.findByRole('button', { name: 'Confirmar asistencia' });

    expect(window.location.hash).toBe('');
    const [url, init] = mock.mock.calls[0] ?? ['', undefined];
    expect(url).not.toContain('CODIGO');
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe(CODIGO);
  });
});

describe('ConfirmarTurno: confirmar', () => {
  it('al tocar el botón confirma y muestra el mensaje de éxito sin el botón', async () => {
    const mock = servidor(json(RESERVADO));
    await montar();

    await usuario.click(await screen.findByRole('button', { name: 'Confirmar asistencia' }));

    expect(await screen.findByText(/¡Listo! Confirmaste tu turno del martes 17\/11 a las 10:30/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirmar asistencia' })).not.toBeInTheDocument();
    expect(posts(mock)).toHaveLength(1);
    expect(new Headers(posts(mock)[0]?.[1]?.headers).get('X-Codigo-Gestion')).toBe(CODIGO);
  });

  it('si la clínica rechaza la confirmación (el turno empezó) lo dice y no deja reintentar', async () => {
    servidor(json(RESERVADO), json({ detail: 'x', motivo: 'turno_iniciado' }, 409));
    await montar();

    await usuario.click(await screen.findByRole('button', { name: 'Confirmar asistencia' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/ya empezó/i);
    expect(screen.queryByRole('button', { name: 'Confirmar asistencia' })).not.toBeInTheDocument();
  });

  it('ante un error de red muestra el aviso y deja reintentar', async () => {
    const mock = servidor(json(RESERVADO));
    await montar();
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) =>
        init?.method === 'POST' ? Promise.reject(new TypeError('red')) : mock(url, init),
      ),
    );

    await usuario.click(await screen.findByRole('button', { name: 'Confirmar asistencia' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/conectar con la clínica/i);
    expect(screen.getByRole('button', { name: 'Confirmar asistencia' })).toBeEnabled();
  });
});

describe('ConfirmarTurno: turnos que no se pueden confirmar', () => {
  it('un turno cancelado dice que ya no se puede confirmar, sin botón de confirmar', async () => {
    const mock = servidor(json(CANCELADO));
    await montar();

    expect(await screen.findByText('Este turno ya no se puede confirmar')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirmar asistencia' })).not.toBeInTheDocument();
    expect(posts(mock)).toHaveLength(0);
  });

  it('una pre-reserva explica que falta la seña y no ofrece confirmar', async () => {
    servidor(json(EN_ESPERA));
    await montar();

    expect(await screen.findByText('Este turno ya no se puede confirmar')).toBeInTheDocument();
    expect(screen.getByText(/seña/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirmar asistencia' })).not.toBeInTheDocument();
  });

  it('un turno ya confirmado lo dice y no ofrece confirmar de nuevo', async () => {
    servidor(json(CONFIRMADO_YA));
    await montar();

    expect(await screen.findByText(/Ya confirmaste tu turno/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirmar asistencia' })).not.toBeInTheDocument();
  });

  it('un código desconocido muestra el aviso de que no se encontró el turno', async () => {
    servidor(json({ detail: 'No encontramos un turno con ese código' }, 404));
    await montar();

    expect(await screen.findByRole('alert')).toHaveTextContent(/No encontramos un turno con ese código/);
    expect(screen.queryByRole('button', { name: 'Confirmar asistencia' })).not.toBeInTheDocument();
  });

  it('sin código en el enlace no consulta nada y pide abrir el enlace del mensaje', async () => {
    window.history.replaceState(null, '', '/confirmar');
    const mock = servidor(json(RESERVADO));
    await montar();

    expect(screen.getByText(/Abrí el enlace del mensaje/)).toBeInTheDocument();
    expect(mock).not.toHaveBeenCalled();
  });
});

describe('ConfirmarTurno: gestionar el turno', () => {
  it.each([
    ['reservado', RESERVADO],
    ['cancelado', CANCELADO],
    ['confirmado', CONFIRMADO_YA],
  ])('ofrece el enlace a Gestionar mi turno con el mismo código (%s)', async (_nombre, cuerpo) => {
    servidor(json(cuerpo));
    await montar();

    const enlace = await screen.findByRole('link', { name: 'Gestionar mi turno' });
    expect(enlace).toHaveAttribute('href', `/gestionar#${CODIGO}`);
  });
});
