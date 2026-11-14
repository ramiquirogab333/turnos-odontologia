import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { CatalogoAdmin, ErrorCatalogo, TratamientoAdmin } from '../lib/tipos';
import { apiFalsa, catalogoAdmin, tratamientoAdmin } from '../test/datos';
import { TratamientosCatalogo } from './TratamientosCatalogo';

const base = userEvent.setup();
const tocar = (el: Element) => act(() => base.click(el));
const escribir = async (el: Element, texto: string) => {
  await act(() => base.clear(el));
  if (texto !== '') await act(() => base.type(el, texto));
};

function Envoltorio({ api, inicial }: { readonly api: Api; readonly inicial: CatalogoAdmin }) {
  const [datos, setDatos] = useState(inicial);
  const [aviso, setAviso] = useState('');
  return (
    <>
      <p data-testid="aviso">{aviso}</p>
      <TratamientosCatalogo api={api} datos={datos} cambiar={setDatos} avisar={setAviso} />
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

describe('TratamientosCatalogo: lista', () => {
  it('muestra nombre, duración, precio y estado como texto; los inactivos atenuados y los de precio 0 con "Sin seña"', async () => {
    const datos = catalogoAdmin({
      tratamientos: [
        tratamientoAdmin(),
        tratamientoAdmin({ id: 7, nombre: 'Ortodoncia demo', activo: false }),
        tratamientoAdmin({ id: 8, nombre: 'Control de prueba', precio_base: '0.00' }),
      ],
    });
    await montar(apiFalsa(), datos);
    const limpieza = fila('Limpieza dental');
    expect(within(limpieza).getByText('45 min')).toBeInTheDocument();
    expect(within(limpieza).getByText('$ 18.500')).toBeInTheDocument();
    expect(within(limpieza).getByText('Activo')).toBeInTheDocument();
    const inactivo = fila('Ortodoncia demo');
    expect(within(inactivo).getByText('Inactivo')).toBeInTheDocument();
    expect(within(inactivo).getByText('No se ofrece para reservar')).toBeInTheDocument();
    expect(within(fila('Control de prueba')).getByText('Sin seña')).toBeInTheDocument();
    expect(within(limpieza).queryByText('Sin seña')).toBeNull();
  });

  it('un catálogo vacío invita a cargar el primero', async () => {
    await montar(apiFalsa(), catalogoAdmin({ tratamientos: [] }));
    expect(screen.getByText(/Todavía no cargaste ningún tratamiento/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Agregar tratamiento' })).toBeInTheDocument();
  });
});

describe('TratamientosCatalogo: editar', () => {
  it('cambiar la duración guarda solo lo que cambió, actualiza la lista y confirma "Guardamos los cambios"', async () => {
    const api = apiFalsa({
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: tratamientoAdmin({ duracion_minutos: 60 }) }),
    });
    await montar(api);
    await tocar(within(fila('Limpieza dental')).getByRole('button', { name: 'Editar' }));
    expect(screen.getByText(/La duración y el precio nuevos valen solo para los turnos que se tomen desde ahora/)).toBeInTheDocument();
    await escribir(screen.getByLabelText('Duración (minutos)'), '60');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('tratamientos', 3, { nombre: 'Limpieza dental', duracion_minutos: 60, precio_base: '18500.00' });
    expect(within(fila('Limpieza dental')).getByText('60 min')).toBeInTheDocument();
    expect(screen.getByTestId('aviso')).toHaveTextContent('Guardamos los cambios');
    expect(screen.queryByLabelText('Duración (minutos)')).toBeNull();
  });

  it('una duración de 7 minutos muestra el error junto al campo, conserva lo escrito y no pide nada', async () => {
    const api = apiFalsa();
    await montar(api);
    await tocar(within(fila('Limpieza dental')).getByRole('button', { name: 'Editar' }));
    await escribir(screen.getByLabelText('Duración (minutos)'), '7');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(screen.getByText('La duración va de 5 a 480 minutos, en múltiplos de 5')).toBeInTheDocument();
    expect(screen.getByLabelText('Duración (minutos)')).toHaveValue(7);
    expect(screen.getByLabelText('Duración (minutos)')).toHaveAttribute('aria-invalid', 'true');
    expect(api.actualizarCatalogo).not.toHaveBeenCalled();
  });

  it('un rechazo del servidor se muestra y no pierde lo escrito', async () => {
    const error: ErrorCatalogo = { tipo: 'duplicado', campo: 'nombre' };
    const api = apiFalsa({ actualizarCatalogo: vi.fn().mockResolvedValue({ ok: false, error }) });
    await montar(api);
    await tocar(within(fila('Limpieza dental')).getByRole('button', { name: 'Editar' }));
    await escribir(screen.getByLabelText('Nombre'), 'Empaste');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(screen.getByText('Ya hay un tratamiento con ese nombre')).toBeInTheDocument();
    expect(screen.getByLabelText('Nombre')).toHaveValue('Empaste');
  });
});

describe('TratamientosCatalogo: agregar', () => {
  it('con precio 0 avisa antes de guardar que no pedirá seña y la fila nueva muestra "Sin seña"', async () => {
    const nuevo = tratamientoAdmin({ id: 9, nombre: 'Control de prueba', duracion_minutos: 15, precio_base: '0.00' });
    const api = apiFalsa({ crearCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: nuevo }) });
    await montar(api);
    await tocar(screen.getByRole('button', { name: 'Agregar tratamiento' }));
    await escribir(screen.getByLabelText('Nombre'), 'Control de prueba');
    await escribir(screen.getByLabelText('Duración (minutos)'), '15');
    await escribir(screen.getByLabelText('Precio (pesos)'), '0');
    expect(screen.getByText('Los turnos de este tratamiento no pedirán seña.')).toBeInTheDocument();
    await tocar(screen.getByRole('button', { name: 'Guardar tratamiento' }));
    expect(api.crearCatalogo).toHaveBeenCalledWith('tratamientos', { nombre: 'Control de prueba', duracion_minutos: 15, precio_base: '0.00' });
    expect(within(fila('Control de prueba')).getByText('Sin seña')).toBeInTheDocument();
  });

  it('un doble toque en guardar sale como un solo pedido', async () => {
    let resolver: (v: { ok: true; valor: TratamientoAdmin }) => void = () => undefined;
    const api = apiFalsa({
      crearCatalogo: vi.fn(
        () =>
          new Promise((r) => {
            resolver = r;
          }),
      ) as unknown as Api['crearCatalogo'],
    });
    await montar(api, catalogoAdmin({ tratamientos: [] }));
    await tocar(screen.getByRole('button', { name: 'Agregar tratamiento' }));
    await escribir(screen.getByLabelText('Nombre'), 'Control de prueba');
    await escribir(screen.getByLabelText('Duración (minutos)'), '15');
    await escribir(screen.getByLabelText('Precio (pesos)'), '5000');
    const guardar = screen.getByRole('button', { name: 'Guardar tratamiento' });
    await act(async () => {
      await base.dblClick(guardar);
    });
    expect(api.crearCatalogo).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled();
    await act(async () => {
      resolver({ ok: true, valor: tratamientoAdmin({ id: 9, nombre: 'Control de prueba' }) });
      await Promise.resolve();
    });
    expect(screen.getAllByText('Control de prueba')).toHaveLength(1);
  });
});

