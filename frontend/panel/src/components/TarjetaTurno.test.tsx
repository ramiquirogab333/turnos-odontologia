import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { TurnoAgenda } from '../lib/tipos';
import { apiFalsa, pacienteDetalle, turno } from '../test/datos';
import { PuedeVincularContext } from './contextoAgenda';
import { TarjetaTurno } from './TarjetaTurno';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

function montar(elTurno: TurnoAgenda, puedeVincular: boolean, api = apiFalsa()) {
  const alCambiar = vi.fn<() => void>();
  render(
    <PuedeVincularContext value={puedeVincular}>
      <ul>
        <TarjetaTurno turno={elTurno} api={api} onCambio={alCambiar} conProfesional={false} />
      </ul>
    </PuedeVincularContext>,
  );
  return { api, alCambiar };
}

describe('Acceso a la ficha desde la agenda', () => {
  it('un turno vinculado muestra «Ver ficha» hacia el detalle, para quien vincula y para la odontóloga', () => {
    const vinculado = turno({ paciente_id: 7, paciente_nombre: 'Lucía Ejemplo' });
    montar(vinculado, true);
    expect(screen.getByRole('link', { name: 'Ver ficha' })).toHaveAttribute('href', '#/pacientes/7');
    expect(screen.queryByRole('button', { name: 'Vincular paciente' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Cambiar paciente' })).toBeInTheDocument();
  });

  it('la odontóloga ve «Ver ficha» pero no puede cambiar el vínculo', () => {
    montar(turno({ paciente_id: 7, paciente_telefono: null }), false);
    expect(screen.getByRole('link', { name: 'Ver ficha' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cambiar paciente' })).toBeNull();
  });

  it('un turno sin vínculo no muestra «Ver ficha»: recepción ve «Vincular paciente» y la odontóloga ninguna de las dos acciones', () => {
    const sin = turno({ paciente_id: null });
    const { unmount } = render(
      <PuedeVincularContext value={true}>
        <ul>
          <TarjetaTurno turno={sin} api={apiFalsa()} onCambio={() => undefined} conProfesional={false} />
        </ul>
      </PuedeVincularContext>,
    );
    expect(screen.queryByRole('link', { name: 'Ver ficha' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Vincular paciente' })).toBeInTheDocument();
    unmount();
    montar(sin, false);
    expect(screen.queryByRole('link', { name: 'Ver ficha' })).toBeNull();
    expect(screen.queryByRole('button', { name: /paciente/ })).toBeNull();
  });

  it('tras vincular, la agenda se vuelve a pedir', async () => {
    const api = apiFalsa({ buscarPorDni: vi.fn().mockResolvedValue([pacienteDetalle()]) });
    const { alCambiar } = montar(turno({ id: 11, paciente_id: null }), true, api);
    await usuario.click(screen.getByRole('button', { name: 'Vincular paciente' }));
    await usuario.type(screen.getByLabelText('DNI del paciente'), '99000001');
    await usuario.click(screen.getByRole('button', { name: 'Buscar' }));
    await usuario.click(await screen.findByRole('button', { name: 'Vincular a Lucía Ejemplo' }));
    expect(api.vincularTurno).toHaveBeenCalledWith(11, 7);
    expect(alCambiar).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
