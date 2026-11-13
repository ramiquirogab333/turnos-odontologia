import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EsperaAcreditacion } from './EsperaAcreditacion';

const BASE = {
  turno_id: 5,
  pago_id: 11,
  medio: 'mercadopago',
  monto: '3000.00',
  vence_en: '2026-11-16T09:30:00-03:00',
  texto_politica_reembolso: 'Texto sintético de política.',
  referencia_externa: 'abc123abc123abc123abc123abc123ab',
  checkout_url: null,
  alias: null,
  cbu: null,
  titular: null,
  referencia_concepto: null,
  medios_habilitados: ['mercadopago'],
  inicio: '2026-11-16T10:00:00-03:00',
  fin: '2026-11-16T10:30:00-03:00',
  tratamiento_nombre: 'Limpieza',
  profesional_nombre: 'Dra. Sintética',
};
const ESPERANDO = { ...BASE, estado_turno: 'en_espera', estado_pago: 'pendiente', vencida: false };

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function servidor(...respuestas: Response[]) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => {
    const siguiente = respuestas.length > 1 ? respuestas.shift() : respuestas[0];
    return Promise.resolve(siguiente ? siguiente.clone() : json({}, 500));
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

async function montar(onNueva: () => void = vi.fn()) {
  await act(async () => {
    render(<EsperaAcreditacion turnoId={5} codigoGestion="ABCD2345" onNueva={onNueva} />);
    await Promise.resolve();
  });
  return onNueva;
}

async function avanzar(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('EsperaAcreditacion: sondeo', () => {
  it('consulta enseguida y luego cada 3 s mientras siga esperando, con el código en la cabecera', async () => {
    const mock = servidor(json(ESPERANDO));
    await montar();
    expect(mock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent(/esperando la acreditación/i);
    await avanzar(2_900);
    expect(mock).toHaveBeenCalledTimes(1);
    await avanzar(200);
    expect(mock).toHaveBeenCalledTimes(2);
    await avanzar(3_000);
    expect(mock).toHaveBeenCalledTimes(3);
    const [url, init] = mock.mock.calls[0] ?? [];
    expect(url).toBe('/api/public/turnos/5/sena');
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe('ABCD2345');
  });

  it('se rinde a los 2 minutos: muestra "Seguimos esperando la acreditación" y deja de consultar', async () => {
    const mock = servidor(json(ESPERANDO));
    await montar();
    await avanzar(121_000);
    expect(screen.getByRole('heading', { name: 'Seguimos esperando la acreditación' })).toBeInTheDocument();
    const llamadas = mock.mock.calls.length;
    expect(llamadas).toBeGreaterThanOrEqual(40);
    expect(llamadas).toBeLessThanOrEqual(42);
    await avanzar(30_000);
    expect(mock).toHaveBeenCalledTimes(llamadas); // ya no sondea
  });

  it('"Revisar de nuevo" reanuda el sondeo y puede terminar en reservado', async () => {
    const respuestas = [json(ESPERANDO)];
    const mock = servidor(...respuestas);
    await montar();
    await avanzar(121_000);
    mock.mockImplementation(() => Promise.resolve(json({ ...BASE, estado_turno: 'reservado', estado_pago: 'acreditado', vencida: false })));
    const boton = screen.getByRole('button', { name: 'Revisar de nuevo' });
    await act(async () => {
      boton.click();
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByRole('heading', { name: 'Turno reservado' })).toBeInTheDocument();
  });

  it('un error de red momentáneo no corta el sondeo', async () => {
    const mock = vi
      .fn<(url: string, init?: RequestInit) => Promise<Response>>()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue(json({ ...BASE, estado_turno: 'reservado', estado_pago: 'acreditado', vencida: false }));
    vi.stubGlobal('fetch', mock);
    await montar();
    expect(screen.queryByRole('heading', { name: 'Turno reservado' })).not.toBeInTheDocument();
    await avanzar(3_100);
    expect(screen.getByRole('heading', { name: 'Turno reservado' })).toBeInTheDocument();
  });
});

describe('EsperaAcreditacion: pantallas terminales', () => {
  it('reservado/acreditado lleva a "Turno reservado" con el código y el horario de la clínica', async () => {
    servidor(json({ ...BASE, estado_turno: 'reservado', estado_pago: 'acreditado', vencida: false }));
    await montar();
    expect(screen.getByRole('heading', { name: 'Turno reservado' })).toBeInTheDocument();
    expect(screen.getByText('ABCD2345')).toBeInTheDocument();
    expect(screen.getByText(/10:00 a 10:30/)).toBeInTheDocument();
    expect(screen.getByText(/limpieza con dra\. sintética/i)).toBeInTheDocument();
  });

  it('vencida lleva a "La reserva venció" con "Elegir otro horario"', async () => {
    servidor(json({ ...BASE, estado_turno: 'cancelado', estado_pago: 'vencido', vencida: true }));
    const onNueva = await montar();
    expect(screen.getByRole('heading', { name: 'La reserva venció' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Turno reservado' })).not.toBeInTheDocument();
    await act(async () => {
      screen.getByRole('button', { name: 'Elegir otro horario' }).click();
      await Promise.resolve();
    });
    expect(onNueva).toHaveBeenCalledTimes(1);
  });

  it('una pre-reserva en_espera que el servidor ya marca vencida también termina en "La reserva venció"', async () => {
    servidor(json({ ...ESPERANDO, vencida: true }));
    await montar();
    expect(screen.getByRole('heading', { name: 'La reserva venció' })).toBeInTheDocument();
  });

  it('a_reembolsar lleva al mensaje de devolución', async () => {
    servidor(json({ ...BASE, estado_turno: 'cancelado', estado_pago: 'a_reembolsar', vencida: false }));
    await montar();
    expect(screen.getByRole('heading', { name: 'El horario se ocupó' })).toBeInTheDocument();
    expect(screen.getByText('La clínica se va a comunicar para devolverte la seña.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Elegir otro horario' })).toBeInTheDocument();
  });

  it('un turno que no existe o un código ajeno (404) corta con un mensaje claro', async () => {
    servidor(json({ detail: 'Turno no encontrado' }, 404));
    await montar();
    expect(screen.getByRole('heading', { name: 'No encontramos tu reserva' })).toBeInTheDocument();
  });

  it('mientras espera muestra el encabezado que le pasen (los datos de la transferencia)', async () => {
    servidor(json(ESPERANDO));
    await act(async () => {
      render(
        <EsperaAcreditacion turnoId={5} codigoGestion="ABCD2345" onNueva={vi.fn()} encabezado={<p>Datos de ejemplo</p>} />,
      );
      await Promise.resolve();
    });
    expect(screen.getByText('Datos de ejemplo')).toBeInTheDocument();
  });
});

describe('EsperaAcreditacion: pago en revisión (RN-SN-09)', () => {
  it('muestra una pantalla clara de "revisando tu pago" en lugar de quedar en error', async () => {
    servidor(json({ ...ESPERANDO, estado_pago: 'en_revision' }));
    await montar();
    expect(screen.getByRole('heading', { name: 'Estamos revisando tu pago' })).toBeInTheDocument();
    expect(screen.getByText('La clínica se va a comunicar con vos.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'La reserva venció' })).not.toBeInTheDocument();
  });

  it('si el barrido ya canceló el turno, con el pago en revisión NO dice "La reserva venció"', async () => {
    servidor(json({ ...BASE, estado_turno: 'cancelado', estado_pago: 'en_revision', vencida: true }));
    await montar();
    expect(screen.getByRole('heading', { name: 'Estamos revisando tu pago' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'La reserva venció' })).not.toBeInTheDocument();
  });

  it('sigue consultando y pasa a "Turno reservado" cuando la clínica lo acredita', async () => {
    const mock = servidor(json({ ...ESPERANDO, estado_pago: 'en_revision' }));
    await montar();
    mock.mockImplementation(() => Promise.resolve(json({ ...BASE, estado_turno: 'reservado', estado_pago: 'acreditado', vencida: false })));
    await avanzar(3_100);
    expect(screen.getByRole('heading', { name: 'Turno reservado' })).toBeInTheDocument();
  });
});

describe('EsperaAcreditacion: limpieza del almacenamiento', () => {
  it.each([
    ['reservado', { ...BASE, estado_turno: 'reservado', estado_pago: 'acreditado', vencida: false }],
    ['vencida', { ...BASE, estado_turno: 'cancelado', estado_pago: 'vencido', vencida: true }],
    ['a_reembolsar', { ...BASE, estado_turno: 'cancelado', estado_pago: 'a_reembolsar', vencida: false }],
  ])('al llegar a un estado terminal (%s) se borra la seña pendiente', async (_nombre, cuerpo) => {
    localStorage.setItem('sena-pendiente-v2', JSON.stringify({ v: 2, turnoId: 5, codigoGestion: 'ABCD2345', expira: Date.now() + 3_600_000 }));
    servidor(json(cuerpo));
    await montar();
    expect(localStorage.getItem('sena-pendiente-v2')).toBeNull();
  });

  it('mientras sigue esperando NO se borra (el paciente puede recargar)', async () => {
    localStorage.setItem('sena-pendiente-v2', JSON.stringify({ v: 2, turnoId: 5, codigoGestion: 'ABCD2345', expira: Date.now() + 3_600_000 }));
    servidor(json(ESPERANDO));
    await montar();
    expect(localStorage.getItem('sena-pendiente-v2')).not.toBeNull();
  });
});

describe('EsperaAcreditacion: usuario real', () => {
  it('con timers reales no pierde el foco ni rompe al desmontar durante una consulta', async () => {
    vi.useRealTimers();
    servidor(json(ESPERANDO));
    const { unmount } = render(<EsperaAcreditacion turnoId={5} codigoGestion="ABCD2345" onNueva={vi.fn()} />);
    unmount();
    await userEvent.setup().keyboard('{Tab}');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
