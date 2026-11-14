import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ErrorApiPanel } from '../lib/api';
import type { PestanaCatalogo } from '../lib/ruta';
import type { CatalogoAdmin } from '../lib/tipos';
import { apiFalsa, catalogoAdmin } from '../test/datos';
import { Catalogo } from './Catalogo';

const base = userEvent.setup();
const tocar = (el: Element) => act(() => base.click(el));

async function montar(api = apiFalsa(), pestanaInicial?: PestanaCatalogo) {
  await act(async () => {
    render(<Catalogo api={api} {...(pestanaInicial === undefined ? {} : { pestanaInicial })} />);
    await Promise.resolve();
  });
  return api;
}

describe('Catalogo', () => {
  it('pide el catálogo una sola vez, antes de que responda, y abre Tratamientos con sus datos', async () => {
    const api = apiFalsa({ catalogo: vi.fn(() => new Promise<CatalogoAdmin>(() => undefined)) });
    await montar(api);
    expect(api.catalogo).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent('Cargando el catálogo…');
  });

  it('muestra las cuatro pestañas con Tratamientos abierta', async () => {
    await montar();
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Tratamientos', 'Profesionales', 'Sillones', 'Horarios']);
    expect(screen.getByRole('tab', { name: 'Tratamientos' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('Limpieza dental')).toBeInTheDocument();
  });

  it('cambia de pestaña sin volver a pedir el catálogo', async () => {
    const api = await montar();
    await tocar(screen.getByRole('tab', { name: 'Sillones' }));
    expect(screen.getByRole('tab', { name: 'Sillones' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('Sillón 2')).toBeInTheDocument();
    expect(api.catalogo).toHaveBeenCalledTimes(1);
  });

  it('abre la pestaña indicada por el hash', async () => {
    await montar(apiFalsa(), 'horarios');
    expect(screen.getByRole('tab', { name: 'Horarios' })).toHaveAttribute('aria-selected', 'true');
  });

  it('si falla la carga dice "No pudimos cargar el catálogo", ofrece reintentar y no muestra ninguna lista', async () => {
    const api = apiFalsa({
      catalogo: vi.fn().mockRejectedValueOnce(new ErrorApiPanel(500, 'boom', null)).mockResolvedValue(catalogoAdmin()),
    });
    await montar(api);
    expect(screen.getByRole('alert')).toHaveTextContent('No pudimos cargar el catálogo');
    expect(screen.queryByRole('tab')).toBeNull();
    expect(screen.queryByText('Limpieza dental')).toBeNull();
    await tocar(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Limpieza dental')).toBeInTheDocument();
    expect(api.catalogo).toHaveBeenCalledTimes(2);
  });
});
