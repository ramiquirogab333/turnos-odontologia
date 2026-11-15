import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import { apiFalsa } from '../test/datos';
import { LoteOdontograma } from './LoteOdontograma';
import type { AvisoCambios } from './useCambiosPendientes';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  select: (el: Element, v: string) => act(() => base.selectOptions(el, v)),
};

function montar(sobre: Partial<Api> = {}, pieza: number | null = 16) {
  const api = apiFalsa(sobre);
  const alRegistrar = vi.fn<() => void>();
  const alVencer = vi.fn<() => void>();
  const registrar = vi.fn<(a: AvisoCambios | null) => void>();
  const ui = (p: number | null) => (
    <LoteOdontograma api={api} pacienteId={7} pieza={p} onRegistrado={alRegistrar} onAccesoVencido={alVencer} registrarCambios={registrar} />
  );
  const { rerender } = render(ui(pieza));
  return { api, alRegistrar, alVencer, registrar, cambiarPieza: (p: number | null) => { rerender(ui(p)); } };
}

async function agregar(estado: string, cara?: string): Promise<void> {
  await usuario.select(screen.getByLabelText('Estado'), estado);
  if (cara !== undefined) await usuario.select(screen.getByLabelText('Cara'), cara);
  await usuario.click(screen.getByRole('button', { name: 'Agregar al lote' }));
}

