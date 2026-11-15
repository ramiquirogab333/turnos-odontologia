import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ErrorApiPanel, type Api } from '../lib/api';
import type { PestanaPaciente } from '../lib/ruta';
import type { PacienteDetalle, Rol } from '../lib/tipos';
import { ACCESO_LECTURA, apiFalsa, pacienteClinico, pacienteDetalle } from '../test/datos';
import { DetallePaciente } from './DetallePaciente';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

async function montar(api: Api, roles: readonly Rol[] = ['recepcion'], pestana: PestanaPaciente = 'ficha') {
  await act(async () => {
    render(<DetallePaciente api={api} roles={roles} pacienteId={7} pestanaInicial={pestana} />);
    await Promise.resolve();
  });
}

afterEach(() => {
  window.history.replaceState(null, '', '#/');
});

describe('Detalle del paciente por ruta según el rol', () => {
  it('recepción ve la cabecera y las pestañas Ficha, Odontograma, Presupuestos y Datos, con Ficha abierta', async () => {
    const api = apiFalsa();
    await montar(api);
    expect(await screen.findByRole('heading', { level: 2, name: 'Lucía Ejemplo' })).toBeInTheDocument();
    const pestanas = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(pestanas).toEqual(['Ficha', 'Odontograma', 'Presupuestos', 'Datos']);
    expect(screen.getByRole('tab', { name: 'Ficha' })).toHaveAttribute('aria-selected', 'true');
    expect(api.ficha).toHaveBeenCalledWith(7);
  });

  it('la odontóloga ve a una paciente suya sin la pestaña Datos', async () => {
    await montar(apiFalsa({ paciente: vi.fn<Api['paciente']>().mockResolvedValue(pacienteClinico()) }), ['odontologo']);
    await screen.findByRole('heading', { level: 2, name: 'Lucía Ejemplo' });
    expect(screen.queryByRole('tab', { name: 'Datos' })).toBeNull();
    expect(screen.getAllByRole('tab')).toHaveLength(3);
  });

  it('la odontóloga con un enlace directo a Datos abre la ficha', async () => {
    const api = apiFalsa({ paciente: vi.fn<Api['paciente']>().mockResolvedValue(pacienteClinico()) });
    await montar(api, ['odontologo'], 'datos');
    await screen.findByRole('heading', { level: 2, name: 'Lucía Ejemplo' });
    expect(screen.getByRole('tab', { name: 'Ficha' })).toHaveAttribute('aria-selected', 'true');
    expect(api.ficha).toHaveBeenCalled();
  });

  it('la odontóloga ante una paciente ajena ve el mensaje de falta de acceso con el enlace a la agenda y ningún dato', async () => {
    const paciente = vi.fn<Api['paciente']>().mockRejectedValue(new ErrorApiPanel(403, 'ajena', 'paciente_ajeno'));
    await montar(apiFalsa({ paciente }), ['odontologo']);
    expect(await screen.findByText('No tenés acceso a esta paciente: el acceso empieza cuando un turno con vos se marca atendido')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Volver a la agenda' })).toHaveAttribute('href', '#/agenda');
    expect(screen.queryByText('Lucía Ejemplo')).toBeNull();
    expect(screen.queryByRole('tab')).toBeNull();
  });

  it('un paciente inexistente dice «No encontramos ese paciente» con el enlace a Pacientes', async () => {
    const paciente = vi.fn<Api['paciente']>().mockRejectedValue(new ErrorApiPanel(404, 'no existe', null));
    await montar(apiFalsa({ paciente }));
    expect(await screen.findByText('No encontramos ese paciente')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ir a Pacientes' })).toHaveAttribute('href', '#/pacientes');
  });
});

describe('Cabecera del paciente según el rol', () => {
  it('recepción ve los cinco datos y el teléfono', async () => {
    await montar(apiFalsa());
    const cabecera = (await screen.findByRole('heading', { level: 2, name: 'Lucía Ejemplo' })).closest('header') as HTMLElement;
    expect(within(cabecera).getByText(/DNI 99000001/)).toBeInTheDocument();
    expect(within(cabecera).getByText(/Swiss Medical · SM-0001/)).toBeInTheDocument();
    expect(within(cabecera).getByText('+5491100000001')).toBeInTheDocument();
  });

  it('la odontóloga no ve teléfono ni email en ningún lugar de la página', async () => {
    const paciente = pacienteClinico({ email: null });
    await montar(apiFalsa({ paciente: vi.fn<Api['paciente']>().mockResolvedValue(paciente) }), ['odontologo']);
    await screen.findByRole('heading', { level: 2, name: 'Lucía Ejemplo' });
    expect(screen.getByText(/DNI 99000001/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('+549');
    expect(document.body.textContent).not.toContain('@');
  });

  it('con acceso de solo lectura la cabecera lo dice y explica cómo recuperar la escritura', async () => {
    const paciente: PacienteDetalle = pacienteClinico({ acceso_clinico: ACCESO_LECTURA });
    await montar(apiFalsa({ paciente: vi.fn<Api['paciente']>().mockResolvedValue(paciente) }), ['odontologo']);
    expect(
      await screen.findByText('Solo lectura: tu última atención con esta paciente fue hace más de 12 meses. Para editar, pedí un turno a recepción'),
    ).toBeInTheDocument();
  });
});

describe('Carga del detalle sin cascadas', () => {
  it('pide el paciente y el odontograma a la vez y no pide la ficha ni los presupuestos', async () => {
    const resolvers: (() => void)[] = [];
    const paciente = vi.fn<Api['paciente']>(() => new Promise((r) => resolvers.push(() => { r(pacienteDetalle()); })));
    const odontograma = vi.fn<Api['odontograma']>(() => new Promise((r) => resolvers.push(() => { r({ paciente_id: 7, piezas: [] }); })));
    const api = apiFalsa({ paciente, odontograma });
    await montar(api, ['recepcion'], 'odontograma');
    expect(paciente).toHaveBeenCalledTimes(1);
    expect(odontograma).toHaveBeenCalledTimes(1);
    expect(api.ficha).not.toHaveBeenCalled();
    expect(api.presupuestos).not.toHaveBeenCalled();
    await act(async () => {
      resolvers.forEach((r) => { r(); });
      await Promise.resolve();
    });
  });

  it('si fallan los presupuestos la cabecera sigue y la pestaña ofrece reintentar, sin el texto de lista vacía', async () => {
    const presupuestos = vi.fn<Api['presupuestos']>().mockRejectedValueOnce(new ErrorApiPanel(500, 'x', null)).mockResolvedValue([]);
    await montar(apiFalsa({ presupuestos }), ['recepcion'], 'presupuestos');
    expect(await screen.findByText(/^No pudimos cargar los presupuestos/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Lucía Ejemplo' })).toBeInTheDocument();
    expect(screen.queryByText('Este paciente todavía no tiene presupuestos')).toBeNull();
    await usuario.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Este paciente todavía no tiene presupuestos')).toBeInTheDocument();
    expect(presupuestos).toHaveBeenCalledTimes(2);
  });

  it('volver a una pestaña ya abierta usa lo cargado y «Actualizar» la pide otra vez', async () => {
    const api = apiFalsa();
    await montar(api);
    await screen.findByRole('heading', { level: 2, name: 'Lucía Ejemplo' });
    await screen.findByText('Penicilina (sintético)');
    await usuario.click(screen.getByRole('tab', { name: 'Odontograma' }));
    await screen.findByRole('tab', { name: 'Odontograma', selected: true });
    expect(api.odontograma).toHaveBeenCalledTimes(1);
    await usuario.click(screen.getByRole('tab', { name: 'Ficha' }));
    expect(await screen.findByText('Penicilina (sintético)')).toBeInTheDocument();
    expect(api.ficha).toHaveBeenCalledTimes(1);
    await usuario.click(screen.getByRole('button', { name: 'Actualizar' }));
    expect(api.ficha).toHaveBeenCalledTimes(2);
  });

  it('cambiar de pestaña actualiza el hash sin recargar', async () => {
    await montar(apiFalsa());
    await screen.findByRole('heading', { level: 2, name: 'Lucía Ejemplo' });
    await usuario.click(screen.getByRole('tab', { name: 'Presupuestos' }));
    expect(window.location.hash).toBe('#/pacientes/7?pestana=presupuestos');
  });
});

describe('Cambios pendientes al salir de una pestaña', () => {
  async function conCambios(api: Api): Promise<void> {
    await montar(api);
    await usuario.click(await screen.findByRole('button', { name: 'Editar ficha' }));
    await usuario.click(screen.getByLabelText('Observaciones'));
    await act(() => base.paste('Nota (sintético)'));
  }

  it('beforeunload solo se activa cuando hay cambios', async () => {
    await montar(apiFalsa());
    await screen.findByText('Penicilina (sintético)');
    const sinCambios = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(sinCambios);
    expect(sinCambios.defaultPrevented).toBe(false);
    await usuario.click(screen.getByRole('button', { name: 'Editar ficha' }));
    await usuario.click(screen.getByLabelText('Observaciones'));
    await act(() => base.paste('Nota (sintético)'));
    const conCambiosEvento = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(conCambiosEvento);
    expect(conCambiosEvento.defaultPrevented).toBe(true);
  });

  it('cambiar de pestaña con cambios pide confirmación y, sin elegir, nada se pierde', async () => {
    await conCambios(apiFalsa());
    await usuario.click(screen.getByRole('tab', { name: 'Odontograma' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText('Tenés cambios sin guardar en la ficha')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Ficha' })).toHaveAttribute('aria-selected', 'true');
    await usuario.click(within(dialogo).getByRole('button', { name: 'Seguir editando' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByLabelText('Observaciones')).toHaveValue('Nota (sintético)');
  });

  it('«Descartar cambios» sigue a la otra pestaña y descarta lo escrito', async () => {
    const api = apiFalsa();
    await conCambios(api);
    await usuario.click(screen.getByRole('tab', { name: 'Odontograma' }));
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Descartar cambios' }));
    expect(await screen.findByRole('tab', { name: 'Odontograma', selected: true })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/pacientes/7?pestana=odontograma');
    await usuario.click(screen.getByRole('tab', { name: 'Ficha' }));
    expect(screen.queryByLabelText('Observaciones')).toBeNull();
  });

  it('«Volver» con cambios también pide confirmación', async () => {
    await conCambios(apiFalsa());
    await usuario.click(screen.getByRole('link', { name: /Volver/ }));
    expect(await screen.findByText('Tenés cambios sin guardar en la ficha')).toBeInTheDocument();
  });
});
