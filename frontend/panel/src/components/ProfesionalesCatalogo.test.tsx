import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ErrorApiPanel } from '../lib/api';
import type { Api } from '../lib/api';
import type { CatalogoAdmin } from '../lib/tipos';
import { apiFalsa, catalogoAdmin, profesionalAdmin } from '../test/datos';
import { ProfesionalesCatalogo } from './ProfesionalesCatalogo';

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
      <ProfesionalesCatalogo api={api} datos={datos} cambiar={setDatos} avisar={setAviso} />
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

describe('ProfesionalesCatalogo', () => {
  it('lista nombre, especialidad, matrícula y estado; sin especialidad lo dice en lugar de dejar un espacio vacío', async () => {
    const datos = catalogoAdmin({
      profesionales: [profesionalAdmin(), profesionalAdmin({ id: 2, nombre: 'Dr. Juan Ejemplo', matricula: 'MP-99002', especialidad: '', activo: false })],
    });
    await montar(apiFalsa(), datos);
    const ana = fila('Dra. Ana Ficticia');
    expect(within(ana).getByText('Odontología general')).toBeInTheDocument();
    expect(within(ana).getByText('Matrícula MP-99001')).toBeInTheDocument();
    expect(within(ana).getByText('Activo')).toBeInTheDocument();
    const juan = fila('Dr. Juan Ejemplo');
    expect(within(juan).getByText('Sin especialidad')).toBeInTheDocument();
    expect(within(juan).getByText('Inactivo')).toBeInTheDocument();
    expect(within(juan).getByText('No se ofrece para reservar')).toBeInTheDocument();
  });

  it('agrega una profesional sin especialidad y la lista muestra "Sin especialidad"', async () => {
    const nuevo = profesionalAdmin({ id: 2, nombre: 'Dr. Juan Ejemplo', matricula: 'MP-99002', especialidad: '' });
    const api = apiFalsa({ crearCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: nuevo }) });
    await montar(api);
    await tocar(screen.getByRole('button', { name: 'Agregar profesional' }));
    await escribir(screen.getByLabelText('Nombre'), 'Dr. Juan Ejemplo');
    await escribir(screen.getByLabelText('Matrícula'), 'MP-99002');
    await tocar(screen.getByRole('button', { name: 'Guardar profesional' }));
    expect(api.crearCatalogo).toHaveBeenCalledWith('profesionales', { nombre: 'Dr. Juan Ejemplo', matricula: 'MP-99002', especialidad: '' });
    expect(within(fila('Dr. Juan Ejemplo')).getByText('Sin especialidad')).toBeInTheDocument();
    expect(screen.getByTestId('aviso')).toHaveTextContent('Guardamos los cambios');
  });

  it('una matrícula repetida se muestra en el campo, no crea a nadie y conserva lo escrito', async () => {
    const api = apiFalsa({ crearCatalogo: vi.fn().mockResolvedValue({ ok: false, error: { tipo: 'duplicado', campo: 'matricula' } }) });
    await montar(api);
    await tocar(screen.getByRole('button', { name: 'Agregar profesional' }));
    await escribir(screen.getByLabelText('Nombre'), 'Dr. Juan Ejemplo');
    await escribir(screen.getByLabelText('Matrícula'), 'mp-99001');
    await tocar(screen.getByRole('button', { name: 'Guardar profesional' }));
    expect(screen.getByText('Ya hay una profesional con esa matrícula')).toBeInTheDocument();
    expect(screen.getByLabelText('Matrícula')).toHaveValue('mp-99001');
    expect(screen.queryByText('Dr. Juan Ejemplo', { selector: 'p' })).toBeNull();
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('nombre y matrícula vacíos se piden junto a cada campo sin llamar al servidor', async () => {
    const api = apiFalsa();
    await montar(api);
    await tocar(screen.getByRole('button', { name: 'Agregar profesional' }));
    await tocar(screen.getByRole('button', { name: 'Guardar profesional' }));
    expect(screen.getByText('Ingresá el nombre.')).toBeInTheDocument();
    expect(screen.getByText('Ingresá la matrícula.')).toBeInTheDocument();
    expect(api.crearCatalogo).not.toHaveBeenCalled();
  });

  it('desactivar muestra el impacto y, al confirmar, guarda activo=false', async () => {
    const api = apiFalsa({
      impactoCatalogo: vi.fn().mockResolvedValue({ turnos_futuros: 2, primero: '2031-11-18T09:00:00-03:00' }),
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: profesionalAdmin({ activo: false }) }),
    });
    await montar(api);
    await tocar(within(fila('Dra. Ana Ficticia')).getByRole('button', { name: 'Desactivar' }));
    expect(await screen.findByText('Hay 2 turnos tomados con esta profesional. No se cancelan: siguen en la agenda.')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Desactivar' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('profesionales', 1, { activo: false });
    expect(within(fila('Dra. Ana Ficticia')).getByText('Inactivo')).toBeInTheDocument();
  });

  it('si no se pudo consultar el impacto lo dice y permite desactivar igual', async () => {
    const api = apiFalsa({
      impactoCatalogo: vi.fn().mockRejectedValue(new ErrorApiPanel(0, 'sin red', null)),
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: profesionalAdmin({ activo: false }) }),
    });
    await montar(api);
    await tocar(within(fila('Dra. Ana Ficticia')).getByRole('button', { name: 'Desactivar' }));
    expect(await screen.findByText('No pudimos revisar los turnos tomados; los turnos existentes no se cancelan igual.')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Desactivar' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledTimes(1);
  });

  it('reactivar guarda activo=true sin confirmación', async () => {
    const api = apiFalsa({ actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: profesionalAdmin({ activo: true }) }) });
    await montar(api, catalogoAdmin({ profesionales: [profesionalAdmin({ activo: false })] }));
    await tocar(screen.getByRole('button', { name: 'Reactivar' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('profesionales', 1, { activo: true });
    expect(within(fila('Dra. Ana Ficticia')).getByText('Activo')).toBeInTheDocument();
  });

  it('borrar una profesional con turnos registrados explica el 409 y ofrece desactivar', async () => {
    const api = apiFalsa({
      borrarCatalogo: vi.fn().mockResolvedValue({ ok: false, error: { tipo: 'en_uso' } }),
    });
    await montar(api);
    await tocar(within(fila('Dra. Ana Ficticia')).getByRole('button', { name: 'Borrar' }));
    await tocar(await screen.findByRole('button', { name: 'Borrar profesional' }));
    expect(screen.getByRole('alert')).toHaveTextContent('No se puede borrar porque tiene turnos registrados');
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Desactivar' })).toBeInTheDocument();
    expect(fila('Dra. Ana Ficticia')).toBeInTheDocument();
  });
});
