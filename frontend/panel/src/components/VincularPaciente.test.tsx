import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import { apiFalsa, pacienteDetalle, turno } from '../test/datos';
import { VincularPaciente } from './VincularPaciente';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

const SIN_VINCULO = turno({ id: 11, paciente_id: null, paciente_nombre: 'Carlos Sintético', paciente_telefono: '+5491100000003' });

async function montar(sobre: Partial<Api> = {}, elTurno = SIN_VINCULO) {
  const api = apiFalsa(sobre);
  const alVincular = vi.fn<() => void>();
  const alCerrar = vi.fn<() => void>();
  await act(async () => {
    render(<VincularPaciente api={api} turno={elTurno} onVinculado={alVincular} onCerrar={alCerrar} />);
    await Promise.resolve();
  });
  return { api, alVincular, alCerrar };
}

async function buscar(dni: string): Promise<void> {
  await usuario.type(screen.getByLabelText('DNI del paciente'), dni);
  await usuario.click(screen.getByRole('button', { name: 'Buscar' }));
}

describe('Vínculo de un turno con su paciente desde la agenda', () => {
  it('busca por DNI y vincula a la paciente existente', async () => {
    const buscarPorDni = vi.fn<Api['buscarPorDni']>().mockResolvedValue([pacienteDetalle()]);
    const { api, alVincular } = await montar({ buscarPorDni });
    await buscar('99000001');
    expect(buscarPorDni).toHaveBeenCalledWith('99000001');
    await usuario.click(await screen.findByRole('button', { name: 'Vincular a Lucía Ejemplo' }));
    expect(api.vincularTurno).toHaveBeenCalledWith(11, 7);
    expect(alVincular).toHaveBeenCalledTimes(1);
  });

  it('un DNI no registrado ofrece el alta precargada con DNI, teléfono y nombre separado, y vincula al guardar', async () => {
    const crearPaciente = vi.fn<Api['crearPaciente']>().mockResolvedValue({ ok: true, valor: pacienteDetalle({ id: 15, nombre: 'Carlos', apellido: 'Sintético', dni: '99000003' }) });
    const { api, alVincular } = await montar({ crearPaciente });
    await buscar('99000003');
    expect(await screen.findByText('No hay ningún paciente con ese DNI')).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Dar de alta y vincular' }));
    await screen.findByRole('combobox', { name: 'Obra social' });
    expect(screen.getByLabelText('DNI')).toHaveValue('99000003');
    expect(screen.getByLabelText('Teléfono')).toHaveValue('+5491100000003');
    expect(screen.getByLabelText('Nombre')).toHaveValue('Carlos');
    expect(screen.getByLabelText('Apellido')).toHaveValue('Sintético');
    await usuario.click(screen.getByRole('button', { name: 'Guardar paciente' }));
    expect(crearPaciente).toHaveBeenCalledTimes(1);
    expect(api.vincularTurno).toHaveBeenCalledWith(11, 15);
    expect(alVincular).toHaveBeenCalledTimes(1);
  });

  it('si el alta se crea pero el vínculo falla, «Reintentar vínculo» vincula sin crear un segundo paciente', async () => {
    const crearPaciente = vi.fn<Api['crearPaciente']>().mockResolvedValue({ ok: true, valor: pacienteDetalle({ id: 15 }) });
    const vincularTurno = vi
      .fn<Api['vincularTurno']>()
      .mockResolvedValueOnce({ ok: false, error: { tipo: 'desconocido' } })
      .mockResolvedValueOnce({ ok: true, valor: { turno_id: 11, paciente_id: 15 } });
    const { alVincular } = await montar({ crearPaciente, vincularTurno });
    await buscar('99000003');
    await usuario.click(await screen.findByRole('button', { name: 'Dar de alta y vincular' }));
    await screen.findByRole('combobox', { name: 'Obra social' });
    await usuario.click(screen.getByRole('button', { name: 'Guardar paciente' }));
    expect(await screen.findByText('Creamos el paciente pero no pudimos vincular el turno')).toBeInTheDocument();
    expect(alVincular).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: 'Reintentar vínculo' }));
    expect(vincularTurno).toHaveBeenCalledTimes(2);
    expect(vincularTurno).toHaveBeenLastCalledWith(11, 15);
    expect(crearPaciente).toHaveBeenCalledTimes(1);
    expect(alVincular).toHaveBeenCalledTimes(1);
  });

  it('un DNI mal escrito se corrige sin buscar', async () => {
    const { api } = await montar();
    await buscar('9900001a');
    expect(screen.getByText('El DNI tiene 7 u 8 números, sin puntos')).toBeInTheDocument();
    expect(api.buscarPorDni).not.toHaveBeenCalled();
  });
});

describe('Corrección de un vínculo existente', () => {
  const VINCULADO = turno({ id: 11, paciente_id: 9, paciente_nombre: 'Mateo Prueba', estado: 'atendido' });

  it('pide confirmación con el aviso de acceso clínico antes de enviar y después vincula', async () => {
    const buscarPorDni = vi.fn<Api['buscarPorDni']>().mockResolvedValue([pacienteDetalle()]);
    const { api, alVincular } = await montar({ buscarPorDni }, VINCULADO);
    await buscar('99000001');
    await usuario.click(await screen.findByRole('button', { name: 'Vincular a Lucía Ejemplo' }));
    expect(screen.getByText(/puede ganar o perder acceso clínico/)).toBeInTheDocument();
    expect(api.vincularTurno).not.toHaveBeenCalled();
    await usuario.click(screen.getByRole('button', { name: 'Confirmar el cambio' }));
    expect(api.vincularTurno).toHaveBeenCalledWith(11, 7);
    expect(alVincular).toHaveBeenCalledTimes(1);
  });

  it('elegir el mismo paciente avisa y no envía ningún pedido', async () => {
    const buscarPorDni = vi.fn<Api['buscarPorDni']>().mockResolvedValue([pacienteDetalle({ id: 9 })]);
    const { api } = await montar({ buscarPorDni }, VINCULADO);
    await buscar('99000001');
    expect(await screen.findByText('El turno ya está vinculado con esta paciente')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Vincular a/ })).toBeNull();
    expect(api.vincularTurno).not.toHaveBeenCalled();
  });

  it('«Volver» en la confirmación vuelve a la búsqueda sin cambiar el vínculo', async () => {
    const buscarPorDni = vi.fn<Api['buscarPorDni']>().mockResolvedValue([pacienteDetalle()]);
    const { api } = await montar({ buscarPorDni }, VINCULADO);
    await buscar('99000001');
    await usuario.click(await screen.findByRole('button', { name: 'Vincular a Lucía Ejemplo' }));
    await usuario.click(screen.getByRole('button', { name: 'Volver' }));
    expect(screen.getByLabelText('DNI del paciente')).toBeInTheDocument();
    expect(screen.queryByText(/puede ganar o perder acceso clínico/)).toBeNull();
    expect(api.vincularTurno).not.toHaveBeenCalled();
  });
});
