import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MedioSena, Profesional, ReservaEnEspera, Tratamiento } from '../lib/tipos';
import { PagoSena } from './PagoSena';

const POLITICA = 'Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve.';
const TRATAMIENTO: Tratamiento = { id: 1, nombre: 'Limpieza', duracion_minutos: 30, precio_base: '10000.00' };
const PROFESIONAL: Profesional = { id: 7, nombre: 'Dra. Sintética', especialidad: 'General' };

function reserva(sobre: Partial<ReservaEnEspera['sena']> = {}): ReservaEnEspera {
  return {
    turno_id: 5,
    codigo_gestion: 'ABCD2345',
    estado: 'en_espera',
    inicio: '2026-11-16T10:00:00-03:00',
    fin: '2026-11-16T10:30:00-03:00',
    sena: {
      monto: '3000.00',
      vence_en: '2026-11-16T09:30:00-03:00',
      medios_habilitados: ['mercadopago', 'transferencia'],
      texto_politica_reembolso: POLITICA,
      ...sobre,
    },
  };
}

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

const DATOS_PAGO = {
  turno_id: 5,
  pago_id: 11,
  estado: 'pendiente',
  monto: '3000.00',
  vence_en: '2026-11-16T09:30:00-03:00',
  texto_politica_reembolso: POLITICA,
  referencia_externa: 'abc123abc123abc123abc123abc123ab',
};
const INICIO_MP = {
  ...DATOS_PAGO,
  medio: 'mercadopago',
  checkout_url: 'http://localhost:5173/?pago=retorno&turno=5',
  alias: null,
  cbu: null,
  titular: null,
  referencia_concepto: null,
};
const INICIO_TR = {
  ...DATOS_PAGO,
  medio: 'transferencia',
  referencia_externa: 'SENA-5-A1B2C3',
  checkout_url: null,
  alias: 'clinica.demo.sintetica',
  cbu: '0000003100000000000043',
  titular: 'Clínica Demo Sintética',
  referencia_concepto: 'SENA-5-A1B2C3',
};
const ESTADO_ESPERA = {
  turno_id: 5,
  estado_turno: 'en_espera',
  estado_pago: 'pendiente',
  vencida: false,
  medios_habilitados: ['mercadopago', 'transferencia'],
  pago_id: 11,
  medio: 'transferencia',
  monto: '3000.00',
  vence_en: '2026-11-16T09:30:00-03:00',
  texto_politica_reembolso: POLITICA,
  referencia_externa: 'SENA-5-A1B2C3',
  checkout_url: null,
  alias: null,
  cbu: null,
  titular: null,
  referencia_concepto: null,
  inicio: '2026-11-16T10:00:00-03:00',
  fin: '2026-11-16T10:30:00-03:00',
  tratamiento_nombre: 'Limpieza',
  profesional_nombre: 'Dra. Sintética',
};

