import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { Presupuesto } from '../lib/tipos';
import { apiFalsa, pagoPresupuesto, presupuesto } from '../test/datos';
import { CobrosPresupuesto } from './CobrosPresupuesto';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
  clear: (el: Element) => act(() => base.clear(el)),
};

const SIN_COBROS = presupuesto({ pagos: [], total_pagado: '0.00', saldo: '2500.00' });

function Arnes({ api, inicial, alCambiar }: { api: Api; inicial: Presupuesto; alCambiar: (p: Presupuesto) => void }) {
  const [p, setP] = useState(inicial);
  return (
    <CobrosPresupuesto
      api={api}
      pacienteId={7}
      presupuesto={p}
      puedeRegistrar
      hoy="2031-11-18"
      onCambio={(nuevo) => {
        setP(nuevo);
        alCambiar(nuevo);
      }}
    />
  );
}

function montar(inicial: Presupuesto = SIN_COBROS, sobre: Partial<Api> = {}) {
  const api = apiFalsa(sobre);
  const alCambiar = vi.fn<(p: Presupuesto) => void>();
  render(<Arnes api={api} inicial={inicial} alCambiar={alCambiar} />);
  return { api, alCambiar };
}

describe('Registro de cobros de un presupuesto aceptado', () => {
  it('un cobro parcial por transferencia con referencia actualiza la lista, lo pagado y el saldo', async () => {
    const registrar = vi.fn<Api['registrarCobro']>().mockResolvedValue({ ok: true, valor: { pago: pagoPresupuesto(), total_pagado: '1000.00', saldo: '1500.00' } });
    montar(SIN_COBROS, { registrarCobro: registrar });
    expect(screen.getByLabelText('Monto')).toHaveValue('2500.00');
    await usuario.clear(screen.getByLabelText('Monto'));
    await usuario.type(screen.getByLabelText('Monto'), '1000');
    await usuario.type(screen.getByLabelText('Referencia (opcional)'), 'TRF-0001');
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    expect(registrar).toHaveBeenCalledWith(7, 9, { medio: 'transferencia', monto: '1000.00', referencia: 'TRF-0001' });
    expect(await screen.findByText('Pagado $ 1.000 · Saldo $ 1.500')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Cobros' })).getByText(/TRF-0001/)).toBeInTheDocument();
    expect(screen.getByLabelText('Monto')).toHaveValue('1500.00');
  });

  it('el medio se elige con dos botones y Mercado Pago viaja como mercadopago', async () => {
    const { api } = montar();
    await usuario.click(screen.getByRole('button', { name: 'Mercado Pago' }));
    expect(screen.getByRole('button', { name: 'Mercado Pago' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Transferencia' })).toHaveAttribute('aria-pressed', 'false');
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    expect(api.registrarCobro).toHaveBeenCalledWith(7, 9, { medio: 'mercadopago', monto: '2500.00', referencia: null });
  });

  it('monto_excede_saldo muestra el saldo actual, lo toma como monto sugerido y no registra nada', async () => {
    const registrar = vi.fn<Api['registrarCobro']>().mockResolvedValue({ ok: false, error: { tipo: 'monto_excede_saldo', saldo: '500.00' } });
    const { alCambiar } = montar(presupuesto({ pagos: [pagoPresupuesto()], total_pagado: '1000.00', saldo: '1500.00' }), { registrarCobro: registrar });
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    expect(await screen.findByText('El monto supera el saldo. El saldo actual es $ 500')).toBeInTheDocument();
    expect(screen.getByLabelText('Monto')).toHaveValue('500.00');
    expect(screen.getByText('Pagado $ 2.000 · Saldo $ 500')).toBeInTheDocument();
    expect(alCambiar).toHaveBeenCalledWith(expect.objectContaining({ saldo: '500.00', total_pagado: '2000.00' }));
    expect(within(screen.getByRole('list', { name: 'Cobros' })).getAllByRole('listitem')).toHaveLength(1);
  });

  it('caja_cerrada se explica y referencia_duplicada aparece junto al campo', async () => {
    const registrar = vi.fn<Api['registrarCobro']>()
      .mockResolvedValueOnce({ ok: false, error: { tipo: 'caja_cerrada' } })
      .mockResolvedValueOnce({ ok: false, error: { tipo: 'referencia_duplicada' } });
    montar(SIN_COBROS, { registrarCobro: registrar });
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    expect(await screen.findByText('La caja de ese día está cerrada. Un admin tiene que anular el cierre para registrar este cobro')).toBeInTheDocument();
    await usuario.type(screen.getByLabelText('Referencia (opcional)'), 'TRF-0001');
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    const campo = screen.getByLabelText('Referencia (opcional)');
    expect(await screen.findByText('Ya hay un cobro registrado con esa referencia')).toBeInTheDocument();
    expect(campo).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByRole('list', { name: 'Cobros' })).toBeNull();
  });

  it('un monto en cero o mayor que el saldo se corrige sin enviar', async () => {
    const { api } = montar();
    await usuario.clear(screen.getByLabelText('Monto'));
    await usuario.type(screen.getByLabelText('Monto'), '0');
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    expect(screen.getByText('El monto tiene que ser mayor que 0')).toBeInTheDocument();
    await usuario.clear(screen.getByLabelText('Monto'));
    await usuario.type(screen.getByLabelText('Monto'), '2500,01');
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    expect(screen.getByText('El monto supera el saldo. El saldo actual es $ 2.500')).toBeInTheDocument();
    expect(api.registrarCobro).not.toHaveBeenCalled();
  });

  it('la fecha de cobro no puede ser futura y un día pasado viaja como las 12:00 de la clínica', async () => {
    const { api } = montar();
    const fecha = screen.getByLabelText('Fecha de cobro');
    expect(fecha).toHaveValue('2031-11-18');
    expect(fecha).toHaveAttribute('max', '2031-11-18');
    fireEvent.change(fecha, { target: { value: '2031-11-17' } });
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    expect(api.registrarCobro).toHaveBeenCalledWith(7, 9, { medio: 'transferencia', monto: '2500.00', fecha_cobro: '2031-11-17T12:00:00-03:00', referencia: null });
  });

  it('un doble toque envía un solo pedido', async () => {
    let resolver: () => void = () => undefined;
    const registrar = vi.fn<Api['registrarCobro']>(() => new Promise((r) => { resolver = () => { r({ ok: true, valor: { pago: pagoPresupuesto(), total_pagado: '2500.00', saldo: '0.00' } }); }; }));
    montar(SIN_COBROS, { registrarCobro: registrar });
    await usuario.click(screen.getByRole('button', { name: 'Registrar cobro' }));
    await usuario.click(screen.getByRole('button', { name: 'Registrando…' }));
    expect(registrar).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolver();
      await Promise.resolve();
    });
  });
});

describe('Anulación de cobros', () => {
  const CON_COBRO = presupuesto({ pagos: [pagoPresupuesto({ monto: '1000.00' })], total_pagado: '1000.00', saldo: '1500.00' });

  it('anular con motivo deja el cobro visible como «Anulado» con su motivo y el saldo vuelve a sumar', async () => {
    const anulado = pagoPresupuesto({ estado: 'anulado', anulado_motivo: 'Monto equivocado (sintético)' });
    const anular = vi.fn<Api['anularCobro']>().mockResolvedValue({ ok: true, valor: { pago: anulado, total_pagado: '0.00', saldo: '2500.00' } });
    montar(CON_COBRO, { anularCobro: anular });
    await usuario.click(screen.getByRole('button', { name: 'Anular cobro' }));
    const dialogo = screen.getByRole('dialog');
    await usuario.type(within(dialogo).getByLabelText('Motivo'), 'Monto equivocado (sintético)');
    await usuario.click(within(dialogo).getByRole('button', { name: 'Anular cobro' }));
    expect(anular).toHaveBeenCalledWith(7, 9, 5, 'Monto equivocado (sintético)');
    expect(await screen.findByText(/Anulado · Monto equivocado \(sintético\)/)).toBeInTheDocument();
    expect(screen.getByText('Pagado $ 0 · Saldo $ 2.500')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Anular cobro' })).toBeNull();
  });

  it('un cobro de un día cerrado (409 caja_cerrada) explica y sigue registrado', async () => {
    const anular = vi.fn<Api['anularCobro']>().mockResolvedValue({ ok: false, error: { tipo: 'caja_cerrada' } });
    montar(CON_COBRO, { anularCobro: anular });
    await usuario.click(screen.getByRole('button', { name: 'Anular cobro' }));
    const dialogo = screen.getByRole('dialog');
    await usuario.type(within(dialogo).getByLabelText('Motivo'), 'Error de carga (sintético)');
    await usuario.click(within(dialogo).getByRole('button', { name: 'Anular cobro' }));
    expect(await within(screen.getByRole('dialog')).findByText('La caja de ese día está cerrada. Un admin tiene que anular el cierre para registrar este cobro')).toBeInTheDocument();
    expect(screen.getByText('Pagado $ 1.000 · Saldo $ 1.500')).toBeInTheDocument();
  });

  it('un motivo de «ok» deshabilita «Anular cobro» y dice cuánto falta', async () => {
    const { api } = montar(CON_COBRO);
    await usuario.click(screen.getByRole('button', { name: 'Anular cobro' }));
    const dialogo = screen.getByRole('dialog');
    await usuario.type(within(dialogo).getByLabelText('Motivo'), 'ok');
    expect(within(dialogo).getByRole('button', { name: 'Anular cobro' })).toBeDisabled();
    expect(within(dialogo).getByText('Escribí al menos 3 caracteres')).toBeInTheDocument();
    expect(api.anularCobro).not.toHaveBeenCalled();
  });

  it('nunca ofrece borrar un cobro', () => {
    montar(CON_COBRO);
    expect(screen.queryByRole('button', { name: /Borrar|Eliminar/ })).toBeNull();
  });
});
