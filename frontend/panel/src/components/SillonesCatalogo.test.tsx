import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { CatalogoAdmin } from '../lib/tipos';
import { apiFalsa, catalogoAdmin, sillonAdmin } from '../test/datos';
import { SillonesCatalogo } from './SillonesCatalogo';

const base = userEvent.setup();
const tocar = (el: Element) => act(() => base.click(el));
const elegir = (el: Element, valor: string) => act(() => base.selectOptions(el, valor));
const escribir = async (el: Element, texto: string) => {
  await act(() => base.clear(el));
  await act(() => base.type(el, texto));
};

function Envoltorio({ api, inicial }: { readonly api: Api; readonly inicial: CatalogoAdmin }) {
  const [datos, setDatos] = useState(inicial);
  const [aviso, setAviso] = useState('');
  return (
    <>
      <p data-testid="aviso">{aviso}</p>
      <SillonesCatalogo api={api} datos={datos} cambiar={setDatos} avisar={setAviso} />
    </>
  );
}

async function montar(api: Api, datos: CatalogoAdmin = catalogoAdmin()) {
  await act(async () => {
    render(<Envoltorio api={api} inicial={datos} />);
    await Promise.resolve();
  });
}

const fila = (nombre: string) => screen.getByText(nombre).closest('li') as HTMLElement;

describe('SillonesCatalogo', () => {
  it('lista el estado como texto: Disponible, En mantenimiento y Fuera de uso', async () => {
    const datos = catalogoAdmin({
      sillones: [sillonAdmin(), sillonAdmin({ id: 5, nombre: 'Sillón 2', estado: 'mantenimiento' }), sillonAdmin({ id: 6, nombre: 'Sillón 3', estado: 'inactivo' })],
    });
    await montar(apiFalsa(), datos);
    expect(within(fila('Sillón 1')).getByText('Disponible')).toBeInTheDocument();
    expect(within(fila('Sillón 2')).getByText('En mantenimiento')).toBeInTheDocument();
    expect(within(fila('Sillón 2')).getByText('No se ofrece para reservar')).toBeInTheDocument();
    expect(within(fila('Sillón 3')).getByText('Fuera de uso')).toBeInTheDocument();
    expect(within(fila('Sillón 1')).queryByText('No se ofrece para reservar')).toBeNull();
  });

  it('poner un sillón en mantenimiento pide confirmar con el impacto y guarda el estado', async () => {
    const api = apiFalsa({
      impactoCatalogo: vi.fn().mockResolvedValue({ turnos_futuros: 1, primero: '2031-11-18T09:00:00-03:00' }),
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: sillonAdmin({ id: 5, nombre: 'Sillón 2', estado: 'mantenimiento' }) }),
    });
    await montar(api);
    await tocar(within(fila('Sillón 2')).getByRole('button', { name: 'Editar' }));
    await elegir(screen.getByLabelText('Estado'), 'mantenimiento');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(api.actualizarCatalogo).not.toHaveBeenCalled();
    expect(await screen.findByText('Hay 1 turno tomado en este sillón. No se cancela: sigue en la agenda.')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmar cambio' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('sillones', 5, { nombre: 'Sillón 2', estado: 'mantenimiento' });
    expect(within(fila('Sillón 2')).getByText('En mantenimiento')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renombrar sin cambiar el estado guarda directo, sin diálogo', async () => {
    const api = apiFalsa({ actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: sillonAdmin({ id: 5, nombre: 'Sillón 2B' }) }) });
    await montar(api);
    await tocar(within(fila('Sillón 2')).getByRole('button', { name: 'Editar' }));
    await escribir(screen.getByLabelText('Nombre'), 'Sillón 2B');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(api.impactoCatalogo).not.toHaveBeenCalled();
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('sillones', 5, { nombre: 'Sillón 2B', estado: 'activo' });
    expect(screen.getByText('Sillón 2B')).toBeInTheDocument();
  });

  it('volver a "Disponible" un sillón en mantenimiento no pide confirmación', async () => {
    const api = apiFalsa({ actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: sillonAdmin({ id: 5, nombre: 'Sillón 2' }) }) });
    await montar(api, catalogoAdmin({ sillones: [sillonAdmin({ id: 5, nombre: 'Sillón 2', estado: 'mantenimiento' })] }));
    await tocar(screen.getByRole('button', { name: 'Editar' }));
    await elegir(screen.getByLabelText('Estado'), 'activo');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(api.impactoCatalogo).not.toHaveBeenCalled();
    expect(within(fila('Sillón 2')).getByText('Disponible')).toBeInTheDocument();
  });

  it('agrega un sillón y un nombre repetido se muestra en el campo', async () => {
    const api = apiFalsa({ crearCatalogo: vi.fn().mockResolvedValue({ ok: false, error: { tipo: 'duplicado', campo: 'nombre' } }) });
    await montar(api);
    await tocar(screen.getByRole('button', { name: 'Agregar sillón' }));
    await escribir(screen.getByLabelText('Nombre'), 'sillón 1');
    await tocar(screen.getByRole('button', { name: 'Guardar sillón' }));
    expect(screen.getByText('Ya hay un sillón con ese nombre')).toBeInTheDocument();
    expect(screen.getByLabelText('Nombre')).toHaveValue('sillón 1');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('borrar un sillón sin uso lo saca; en uso explica el 409', async () => {
    const api = apiFalsa({
      borrarCatalogo: vi.fn().mockResolvedValueOnce({ ok: true, valor: null }).mockResolvedValueOnce({ ok: false, error: { tipo: 'en_uso' } }),
    });
    await montar(api);
    await tocar(within(fila('Sillón 2')).getByRole('button', { name: 'Borrar' }));
    await tocar(await screen.findByRole('button', { name: 'Borrar sillón' }));
    expect(screen.queryByText('Sillón 2')).toBeNull();
    await tocar(within(fila('Sillón 1')).getByRole('button', { name: 'Borrar' }));
    await tocar(await screen.findByRole('button', { name: 'Borrar sillón' }));
    expect(screen.getByRole('alert')).toHaveTextContent('No se puede borrar porque tiene turnos registrados');
    expect(fila('Sillón 1')).toBeInTheDocument();
  });
});