describe('Registro de hallazgos en lote', () => {
  it('arma un lote de dos hallazgos y los registra con un solo pedido', async () => {
    const { api, alRegistrar, cambiarPieza } = montar();
    await agregar('Caries', 'oclusal');
    cambiarPieza(36);
    await agregar('Endodoncia');
    const lote = screen.getByRole('list', { name: 'Lote de hallazgos' });
    expect(within(lote).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      expect.stringContaining('16 · O · Caries'),
      expect.stringContaining('36 · Endodoncia'),
    ]);
    await usuario.click(screen.getByRole('button', { name: 'Registrar 2 hallazgos' }));
    expect(api.registrarOdontograma).toHaveBeenCalledTimes(1);
    expect(api.registrarOdontograma).toHaveBeenCalledWith(7, [
      { pieza: 16, cara: 'O', estado: 'caries', nota: null },
      { pieza: 36, cara: null, estado: 'endodoncia', nota: null },
    ]);
    expect(await screen.findByText('Registramos 2 hallazgos')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Lote de hallazgos' })).toBeNull();
    expect(alRegistrar).toHaveBeenCalledTimes(1);
  });

  it('caries sin cara deshabilita «Agregar al lote» y pide la cara; con una cara se habilita', async () => {
    montar();
    await usuario.select(screen.getByLabelText('Estado'), 'Caries');
    expect(screen.getByRole('button', { name: 'Agregar al lote' })).toBeDisabled();
    expect(screen.getByText('Elegí la cara afectada')).toBeInTheDocument();
    await usuario.select(screen.getByLabelText('Cara'), 'mesial');
    expect(screen.getByRole('button', { name: 'Agregar al lote' })).toBeEnabled();
  });

  it('los estados de pieza no ofrecen el selector de cara y sano lo ofrece como opcional', async () => {
    montar();
    await usuario.select(screen.getByLabelText('Estado'), 'Corona');
    expect(screen.queryByLabelText('Cara')).toBeNull();
    await usuario.select(screen.getByLabelText('Estado'), 'Sano');
    expect(screen.getByLabelText('Cara')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Agregar al lote' })).toBeEnabled();
  });

  it('sin pieza elegida pide elegirla en la grilla', () => {
    montar({}, null);
    expect(screen.getByText('Elegí una pieza en la grilla')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Agregar al lote' })).toBeDisabled();
  });

  it('«Quitar» saca un hallazgo del lote', async () => {
    montar();
    await agregar('Caries', 'oclusal');
    await usuario.click(screen.getByRole('button', { name: 'Quitar 16 · O · Caries' }));
    expect(screen.queryByRole('list', { name: 'Lote de hallazgos' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Registrar/ })).toBeNull();
  });

  it('agrega la nota de hasta 500 caracteres', async () => {
    const { api } = montar();
    fireEvent.change(screen.getByLabelText('Nota (opcional)'), { target: { value: 'Mancha (sintético)' } });
    expect(screen.getByLabelText('Nota (opcional)')).toHaveAttribute('maxlength', '500');
    await agregar('Caries', 'oclusal');
    await usuario.click(screen.getByRole('button', { name: 'Registrar 1 hallazgo' }));
    expect(api.registrarOdontograma).toHaveBeenCalledWith(7, [{ pieza: 16, cara: 'O', estado: 'caries', nota: 'Mancha (sintético)' }]);
  });

  it('un lote en el tope de 64 no crece: avisa y «Registrar 64 hallazgos» los envía todos en un solo pedido', async () => {
    const { api } = montar();
    await usuario.select(screen.getByLabelText('Estado'), 'Caries');
    await usuario.select(screen.getByLabelText('Cara'), 'oclusal');
    for (let i = 0; i < 64; i += 1) {
      fireEvent.change(screen.getByLabelText('Nota (opcional)'), { target: { value: `n${String(i)}` } });
      fireEvent.click(screen.getByRole('button', { name: 'Agregar al lote' }));
    }
    expect(within(screen.getByRole('list', { name: 'Lote de hallazgos' })).getAllByRole('listitem')).toHaveLength(64);
    fireEvent.change(screen.getByLabelText('Nota (opcional)'), { target: { value: 'otra' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar al lote' }));
    expect(screen.getByText('Un lote admite hasta 64 hallazgos: registrá estos primero')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Lote de hallazgos' })).getAllByRole('listitem')).toHaveLength(64);
    await usuario.click(screen.getByRole('button', { name: 'Registrar 64 hallazgos' }));
    expect(api.registrarOdontograma).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.registrarOdontograma).mock.calls[0]?.[1]).toHaveLength(64);
  });
});

describe('El registro es solo de alta', () => {
  it('no ofrece editar ni borrar un hallazgo registrado y dice cómo corregir', () => {
    montar();
    expect(screen.queryByRole('button', { name: /Editar|Borrar|Eliminar/ })).toBeNull();
    expect(screen.getByText(/Para corregir un hallazgo, registrá uno nuevo/)).toBeInTheDocument();
  });

  it('con acceso vencido (403) explica, conserva el lote y avisa al detalle', async () => {
    const registrarOdontograma = vi.fn<Api['registrarOdontograma']>().mockResolvedValue({ ok: false, error: { tipo: 'acceso_vencido' } });
    const { alRegistrar, alVencer, cambiarPieza } = montar({ registrarOdontograma });
    await agregar('Caries', 'oclusal');
    cambiarPieza(36);
    await agregar('Endodoncia');
    cambiarPieza(46);
    await agregar('Corona');
    await usuario.click(screen.getByRole('button', { name: 'Registrar 3 hallazgos' }));
    expect(await screen.findByText('Tu acceso para editar venció. Para editar, pedí un turno a recepción')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Lote de hallazgos' })).getAllByRole('listitem')).toHaveLength(3);
    expect(alRegistrar).not.toHaveBeenCalled();
    expect(alVencer).toHaveBeenCalledTimes(1);
  });

  it('un error de red conserva el lote para reintentar', async () => {
    const registrarOdontograma = vi.fn<Api['registrarOdontograma']>().mockResolvedValue({ ok: false, error: { tipo: 'desconocido' } });
    montar({ registrarOdontograma });
    await agregar('Caries', 'oclusal');
    await usuario.click(screen.getByRole('button', { name: 'Registrar 1 hallazgo' }));
    expect(await screen.findByText(/No pudimos registrar los hallazgos/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registrar 1 hallazgo' })).toBeEnabled();
  });

  it('avisa los hallazgos sin registrar y nunca guarda el lote en el navegador', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const { registrar } = montar();
    expect(registrar).toHaveBeenLastCalledWith(null);
    await agregar('Caries', 'oclusal');
    expect(registrar).toHaveBeenLastCalledWith({ mensaje: 'Tenés 1 hallazgo sin registrar', seguir: 'Seguir', descartar: 'Descartar' });
    await agregar('Sano');
    expect(registrar).toHaveBeenLastCalledWith({ mensaje: 'Tenés 2 hallazgos sin registrar', seguir: 'Seguir', descartar: 'Descartar' });
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });

  it('un doble toque en «Registrar» envía un solo pedido', async () => {
    let resolver: () => void = () => undefined;
    const registrarOdontograma = vi.fn<Api['registrarOdontograma']>(() => new Promise((r) => { resolver = () => { r({ ok: true, valor: [] }); }; }));
    montar({ registrarOdontograma });
    await agregar('Caries', 'oclusal');
    await usuario.click(screen.getByRole('button', { name: 'Registrar 1 hallazgo' }));
    await usuario.click(screen.getByRole('button', { name: 'Registrando…' }));
    expect(registrarOdontograma).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolver();
      await Promise.resolve();
    });
  });
});