describe('TratamientosCatalogo: desactivar y borrar', () => {
  it('desactivar pide confirmación con el impacto y, al confirmar, guarda activo=false', async () => {
    const api = apiFalsa({
      impactoCatalogo: vi.fn().mockResolvedValue({ turnos_futuros: 2, primero: '2031-11-18T09:00:00-03:00' }),
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: tratamientoAdmin({ activo: false }) }),
    });
    await montar(api);
    await tocar(within(fila('Limpieza dental')).getByRole('button', { name: 'Desactivar' }));
    expect(await screen.findByText('Hay 2 turnos tomados en este tratamiento. No se cancelan: siguen en la agenda.')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Desactivar' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('tratamientos', 3, { activo: false });
    expect(within(fila('Limpieza dental')).getByText('Inactivo')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('reactivar no pide confirmación y guarda activo=true', async () => {
    const api = apiFalsa({ actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: tratamientoAdmin({ activo: true }) }) });
    await montar(api, catalogoAdmin({ tratamientos: [tratamientoAdmin({ activo: false })] }));
    await tocar(screen.getByRole('button', { name: 'Reactivar' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('tratamientos', 3, { activo: true });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(within(fila('Limpieza dental')).getByText('Activo')).toBeInTheDocument();
  });

  it('borrar un tratamiento usado explica el 409, ofrece "Desactivar" y deja el tratamiento en la lista', async () => {
    const api = apiFalsa({
      borrarCatalogo: vi.fn().mockResolvedValue({ ok: false, error: { tipo: 'en_uso' } }),
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: tratamientoAdmin({ activo: false }) }),
    });
    await montar(api);
    await tocar(within(fila('Limpieza dental')).getByRole('button', { name: 'Borrar' }));
    await tocar(await screen.findByRole('button', { name: 'Borrar tratamiento' }));
    expect(screen.getByRole('alert')).toHaveTextContent('No se puede borrar porque tiene turnos registrados');
    expect(fila('Limpieza dental')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Desactivar' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('tratamientos', 3, { activo: false });
    expect(within(fila('Limpieza dental')).getByText('Inactivo')).toBeInTheDocument();
  });

  it('borrar un tratamiento sin uso lo saca de la lista', async () => {
    const api = apiFalsa();
    await montar(api);
    await tocar(within(fila('Empaste')).getByRole('button', { name: 'Borrar' }));
    await tocar(await screen.findByRole('button', { name: 'Borrar tratamiento' }));
    expect(api.borrarCatalogo).toHaveBeenCalledWith('tratamientos', 6);
    expect(screen.queryByText('Empaste')).toBeNull();
  });
});
