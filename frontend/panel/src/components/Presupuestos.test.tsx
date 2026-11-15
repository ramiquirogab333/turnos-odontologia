import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { CualquierPresupuesto } from '../lib/tipos';
import { ACCESO_COMPLETO, apiFalsa, lineaPresupuesto, pacienteClinico, pacienteDetalle, pagoPresupuesto, presupuesto, presupuestoClinico } from '../test/datos';
import { Presupuestos } from './Presupuestos';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

const ACEPTADO = presupuesto({ id: 9 });
const BORRADOR = presupuesto({ id: 10, estado: 'borrador', pagos: [], total_pagado: '0.00', saldo: '2500.00', created_at: '2031-11-19T09:00:00-03:00' });

function montar(opciones: { datos?: readonly CualquierPresupuesto[]; gestiona?: boolean; clinica?: boolean; api?: Partial<Api> } = {}) {
  const api = apiFalsa(opciones.api);
  const alReemplazar = vi.fn<(l: readonly CualquierPresupuesto[]) => void>();
  render(
    <Presupuestos
      api={api}
      paciente={opciones.clinica === true ? pacienteClinico({ acceso_clinico: ACCESO_COMPLETO }) : pacienteDetalle()}
      datos={opciones.datos ?? [ACEPTADO, BORRADOR]}
      puedeGestionar={opciones.gestiona ?? true}
      onActualizar={() => undefined}
      onReemplazar={alReemplazar}
      registrarCambios={() => undefined}
    />,
  );
  return { api, alReemplazar };
}

describe('Lista de presupuestos por rol', () => {
  it('recepción ve el aceptado con «Pagado $ 1.000 · Saldo $ 1.500» y el borrador con «Editar»', () => {
    montar();
    const tarjetas = screen.getAllByRole('article');
    expect(tarjetas).toHaveLength(2);
    // más reciente primero: el borrador del 19/11 antes que el aceptado del 18/11
    expect(within(tarjetas[0] as HTMLElement).getByText('Borrador')).toBeInTheDocument();
    expect(within(tarjetas[0] as HTMLElement).getByRole('button', { name: 'Editar' })).toBeInTheDocument();
    expect(within(tarjetas[1] as HTMLElement).getByText('Aceptado')).toBeInTheDocument();
    expect(within(tarjetas[1] as HTMLElement).getByText('Pagado $ 1.000 · Saldo $ 1.500')).toBeInTheDocument();
    expect(within(tarjetas[1] as HTMLElement).getByText('A cargo del paciente $ 2.500')).toBeInTheDocument();
    expect(within(tarjetas[1] as HTMLElement).getByText('Swiss Medical')).toBeInTheDocument();
  });

  it('la odontóloga ve líneas e importes pero ni pagos, ni saldo, ni botones de acción en ningún lugar', () => {
    montar({ datos: [presupuestoClinico(), presupuestoClinico({ id: 10, estado: 'borrador' })], gestiona: false, clinica: true });
    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect(screen.getAllByText('Limpieza dental').length).toBeGreaterThan(0);
    expect(screen.getAllByText('A cargo del paciente $ 2.500').length).toBe(2);
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Actualizar']);
    expect(document.body.textContent).not.toMatch(/Pagado|Saldo|cobro|Cobro/);
  });

  it('un paciente sin presupuestos dice que no hay y ofrece «Nuevo presupuesto»', () => {
    montar({ datos: [] });
    expect(screen.getByText('Este paciente todavía no tiene presupuestos')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Nuevo presupuesto' })).toBeInTheDocument();
  });

  it('sin permiso de gestión el vacío no ofrece «Nuevo presupuesto»', () => {
    montar({ datos: [], gestiona: false, clinica: true });
    expect(screen.queryByRole('button', { name: 'Nuevo presupuesto' })).toBeNull();
  });

  it('cada línea muestra los importes tal como los dio el servidor y la nota de «sin cobertura»', () => {
    const sin = lineaPresupuesto({ id: 2, orden: 2, tratamiento: { id: 4, nombre: 'Corona' }, importe_bruto: '9999999999.99', importe_cobertura: '0.00', importe_paciente: '9999999999.99', sin_cobertura: true });
    montar({ datos: [presupuesto({ lineas: [lineaPresupuesto(), sin] })] });
    expect(screen.getByText('Sin cobertura para esta prestación')).toBeInTheDocument();
    expect(screen.getAllByText('$ 9.999.999.999,99').length).toBeGreaterThan(0);
    expect(screen.getByText('$ 22.500')).toBeInTheDocument();
  });
});

describe('Presupuesto presentado de solo lectura', () => {
  it('un presupuesto presentado muestra sus líneas congeladas sin «Editar»', () => {
    montar({ datos: [presupuesto({ estado: 'presentado', pagos: [], total_pagado: '0.00' })] });
    expect(screen.getByText('Presentado')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Editar' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Aceptar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rechazar' })).toBeInTheDocument();
  });

  it('rechazado y anulado no ofrecen ninguna acción', () => {
    montar({ datos: [presupuesto({ id: 1, estado: 'rechazado', pagos: [] }), presupuesto({ id: 2, estado: 'anulado', pagos: [], anulado_motivo: 'Error (sintético)' })] });
    expect(screen.getAllByRole('button').map((b) => b.textContent).filter((n) => n !== 'Nuevo presupuesto')).toEqual(['Actualizar']);
    expect(screen.getByText(/Error \(sintético\)/)).toBeInTheDocument();
  });
});

