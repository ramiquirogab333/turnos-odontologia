import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import type { Seccion } from '../lib/ruta';
import { Navegacion } from './Navegacion';

const base = userEvent.setup();

afterEach(() => {
  window.location.hash = '';
});

function montar(actual: Seccion) {
  render(<Navegacion actual={actual} />);
}

describe('Navegacion', () => {
  it('muestra las siete secciones en un nav con nombre', () => {
    montar('agenda');
    const nav = screen.getByRole('navigation', { name: 'Secciones del panel' });
    expect(nav).toBeInTheDocument();
    expect(screen.getAllByRole('link').map((a) => a.textContent)).toEqual(['Agenda', 'Pacientes', 'Indicadores', 'Caja', 'Recordatorios', 'Google Calendar', 'Datos']);
  });

  it('con una lista acotada (la odontóloga) solo muestra esas secciones', () => {
    render(<Navegacion actual="agenda" secciones={['agenda', 'google-calendar']} />);
    expect(screen.getAllByRole('link').map((a) => a.textContent)).toEqual(['Agenda', 'Google Calendar']);
    expect(screen.getByRole('link', { name: 'Google Calendar' })).toHaveAttribute('href', '#/google-calendar');
  });

  it('marca la sección activa con aria-current y solo a ella', () => {
    montar('caja');
    expect(screen.getByRole('link', { name: 'Caja' })).toHaveAttribute('aria-current', 'page');
    for (const nombre of ['Agenda', 'Pacientes', 'Indicadores']) {
      expect(screen.getByRole('link', { name: nombre })).not.toHaveAttribute('aria-current');
    }
  });

  it('Recordatorios (C-09) enlaza a su hash y se marca cuando está activa', async () => {
    montar('recordatorios');
    expect(screen.getByRole('link', { name: 'Recordatorios' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Recordatorios' })).toHaveAttribute('href', '#/recordatorios');
    await act(() => base.click(screen.getByRole('link', { name: 'Agenda' })));
    expect(window.location.hash).toBe('#/agenda');
  });

  it('otra sección activa mueve la marca', () => {
    montar('pacientes');
    expect(screen.getByRole('link', { name: 'Pacientes' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Caja' })).not.toHaveAttribute('aria-current');
  });

  it('cada enlace apunta a su hash y cambiar de sección no recarga la página', async () => {
    montar('agenda');
    const antes = window.location.pathname;
    await act(() => base.click(screen.getByRole('link', { name: 'Indicadores' })));
    expect(window.location.hash).toBe('#/indicadores');
    await act(() => base.click(screen.getByRole('link', { name: 'Caja' })));
    expect(window.location.hash).toBe('#/caja');
    expect(window.location.pathname).toBe(antes);
    expect(screen.getByRole('link', { name: 'Pacientes' })).toHaveAttribute('href', '#/pacientes');
  });

  it('se puede recorrer con el teclado: los enlaces reciben el foco', async () => {
    montar('agenda');
    await act(() => base.tab());
    expect(screen.getByRole('link', { name: 'Agenda' })).toHaveFocus();
    await act(() => base.tab());
    expect(screen.getByRole('link', { name: 'Pacientes' })).toHaveFocus();
  });
});
