import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { Presupuesto } from '../lib/tipos';
import { apiFalsa, lineaPresupuesto, OPCIONES, OPCIONES_CON_INACTIVOS, pacienteDetalle, presupuesto } from '../test/datos';
import { FormPresupuesto } from './FormPresupuesto';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  select: (el: Element, v: string) => act(() => base.selectOptions(el, v)),
};

const GUARDADO = presupuesto({ id: 10, estado: 'borrador', pagos: [], total_pagado: '0.00', saldo: '2500.00' });

async function montar(opciones: { existente?: Presupuesto | null; api?: Partial<Api> } = {}) {
  const api = apiFalsa(opciones.api);
  const alGuardar = vi.fn<(p: Presupuesto) => void>();
  const alRecargar = vi.fn<() => void>();
  const alCancelar = vi.fn<() => void>();
  await act(async () => {
    render(<FormPresupuesto api={api} paciente={pacienteDetalle()} existente={opciones.existente ?? null} onGuardado={alGuardar} onRecargar={alRecargar} onCancelar={alCancelar} />);
    await Promise.resolve();
  });
  await screen.findByRole('button', { name: 'Agregar línea' });
  return { api, alGuardar, alRecargar, alCancelar };
}

async function agregarLinea(tratamiento = 'Limpieza dental'): Promise<void> {
  await usuario.click(screen.getByRole('button', { name: 'Agregar línea' }));
  const lineas = screen.getAllByRole('group', { name: /^Línea/ });
  const ultima = lineas[lineas.length - 1] as HTMLElement;
  await usuario.select(within(ultima).getByLabelText('Tratamiento'), tratamiento);
}

