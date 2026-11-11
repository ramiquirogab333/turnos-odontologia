import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { CambioEstado, ErrorEstado, Resultado } from '../lib/tipos';
import { apiFalsa, CAMBIO, turno } from '../test/datos';
import { AccionesTurno } from './AccionesTurno';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

function montar(sobre: Parameters<typeof turno>[0], api = apiFalsa(), onCambio = vi.fn()) {
  render(<AccionesTurno turno={turno(sobre)} api={api} onCambio={onCambio} />);
  return { api, onCambio };
}

const rechazo = (error: ErrorEstado) => ({ ok: false as const, error });

describe('AccionesTurno: qué botones aparecen', () => {
  it('muestra solo las acciones que informa el servidor, con el resultado en el nombre', () => {
    montar({ acciones: ['atendido', 'ausente'] });
    expect(screen.getByRole('button', { name: 'Marcar atendido' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Marcar ausente' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancelar turno' })).toBeNull();
  });

  it('sin acciones no muestra ningún botón', () => {
    montar({ acciones: [] });
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('ofrece cancelar cuando el servidor lo permite', () => {
    montar({ acciones: ['cancelar'] });
    expect(screen.getByRole('button', { name: 'Cancelar turno' })).toBeInTheDocument();
  });
});

describe('AccionesTurno: confirmación', () => {
  it('ausente con seña acreditada avisa que no se devuelve y que no se puede deshacer, y no cambia nada hasta confirmar', async () => {
    const { api } = montar({ acciones: ['ausente'], sena: { estado: 'acreditado', monto: '3000.00' } });
    await usuario.click(screen.getByRole('button', { name: 'Marcar ausente' }));
    const dialogo = screen.getByRole('dialog', { name: '¿Marcar a Carlos Sintético como ausente?' });
    expect(within(dialogo).getByText(/seña de \$\s?3\.000,00 no se devuelve/)).toBeInTheDocument();
    expect(within(dialogo).getByText(/no se puede deshacer/)).toBeInTheDocument();
    expect(api.marcar).not.toHaveBeenCalled();
    await usuario.click(within(dialogo).getByRole('button', { name: 'Volver' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(api.marcar).not.toHaveBeenCalled();
  });

  it('ausente sin seña no habla de plata', async () => {
    montar({ acciones: ['ausente'], sena: null });
    await usuario.click(screen.getByRole('button', { name: 'Marcar ausente' }));
    const dialogo = screen.getByRole('dialog');
    expect(dialogo).not.toHaveTextContent('seña de');
    expect(dialogo).toHaveTextContent('no se puede deshacer');
  });

  it('atendido avisa que recepción puede corregirlo y que el horario sigue ocupado', async () => {
    montar({ acciones: ['atendido'] });
    await usuario.click(screen.getByRole('button', { name: 'Marcar atendido' }));
    const dialogo = screen.getByRole('dialog', { name: '¿Marcar a Carlos Sintético como atendido?' });
    expect(dialogo).toHaveTextContent('recepción puede corregirlo');
    expect(dialogo).toHaveTextContent('sigue ocupado');
  });

  it('cancelar con seña acreditada avisa que queda a devolver', async () => {
    montar({ acciones: ['cancelar'], sena: { estado: 'acreditado', monto: '3000.00' } });
    await usuario.click(screen.getByRole('button', { name: 'Cancelar turno' }));
    const dialogo = screen.getByRole('dialog', { name: '¿Cancelar el turno de Carlos Sintético?' });
    expect(dialogo).toHaveTextContent(/\$\s?3\.000,00/);
    expect(dialogo).toHaveTextContent('a devolver');
  });

  it('cancelar una pre-reserva dice que no hay seña cobrada', async () => {
    montar({ acciones: ['cancelar'], estado: 'en_espera', bloquea_agenda: false, sena: { estado: 'pendiente', monto: '3000.00' } });
    await usuario.click(screen.getByRole('button', { name: 'Cancelar turno' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('todavía no pagó la seña');
  });

  it('sin nombre de contacto el título usa "este turno"', async () => {
    montar({ acciones: ['atendido'], paciente_nombre: null });
    await usuario.click(screen.getByRole('button', { name: 'Marcar atendido' }));
    expect(screen.getByRole('dialog', { name: '¿Marcar este turno como atendido?' })).toBeInTheDocument();
  });

  it('confirmar llama al servidor con el turno y la acción, avisa el cambio y cierra el diálogo', async () => {
    const { api, onCambio } = montar({ acciones: ['ausente'] });
    await usuario.click(screen.getByRole('button', { name: 'Marcar ausente' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, marcar ausente' }));
    expect(api.marcar).toHaveBeenCalledWith(11, 'ausente');
    expect(onCambio).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('mientras envía deshabilita la confirmación', async () => {
    let resolver: (v: Resultado<CambioEstado, ErrorEstado>) => void = () => undefined;
    const api = apiFalsa({
      marcar: vi.fn(() => new Promise<Resultado<CambioEstado, ErrorEstado>>((res) => { resolver = res; })),
    });
    montar({ acciones: ['atendido'] }, api);
    await usuario.click(screen.getByRole('button', { name: 'Marcar atendido' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, marcar atendido' }));
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Guardando…' })).toBeDisabled();
    await act(async () => {
      resolver({ ok: true, valor: CAMBIO });
      await Promise.resolve();
    });
    expect(api.marcar).toHaveBeenCalledTimes(1);
  });
});

describe('AccionesTurno: rechazos del servidor', () => {
  async function confirmar(accion: 'ausente' | 'atendido' | 'cancelar', error: ErrorEstado, sobre: Parameters<typeof turno>[0] = {}) {
    const api = apiFalsa({ marcar: vi.fn().mockResolvedValue(rechazo(error)) });
    const onCambio = vi.fn();
    montar({ acciones: [accion], ...sobre }, api, onCambio);
    const nombre = accion === 'cancelar' ? 'Cancelar turno' : `Marcar ${accion}`;
    await usuario.click(screen.getByRole('button', { name: nombre }));
    const confirmarBoton = within(screen.getByRole('dialog')).getByRole('button', { name: /^Sí, / });
    await usuario.click(confirmarBoton);
    return { api, onCambio };
  }

  it('marcado_no_habilitado dice desde cuándo, en hora de la clínica, y no recarga la agenda', async () => {
    const { onCambio } = await confirmar('ausente', { tipo: 'marcado_no_habilitado', habilitadoDesde: '2031-11-18T12:10:00Z' });
    expect(screen.getByRole('alert')).toHaveTextContent('Todavía no se puede marcar este turno. Podés hacerlo desde las 09:10.');
    expect(onCambio).not.toHaveBeenCalled();
  });

  it('fuera_de_plazo explica el límite y que el turno no cambió', async () => {
    await confirmar('cancelar', { tipo: 'fuera_de_plazo', limiteCambios: '2031-11-17T09:00:00-03:00' });
    const alerta = screen.getByRole('alert');
    expect(alerta).toHaveTextContent('Faltan menos de 24 horas');
    expect(alerta).toHaveTextContent('17/11');
    expect(alerta).toHaveTextContent('09:00');
  });

  it('transicion_invalida avisa que el turno ya cambió y recarga la agenda', async () => {
    const { onCambio } = await confirmar('atendido', { tipo: 'transicion_invalida' });
    expect(screen.getByRole('alert')).toHaveTextContent('Este turno ya cambió de estado. Actualizamos la agenda.');
    expect(onCambio).toHaveBeenCalledTimes(1);
  });

  it.each([
    [{ tipo: 'no_encontrado' }, 'Ese turno ya no existe. Actualizamos la agenda.', 1],
    [{ tipo: 'sin_permiso' }, 'Tu usuario no puede hacer este cambio.', 0],
    [{ tipo: 'reintentar' }, 'El servidor está ocupado. Probá de nuevo en unos segundos.', 0],
    [{ tipo: 'desconocido' }, 'No pudimos guardar el cambio. Probá de nuevo; si sigue igual, avisá a la clínica.', 0],
  ] as const)('%j muestra "%s"', async (error, texto, recargas) => {
    const { onCambio } = await confirmar('ausente', error);
    expect(screen.getByRole('alert')).toHaveTextContent(texto);
    expect(onCambio).toHaveBeenCalledTimes(recargas);
  });

  it('después de un rechazo se puede volver a intentar', async () => {
    const api = apiFalsa({ marcar: vi.fn().mockResolvedValueOnce(rechazo({ tipo: 'reintentar' })).mockResolvedValueOnce({ ok: true, valor: CAMBIO }) });
    const { onCambio } = montar({ acciones: ['atendido'] }, api);
    await usuario.click(screen.getByRole('button', { name: 'Marcar atendido' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, marcar atendido' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, marcar atendido' }));
    expect(api.marcar).toHaveBeenCalledTimes(2);
    expect(onCambio).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('Pantalla para deshacer un atendido', () => {
  const atendido = { estado: 'atendido' as const, acciones: ['deshacer_atendido' as const] };

  it('«Deshacer atendido» aparece solo si el servidor informa la acción', () => {
    montar({ ...atendido });
    expect(screen.getByRole('button', { name: 'Deshacer atendido' })).toBeInTheDocument();
  });

  it('sin la acción del servidor no hay botón (la odontóloga dueña del turno no lo ve)', () => {
    montar({ estado: 'atendido', acciones: [] });
    expect(screen.queryByRole('button', { name: 'Deshacer atendido' })).toBeNull();
  });

  it('el diálogo pide el motivo y avisa que el turno vuelve a reservado y que la odontóloga puede perder el acceso a la ficha', async () => {
    const { api } = montar({ ...atendido });
    await usuario.click(screen.getByRole('button', { name: 'Deshacer atendido' }));
    const dialogo = screen.getByRole('dialog', { name: '¿Deshacer el atendido de Carlos Sintético?' });
    expect(dialogo).toHaveTextContent('vuelve a reservado');
    expect(dialogo).toHaveTextContent('puede perder el acceso a la ficha');
    expect(within(dialogo).getByLabelText('Motivo')).toBeInTheDocument();
    expect(api.deshacerAtendido).not.toHaveBeenCalled();
  });

  it('sin motivo no envía nada y dice qué falta', async () => {
    const { api } = montar({ ...atendido });
    await usuario.click(screen.getByRole('button', { name: 'Deshacer atendido' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, deshacer el atendido' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Elegí el motivo para deshacer el atendido');
    expect(api.deshacerAtendido).not.toHaveBeenCalled();
  });

  it.each([
    ['turno_equivocado', 'Marqué el turno equivocado'],
    ['paciente_no_asistio', 'La persona no vino'],
    ['otro', 'Otro motivo'],
  ] as const)('con el motivo "%s" llama al servidor, avisa el cambio y cierra', async (clave, etiqueta) => {
    const { api, onCambio } = montar({ ...atendido });
    await usuario.click(screen.getByRole('button', { name: 'Deshacer atendido' }));
    const dialogo = screen.getByRole('dialog');
    await act(() => base.selectOptions(within(dialogo).getByLabelText('Motivo'), etiqueta));
    await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, deshacer el atendido' }));
    expect(api.deshacerAtendido).toHaveBeenCalledWith(11, clave);
    expect(api.marcar).not.toHaveBeenCalled();
    expect(onCambio).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('plazo_vencido dice que ya pasaron 7 días y recarga la agenda', async () => {
    const api = apiFalsa({
      deshacerAtendido: vi.fn().mockResolvedValue(rechazo({ tipo: 'plazo_vencido', limiteCorreccion: '2031-11-25T09:00:00-03:00' })),
    });
    const { onCambio } = montar({ ...atendido }, api);
    await usuario.click(screen.getByRole('button', { name: 'Deshacer atendido' }));
    const dialogo = screen.getByRole('dialog');
    await act(() => base.selectOptions(within(dialogo).getByLabelText('Motivo'), 'Otro motivo'));
    await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, deshacer el atendido' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Ya pasaron 7 días: este turno no se puede corregir');
    expect(onCambio).toHaveBeenCalledTimes(1);
  });

  it('un rechazo de permiso no recarga y deja intentar de nuevo', async () => {
    const api = apiFalsa({ deshacerAtendido: vi.fn().mockResolvedValue(rechazo({ tipo: 'sin_permiso' })) });
    const { onCambio } = montar({ ...atendido }, api);
    await usuario.click(screen.getByRole('button', { name: 'Deshacer atendido' }));
    const dialogo = screen.getByRole('dialog');
    await act(() => base.selectOptions(within(dialogo).getByLabelText('Motivo'), 'Otro motivo'));
    await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, deshacer el atendido' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Tu usuario no puede hacer este cambio.');
    expect(onCambio).not.toHaveBeenCalled();
  });

  it('marcar atendido ya no promete que no se puede deshacer: dice que recepción lo puede corregir', async () => {
    montar({ acciones: ['atendido'] });
    await usuario.click(screen.getByRole('button', { name: 'Marcar atendido' }));
    const dialogo = screen.getByRole('dialog');
    expect(dialogo).toHaveTextContent('recepción puede corregirlo');
    expect(dialogo).not.toHaveTextContent('no se puede deshacer');
  });
});
