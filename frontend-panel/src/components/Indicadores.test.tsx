import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Ocupacion } from '../lib/tipos';
import { apiFalsa, AUSENTISMO, OCUPACION } from '../test/datos';
import { Indicadores } from './Indicadores';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

// 2031-11-18 es martes: la semana va del 17 al 23.
const HOY = '2031-11-18';

async function montar(api = apiFalsa()) {
  await act(async () => {
    render(<Indicadores api={api} hoy={HOY} />);
    await Promise.resolve();
  });
  return api;
}

describe('Pantalla de indicadores', () => {
  it('las dos consultas salen juntas: ninguna espera a la otra (R2)', async () => {
    let resolverOcupacion: (v: Ocupacion) => void = () => undefined;
    const api = apiFalsa({
      ocupacion: vi.fn(() => new Promise<Ocupacion>((res) => { resolverOcupacion = res; })),
    });
    await montar(api);
    // Con la ocupación todavía pendiente, el ausentismo ya se pidió.
    expect(api.ocupacion).toHaveBeenCalledTimes(1);
    expect(api.ausentismo).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Tasa de ausentismo/)).toBeInTheDocument();
    await act(async () => {
      resolverOcupacion(OCUPACION);
      await Promise.resolve();
    });
    expect(await screen.findByText('Sillón 1')).toBeInTheDocument();
  });

  it('abre en el día de hoy', async () => {
    const api = await montar();
    expect(api.ocupacion).toHaveBeenCalledWith(HOY, HOY);
    expect(api.ausentismo).toHaveBeenCalledWith(HOY, HOY);
  });

  it('cada sillón muestra su porcentaje y los minutos en texto', async () => {
    await montar();
    const sillon = (await screen.findByText('Sillón 1')).closest('section');
    expect(sillon).not.toBeNull();
    const dentro = within(sillon as HTMLElement);
    expect(dentro.getByText(/37,5 % ocupado/)).toBeInTheDocument();
    expect(dentro.getByText(/90 de 240 minutos/)).toBeInTheDocument();
    expect(dentro.getByText(/3 turnos/)).toBeInTheDocument();
  });

  it('un sillón sin atención ese día lo dice con palabras, no con un 0 %', async () => {
    await montar();
    const sillon = (await screen.findByText('Sillón 2')).closest('section');
    expect(within(sillon as HTMLElement).getByText('Sin atención ese día')).toBeInTheDocument();
    expect(within(sillon as HTMLElement).queryByText(/%/)).toBeNull();
  });

  it('una pre-reserva que no ocupa agenda figura con 0 %', async () => {
    const ocupacion: Ocupacion = {
      desde: HOY,
      hasta: HOY,
      sillones: [
        {
          sillon_id: 2,
          nombre: 'Sillón 1',
          estado: 'activo',
          dias: [{ dia: HOY, minutos_ocupados: 0, minutos_atencion: 240, porcentaje: '0.00', turnos: 0, minutos_perdidos: 0 }],
        },
      ],
    };
    await montar(apiFalsa({ ocupacion: vi.fn().mockResolvedValue(ocupacion) }));
    expect(await screen.findByText(/0 % ocupado/)).toBeInTheDocument();
  });

  it('el ausentismo muestra la tasa y lo recuperado en pesos', async () => {
    await montar();
    const bloque = (await screen.findByRole('heading', { name: 'Ausentismo' })).closest('section') as HTMLElement;
    expect(within(bloque).getByText(/Tasa de ausentismo: 25 %/)).toBeInTheDocument();
    expect(within(bloque).getByText(/1 ausente de 4 turnos marcados/)).toBeInTheDocument();
    expect(within(bloque).getByText(/Señas retenidas: \$ 3\.000,00 \(1 seña\)/)).toBeInTheDocument();
    expect(within(bloque).getByText(/2 turnos sin marcar/)).toBeInTheDocument();
    expect(within(bloque).getByText('Dra. Ana Ficticia')).toBeInTheDocument();
  });

  it('sin turnos marcados no inventa una tasa', async () => {
    const vacio = { ...AUSENTISMO, atendidos: 0, ausentes: 0, tasa: null, sin_marcar: 0, por_profesional: [], recupero: { senas_retenidas: 0, importe_retenido: '0.00', porcentaje: null } };
    await montar(apiFalsa({ ausentismo: vi.fn().mockResolvedValue(vacio) }));
    expect(await screen.findByText('Sin turnos marcados en este período')).toBeInTheDocument();
    expect(screen.queryByText(/Tasa de ausentismo/)).toBeNull();
  });

  it('si falla el ausentismo se ve la ocupación y un reintento solo en su bloque', async () => {
    const api = apiFalsa({
      ausentismo: vi.fn().mockRejectedValueOnce(new Error('caído')).mockResolvedValue(AUSENTISMO),
    });
    await montar(api);
    expect(await screen.findByText('Sillón 1')).toBeInTheDocument();
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('No pudimos cargar el ausentismo');
    expect(api.ocupacion).toHaveBeenCalledTimes(1);
    await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText(/Tasa de ausentismo/)).toBeInTheDocument();
    expect(api.ocupacion).toHaveBeenCalledTimes(1);
    expect(api.ausentismo).toHaveBeenCalledTimes(2);
  });

  it('si falla la ocupación se ve el ausentismo y un reintento solo en su bloque', async () => {
    const api = apiFalsa({
      ocupacion: vi.fn().mockRejectedValueOnce(new Error('caído')).mockResolvedValue(OCUPACION),
    });
    await montar(api);
    expect(await screen.findByText(/Tasa de ausentismo/)).toBeInTheDocument();
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('No pudimos cargar la ocupación');
    await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Sillón 1')).toBeInTheDocument();
  });

  it('cambiar el período vuelve a pedir las dos cosas, juntas, con el rango nuevo', async () => {
    const api = await montar();
    await screen.findByText('Sillón 1');
    await usuario.click(screen.getByRole('button', { name: 'Esta semana' }));
    await waitFor(() => {
      expect(api.ocupacion).toHaveBeenLastCalledWith('2031-11-17', '2031-11-23');
    });
    expect(api.ausentismo).toHaveBeenLastCalledWith('2031-11-17', '2031-11-23');
    await usuario.click(screen.getByRole('button', { name: 'Últimos 30 días' }));
    await waitFor(() => {
      expect(api.ocupacion).toHaveBeenLastCalledWith('2031-10-20', HOY);
    });
    expect(api.ausentismo).toHaveBeenLastCalledWith('2031-10-20', HOY);
    expect(screen.getByRole('button', { name: 'Últimos 30 días' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('con varios días muestra el resumen del período y el detalle por día', async () => {
    const ocupacion: Ocupacion = {
      desde: '2031-11-17',
      hasta: '2031-11-18',
      sillones: [
        {
          sillon_id: 2,
          nombre: 'Sillón 1',
          estado: 'activo',
          dias: [
            { dia: '2031-11-17', minutos_ocupados: 60, minutos_atencion: 240, porcentaje: '25.00', turnos: 2, minutos_perdidos: 0 },
            { dia: '2031-11-18', minutos_ocupados: 120, minutos_atencion: 240, porcentaje: '50.00', turnos: 4, minutos_perdidos: 0 },
          ],
        },
      ],
    };
    const api = apiFalsa({ ocupacion: vi.fn().mockResolvedValue(ocupacion) });
    await montar(api);
    await usuario.click(screen.getByRole('button', { name: 'Esta semana' }));
    const sillon = (await screen.findByText('Sillón 1')).closest('section') as HTMLElement;
    expect(within(sillon).getByText(/37,5 % ocupado/)).toBeInTheDocument();
    expect(within(sillon).getByText(/180 de 480 minutos/)).toBeInTheDocument();
    expect(within(sillon).getByText('Detalle por día')).toBeInTheDocument();
  });
});