function servidor(medio: MedioSena | null, extra?: { post?: Response }) {
  const mock = vi.fn((_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      return Promise.resolve(extra?.post ?? json(medio === 'transferencia' ? INICIO_TR : INICIO_MP, 201));
    }
    return Promise.resolve(json(ESTADO_ESPERA));
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

function montar(r: ReservaEnEspera = reserva(), irA: (url: string) => void = vi.fn(), onNueva: () => void = vi.fn()) {
  render(<PagoSena reserva={r} tratamiento={TRATAMIENTO} profesional={PROFESIONAL} onNueva={onNueva} irA={irA} />);
  return { irA, onNueva };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('PagoSena: qué ve el paciente (R3, R8)', () => {
  it('muestra el título, el monto exacto, el vencimiento en hora de la clínica y el aviso de no confirmado', () => {
    montar();
    expect(screen.getByRole('heading', { name: 'Pagá la seña para confirmar tu turno' })).toBeInTheDocument();
    expect(screen.getByText(/3\.000,00/)).toBeInTheDocument();
    // El runner corre en Asia/Tokyo: 09:30-03:00 son 21:30 allá. Se muestra la hora de la clínica.
    expect(screen.getByText('Tu reserva vence a las 09:30')).toBeInTheDocument();
    expect(screen.getByText(/tu turno no está confirmado hasta acreditar la seña/i)).toBeInTheDocument();
    expect(screen.getByText(/limpieza con dra\. sintética/i)).toBeInTheDocument();
    expect(screen.getByText(/lunes 16 de noviembre/i)).toBeInTheDocument();
  });

  it('muestra el texto de política que viene de la API y no tiene textos fijos de "no reembolsable"', () => {
    const { unmount } = render(
      <PagoSena reserva={reserva()} tratamiento={TRATAMIENTO} profesional={PROFESIONAL} onNueva={vi.fn()} irA={vi.fn()} />,
    );
    expect(screen.getByText(POLITICA)).toBeInTheDocument();
    expect(screen.queryByText(/no reembolsable/i)).not.toBeInTheDocument();
    unmount();

    // triangulación: otro texto configurado por el admin se muestra tal cual
    montar(reserva({ texto_politica_reembolso: 'Política sintética distinta.' }));
    expect(screen.getByText('Política sintética distinta.')).toBeInTheDocument();
    expect(screen.queryByText(POLITICA)).not.toBeInTheDocument();
  });

  it('ofrece un botón por medio habilitado, y solo esos', () => {
    montar();
    expect(screen.getByRole('button', { name: 'Pagar con Mercado Pago' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pagar por transferencia' })).toBeInTheDocument();
    document.body.innerHTML = '';
    montar(reserva({ medios_habilitados: ['mercadopago'] }));
    expect(screen.getByRole('button', { name: 'Pagar con Mercado Pago' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Pagar por transferencia' })).not.toBeInTheDocument();
  });
});

describe('PagoSena: Mercado Pago', () => {
  it('guarda {turnoId, codigoGestion} en localStorage y redirige al checkout (sin código en la URL)', async () => {
    const fetchMock = servidor('mercadopago');
    const { irA } = montar();
    await userEvent.click(screen.getByRole('button', { name: 'Pagar con Mercado Pago' }));

    await vi.waitFor(() => {
      expect(irA).toHaveBeenCalledWith('http://localhost:5173/?pago=retorno&turno=5');
    });
    const guardado = JSON.parse(localStorage.getItem('sena-pendiente-v2') ?? 'null') as Record<string, unknown>;
    expect(guardado).toMatchObject({ turnoId: 5, codigoGestion: 'ABCD2345' });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/public/turnos/5/sena');
    expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe('ABCD2345');
    expect(String(vi.mocked(irA).mock.calls[0]?.[0])).not.toContain('ABCD2345');
  });

  it('si el almacenamiento está bloqueado igual redirige (try/catch)', async () => {
    servidor('mercadopago');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('bloqueado', 'SecurityError');
    });
    const { irA } = montar();
    await userEvent.click(screen.getByRole('button', { name: 'Pagar con Mercado Pago' }));
    await vi.waitFor(() => {
      expect(irA).toHaveBeenCalledTimes(1);
    });
  });

  it('si Mercado Pago no responde (502) avisa y deja reintentar sin redirigir', async () => {
    servidor('mercadopago', { post: json({ detail: 'No pudimos conectar con Mercado Pago.' }, 502) });
    const { irA } = montar();
    await userEvent.click(screen.getByRole('button', { name: 'Pagar con Mercado Pago' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/mercado pago/i);
    expect(irA).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Pagar con Mercado Pago' })).toBeEnabled();
  });

  it('si la reserva venció o el horario se ocupó ofrece elegir otro horario', async () => {
    servidor('mercadopago', { post: json({ detail: 'La reserva venció', motivo: 'estado_invalido' }, 409) });
    const { onNueva } = montar();
    await userEvent.click(screen.getByRole('button', { name: 'Pagar con Mercado Pago' }));
    expect(await screen.findByRole('heading', { name: 'La reserva venció' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Elegir otro horario' }));
    expect(onNueva).toHaveBeenCalledTimes(1);
  });
});

describe('PagoSena: transferencia', () => {
  it('muestra alias, CBU, titular, monto y código de referencia, cada uno con su botón Copiar', async () => {
    servidor('transferencia');
    montar();
    await userEvent.click(screen.getByRole('button', { name: 'Pagar por transferencia' }));

    const datos = await screen.findByRole('region', { name: /datos para transferir/i });
    expect(within(datos).getByText('clinica.demo.sintetica')).toBeInTheDocument();
    expect(within(datos).getByText('0000003100000000000043')).toBeInTheDocument();
    expect(within(datos).getByText('Clínica Demo Sintética')).toBeInTheDocument();
    expect(within(datos).getByText('SENA-5-A1B2C3')).toBeInTheDocument();
    expect(within(datos).getByText(/3\.000,00/)).toBeInTheDocument();
    expect(within(datos).getByText(/poné este código en el concepto/i)).toBeInTheDocument();
    expect(within(datos).getAllByRole('button', { name: /^Copiar/ })).toHaveLength(4);
    expect(screen.getByText(/la clínica confirma tu turno al acreditar la transferencia/i)).toBeInTheDocument();
  });

  it('copiar escribe el valor en el portapapeles y lo avisa', async () => {
    servidor('transferencia');
    const escribir = vi.fn(() => Promise.resolve());
    const usuario = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: escribir }, configurable: true });
    montar();
    await usuario.click(screen.getByRole('button', { name: 'Pagar por transferencia' }));
    const datos = await screen.findByRole('region', { name: /datos para transferir/i });

    await usuario.click(within(datos).getByRole('button', { name: 'Copiar CBU' }));
    expect(escribir).toHaveBeenLastCalledWith('0000003100000000000043');
    await usuario.click(within(datos).getByRole('button', { name: 'Copiar código de referencia' }));
    expect(escribir).toHaveBeenLastCalledWith('SENA-5-A1B2C3');
    expect(await screen.findAllByText('Copiado')).toHaveLength(2);
  });
});
