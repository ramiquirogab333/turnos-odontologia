import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { CajaDia, Pendiente } from '../lib/tipos';
import { apiFalsa, caja, CAJA_VACIA, pendiente } from '../test/datos';
import { Caja } from './Caja';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

const HOY = '2031-11-18';

async function montar(api = apiFalsa(), esAdmin = false) {
  await act(async () => {
    render(<Caja api={api} hoy={HOY} esAdmin={esAdmin} />);
    await Promise.resolve();
  });
  return api;
}

describe('Pantalla de caja', () => {
  it('el resumen y los pendientes se piden juntos: ninguno espera al otro (R2)', async () => {
    let resolverCaja: (v: CajaDia) => void = () => undefined;
    let resolverPendientes: (v: readonly Pendiente[]) => void = () => undefined;
    const api = apiFalsa({
      caja: vi.fn(() => new Promise<CajaDia>((res) => { resolverCaja = res; })),
      pendientes: vi.fn(() => new Promise<readonly Pendiente[]>((res) => { resolverPendientes = res; })),
    });
    await montar(api);
    expect(api.caja).toHaveBeenCalledTimes(1);
    expect(api.pendientes).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolverCaja(caja());
      resolverPendientes([]);
      await Promise.resolve();
    });
    expect(await screen.findByText('Total del día: $ 3.000,00')).toBeInTheDocument();
  });

  it('abre en el día de hoy', async () => {
    const api = await montar();
    expect(api.caja).toHaveBeenCalledWith(HOY);
  });

  it('muestra el total del día y la línea de señas por Mercado Pago', async () => {
    await montar();
    const resumen = await screen.findByRole('region', { name: 'Resumen de la caja' });
    expect(within(resumen).getByText('Total del día: $ 3.000,00')).toBeInTheDocument();
    expect(within(resumen).getByText(/Ingresos \$ 3\.000,00/)).toBeInTheDocument();
    expect(within(resumen).getByText(/Egresos \$ 0,00/)).toBeInTheDocument();
    expect(within(resumen).getByText('Señas por Mercado Pago: $ 3.000,00 (1)')).toBeInTheDocument();
  });

  it('una devolución se ve como egreso y resta del total', async () => {
    const conEgreso = caja({
      lineas: [
        { concepto: 'sena', medio: 'mercadopago', cantidad: 2, total: '6000.00' },
        { concepto: 'devolucion_sena', medio: 'transferencia', cantidad: 1, total: '3000.00' },
      ],
      total_ingresos: '6000.00',
      total_egresos: '3000.00',
      total_neto: '3000.00',
    });
    await montar(apiFalsa({ caja: vi.fn().mockResolvedValue(conEgreso) }));
    const resumen = await screen.findByRole('region', { name: 'Resumen de la caja' });
    expect(within(resumen).getByText('Devoluciones de señas por transferencia: $ 3.000,00 (1)')).toBeInTheDocument();
    expect(within(resumen).getByText(/Egresos \$ 3\.000,00/)).toBeInTheDocument();
    expect(within(resumen).getByText('Total del día: $ 3.000,00')).toBeInTheDocument();
  });

  it('las señas retenidas por ausencia se muestran aparte, sin restarlas', async () => {
    const conRetenida = caja({ senas_retenidas: { cantidad: 1, total: '4500.00' } });
    await montar(apiFalsa({ caja: vi.fn().mockResolvedValue(conRetenida) }));
    expect(await screen.findByText('Señas retenidas por ausencia: $ 4.500,00 (1 seña)')).toBeInTheDocument();
  });

  it('sin señas retenidas no muestra esa línea', async () => {
    await montar();
    await screen.findByText('Total del día: $ 3.000,00');
    expect(screen.queryByText(/retenidas por ausencia/)).toBeNull();
  });

  it('un día sin movimientos lo dice con palabras y no muestra importes', async () => {
    await montar(apiFalsa({ caja: vi.fn().mockResolvedValue(CAJA_VACIA) }));
    expect(await screen.findByText('No hubo movimientos este día')).toBeInTheDocument();
  });

  it('lista los movimientos del día con hora, concepto, medio y referencia', async () => {
    const conReferencia = caja({
      movimientos: [
        { concepto: 'devolucion_sena', medio: 'transferencia', importe: '3000.00', hora: '2031-11-18T10:30:00-03:00', referencia: 'DEV-SINT-0001', turno_id: 4, presupuesto_id: null },
      ],
    });
    await montar(apiFalsa({ caja: vi.fn().mockResolvedValue(conReferencia) }));
    const lista = await screen.findByRole('list', { name: 'Movimientos del día' });
    expect(within(lista).getByText(/10:30/)).toBeInTheDocument();
    expect(within(lista).getByText(/DEV-SINT-0001/)).toBeInTheDocument();
    expect(within(lista).getByText(/Devolución de seña/)).toBeInTheDocument();
  });

  it('cambiar de día pide solo la caja de ese día y no recarga la página', async () => {
    const api = await montar();
    await screen.findByText('Total del día: $ 3.000,00');
    await usuario.click(screen.getByRole('button', { name: 'Día anterior' }));
    await waitFor(() => {
      expect(api.caja).toHaveBeenLastCalledWith('2031-11-17');
    });
    expect(api.pendientes).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('heading', { level: 2, name: /17 de noviembre/ })).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Hoy' }));
    await waitFor(() => {
      expect(api.caja).toHaveBeenLastCalledWith(HOY);
    });
  });

  it('no deja pasar a un día que todavía no llegó', async () => {
    await montar();
    await screen.findByText('Total del día: $ 3.000,00');
    expect(screen.getByRole('button', { name: 'Día siguiente' })).toBeDisabled();
  });

  it('indica si el día está abierto o cerrado', async () => {
    await montar(apiFalsa({ caja: vi.fn().mockResolvedValue(caja({ estado: 'cerrado', cierre_id: 3 })) }));
    expect(await screen.findByText('Caja cerrada')).toBeInTheDocument();
  });

  it('si falla la carga muestra un error con reintento y ningún importe a medias', async () => {
    const api = apiFalsa({ caja: vi.fn().mockRejectedValueOnce(new Error('caído')).mockResolvedValue(caja()) });
    await montar(api);
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('No pudimos cargar la caja');
    expect(screen.queryByText(/\$/)).toBeNull();
    await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Total del día: $ 3.000,00')).toBeInTheDocument();
    expect(api.pendientes).toHaveBeenCalledTimes(2);
  });

  it('si fallan los pendientes tampoco muestra el resumen suelto', async () => {
    const api = apiFalsa({ pendientes: vi.fn().mockRejectedValueOnce(new Error('caído')).mockResolvedValue([]) });
    await montar(api);
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar la caja');
    expect(screen.queryByText(/Total del día/)).toBeNull();
  });

  it('muestra los pagos por resolver y los refresca cuando se resuelve uno', async () => {
    const api = apiFalsa({
      pendientes: vi.fn().mockResolvedValueOnce([pendiente()]).mockResolvedValue([]),
    });
    await montar(api);
    const seccion = await screen.findByRole('region', { name: 'Pagos por resolver' });
    await usuario.click(within(seccion).getByRole('button', { name: 'Rechazar' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, rechazar el pago' }));
    expect(await screen.findByText('No hay pagos por resolver')).toBeInTheDocument();
    expect(api.caja).toHaveBeenCalledTimes(2);
  });
});