describe('Estados del presupuesto desde el panel', () => {
  it('presentar avisa que los importes quedan fijos, confirma y luego aceptar confirma también', async () => {
    const presentado = presupuesto({ id: 10, estado: 'presentado', pagos: [], total_pagado: '0.00', saldo: '2500.00' });
    const transicionar = vi.fn<Api['transicionarPresupuesto']>().mockResolvedValueOnce({ ok: true, valor: presentado }).mockResolvedValueOnce({ ok: true, valor: { ...presentado, estado: 'aceptado' } });
    const { api } = montar({ datos: [BORRADOR], api: { transicionarPresupuesto: transicionar } });
    await usuario.click(screen.getByRole('button', { name: 'Presentar' }));
    const dialogo = screen.getByRole('dialog');
    expect(within(dialogo).getByText('Los importes quedan fijos desde ahora')).toBeInTheDocument();
    await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, presentar' }));
    expect(api.transicionarPresupuesto).toHaveBeenCalledWith(7, 10, 'presentar');
    expect(await screen.findByText('Presentado')).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Aceptar' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, aceptar' }));
    expect(api.transicionarPresupuesto).toHaveBeenLastCalledWith(7, 10, 'aceptar');
    expect(await screen.findByText('Aceptado')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registrar cobro' })).toBeInTheDocument();
  });

  it('anular un aceptado con cobros muestra el 409 explicado y el presupuesto sigue aceptado', async () => {
    const anularPresupuesto = vi.fn<Api['anularPresupuesto']>().mockResolvedValue({ ok: false, error: { tipo: 'presupuesto_con_pagos' } });
    montar({ datos: [ACEPTADO], api: { anularPresupuesto } });
    await usuario.click(screen.getByRole('button', { name: 'Anular' }));
    const dialogo = screen.getByRole('dialog');
    const confirmar = within(dialogo).getByRole('button', { name: 'Anular presupuesto' });
    expect(confirmar).toBeDisabled();
    await usuario.type(within(dialogo).getByLabelText('Motivo'), 'Error de carga (sintético)');
    await usuario.click(confirmar);
    expect(anularPresupuesto).toHaveBeenCalledWith(7, 9, 'Error de carga (sintético)');
    expect(await within(screen.getByRole('dialog')).findByText('No se puede anular un presupuesto con cobros registrados. Anulá antes los cobros')).toBeInTheDocument();
    expect(screen.getByText('Aceptado')).toBeInTheDocument();
  });

  it('si otra persona cambió el estado (409 transicion_invalida) avisa y la lista se actualiza', async () => {
    const presentado = presupuesto({ id: 10, estado: 'presentado', pagos: [], total_pagado: '0.00' });
    const transicionar = vi.fn<Api['transicionarPresupuesto']>().mockResolvedValue({ ok: false, error: { tipo: 'transicion_invalida' } });
    const lista = vi.fn<Api['presupuestos']>().mockResolvedValue([{ ...presentado, estado: 'rechazado' }]);
    const { alReemplazar } = montar({ datos: [presentado], api: { transicionarPresupuesto: transicionar, presupuestos: lista } });
    await usuario.click(screen.getByRole('button', { name: 'Aceptar' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, aceptar' }));
    expect(await screen.findByText('El presupuesto cambió de estado mientras lo mirabas')).toBeInTheDocument();
    expect(await screen.findByText('Rechazado')).toBeInTheDocument();
    expect(lista).toHaveBeenCalledWith(7);
    expect(alReemplazar).toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('Pagos y cobros en la lista', () => {
  it('un cobro anulado sigue visible con su motivo', () => {
    const anulado = pagoPresupuesto({ id: 6, estado: 'anulado', anulado_motivo: 'Monto equivocado (sintético)' });
    montar({ datos: [presupuesto({ pagos: [pagoPresupuesto(), anulado] })] });
    expect(screen.getByText(/Anulado · Monto equivocado \(sintético\)/)).toBeInTheDocument();
  });
});