describe('Armado de un presupuesto en borrador', () => {
  it('pide los tratamientos y las obras sociales a la vez al abrir (R2)', async () => {
    const resolvers: (() => void)[] = [];
    const opciones = vi.fn<Api['opciones']>(() => new Promise((r) => resolvers.push(() => { r(OPCIONES); })));
    const obras = vi.fn<Api['obrasSociales']>(() => new Promise((r) => resolvers.push(() => { r([{ id: 2, nombre: 'Swiss Medical' }]); })));
    const api = apiFalsa({ opciones, obrasSociales: obras });
    await act(async () => {
      render(<FormPresupuesto api={api} paciente={pacienteDetalle()} existente={null} onGuardado={() => undefined} onRecargar={() => undefined} onCancelar={() => undefined} />);
      await Promise.resolve();
    });
    expect(opciones).toHaveBeenCalledTimes(1);
    expect(obras).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolvers.forEach((r) => { r(); });
      await Promise.resolve();
    });
    expect(await screen.findByRole('button', { name: 'Agregar línea' })).toBeInTheDocument();
  });

  it('guarda el borrador omitiendo la obra social (usa la del paciente) y muestra los importes que devolvió el servidor', async () => {
    const crear = vi.fn<Api['crearPresupuesto']>().mockResolvedValue({ ok: true, valor: { ...GUARDADO, lineas: [lineaPresupuesto({ importe_bruto: '25000.00', importe_cobertura: '22500.00', importe_paciente: '2500.00' })] } });
    const { api, alGuardar } = await montar({ api: { crearPresupuesto: crear } });
    expect(screen.getByText('Guardá el borrador para ver los importes')).toBeInTheDocument();
    await agregarLinea();
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(api.crearPresupuesto).toHaveBeenCalledWith(7, { lineas: [{ tratamiento_id: 3, cantidad: 1, pieza: null, cara: null }], notas: '' });
    expect(await screen.findByText('Borrador guardado')).toBeInTheDocument();
    expect(screen.getByText('$ 25.000')).toBeInTheDocument();
    expect(screen.getByText('$ 22.500')).toBeInTheDocument();
    expect(screen.getByText('$ 2.500')).toBeInTheDocument();
    expect(screen.queryByText('Guardá el borrador para ver los importes')).toBeNull();
    expect(alGuardar).toHaveBeenCalledTimes(1);
  });

  it('«Sin obra social» envía null y otra obra social envía su id; el cuerpo lleva pieza, cara, cantidad y notas', async () => {
    const { api } = await montar();
    await usuario.select(screen.getByLabelText('Obra social'), 'Sin obra social');
    await agregarLinea('Empaste');
    const linea = screen.getByRole('group', { name: /^Línea/ });
    fireEvent.change(within(linea).getByLabelText('Cantidad'), { target: { value: '2' } });
    fireEvent.change(within(linea).getByLabelText('Pieza (opcional)'), { target: { value: '16' } });
    await usuario.select(within(linea).getByLabelText('Cara (opcional)'), 'oclusal');
    fireEvent.change(screen.getByLabelText('Notas'), { target: { value: 'Urgente (sintético)' } });
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(api.crearPresupuesto).toHaveBeenLastCalledWith(7, {
      lineas: [{ tratamiento_id: 6, cantidad: 2, pieza: 16, cara: 'O' }],
      obra_social_id: null,
      notas: 'Urgente (sintético)',
    });
    await usuario.select(screen.getByLabelText('Obra social'), 'Swiss Medical');
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(api.crearPresupuesto).toHaveBeenLastCalledWith(7, expect.objectContaining({ obra_social_id: 2 }));
  });

  it('una obra social desactivada (422) avisa, vuelve a pedir la lista y conserva lo cargado', async () => {
    const crear = vi.fn<Api['crearPresupuesto']>().mockResolvedValue({ ok: false, error: { tipo: 'obra_social_inactiva' } });
    const { api } = await montar({ api: { crearPresupuesto: crear } });
    await agregarLinea();
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(await screen.findByText('Esa obra social ya no está activa. Elegí otra o «Sin obra social»')).toBeInTheDocument();
    expect(api.obrasSociales).toHaveBeenCalledTimes(2);
    expect(within(screen.getByRole('group', { name: /^Línea/ })).getByLabelText('Tratamiento')).toHaveValue('3');
  });

  it('sin líneas o con una cantidad inválida no envía y señala el error', async () => {
    const { api } = await montar();
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(screen.getByText('Agregá al menos una línea')).toBeInTheDocument();
    await agregarLinea();
    fireEvent.change(within(screen.getByRole('group', { name: /^Línea/ })).getByLabelText('Cantidad'), { target: { value: '100' } });
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(screen.getByText('La cantidad va de 1 a 99')).toBeInTheDocument();
    expect(api.crearPresupuesto).not.toHaveBeenCalled();
  });

  it('la cara exige la pieza', async () => {
    const { api } = await montar();
    await agregarLinea();
    await usuario.select(within(screen.getByRole('group', { name: /^Línea/ })).getByLabelText('Cara (opcional)'), 'mesial');
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(screen.getByText('La cara exige indicar la pieza')).toBeInTheDocument();
    expect(api.crearPresupuesto).not.toHaveBeenCalled();
  });

  it('una línea de un tratamiento inactivo en un borrador existente muestra «(inactivo)» y el selector de líneas nuevas no lo ofrece', async () => {
    const existente = presupuesto({ id: 10, estado: 'borrador', pagos: [], lineas: [lineaPresupuesto({ tratamiento: { id: 8, nombre: 'Ortodoncia demo' } })] });
    await montar({ existente, api: { opciones: vi.fn<Api['opciones']>().mockResolvedValue(OPCIONES_CON_INACTIVOS) } });
    const selectorExistente = within(screen.getByRole('group', { name: /^Línea 1/ })).getByLabelText('Tratamiento');
    expect(within(selectorExistente).getByRole('option', { name: 'Ortodoncia demo (inactivo)' })).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Agregar línea' }));
    const nueva = within(screen.getByRole('group', { name: /^Línea 2/ })).getByLabelText('Tratamiento');
    expect(within(nueva).queryByRole('option', { name: /Ortodoncia demo/ })).toBeNull();
  });

  it('al editar un borrador usa PUT con lo precargado y, si ya se presentó (409), avisa, recarga y no envía más', async () => {
    const existente = presupuesto({ id: 10, estado: 'borrador', pagos: [], notas: 'Previa (sintético)' });
    const editar = vi.fn<Api['editarPresupuesto']>().mockResolvedValue({ ok: false, error: { tipo: 'presupuesto_no_editable' } });
    const { api, alRecargar } = await montar({ existente, api: { editarPresupuesto: editar } });
    expect(screen.getByLabelText('Notas')).toHaveValue('Previa (sintético)');
    expect(within(screen.getByRole('group', { name: /^Línea 1/ })).getByLabelText('Tratamiento')).toHaveValue('3');
    await usuario.click(screen.getByRole('button', { name: 'Guardar borrador' }));
    expect(api.editarPresupuesto).toHaveBeenCalledWith(7, 10, { lineas: [{ tratamiento_id: 3, cantidad: 1, pieza: null, cara: null }], obra_social_id: 2, notas: 'Previa (sintético)' });
    expect(await screen.findByText('Este presupuesto ya fue presentado y no se puede editar')).toBeInTheDocument();
    expect(alRecargar).toHaveBeenCalledTimes(1);
  });

  it('«Quitar» saca una línea y «Cancelar» cierra el formulario', async () => {
    const { alCancelar } = await montar();
    await agregarLinea();
    await usuario.click(screen.getByRole('button', { name: 'Quitar línea 1' }));
    expect(screen.queryByRole('group', { name: /^Línea/ })).toBeNull();
    await usuario.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(alCancelar).toHaveBeenCalledTimes(1);
  });
});
