import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ErrorAlta, Resultado, TurnoCreado } from '../lib/tipos';
import { apiFalsa, CREADO, OPCIONES, SLOTS } from '../test/datos';
import { AltaManual } from './AltaManual';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
  elegir: (el: Element, valor: string) => act(() => base.selectOptions(el, valor)),
};

function montar(api = apiFalsa()) {
  const onCreado = vi.fn();
  const onCerrar = vi.fn();
  render(<AltaManual api={api} opciones={OPCIONES} fechaInicial="2031-11-18" onCreado={onCreado} onCerrar={onCerrar} />);
  return { api, onCreado, onCerrar };
}

async function elegirTratamientoYProfesional() {
  await usuario.elegir(screen.getByLabelText('Tratamiento'), 'Limpieza dental');
  await usuario.elegir(screen.getByLabelText('Profesional'), 'Dra. Ana Ficticia');
}

async function completarDatos(nombre = 'Carlos Sintético', telefono = '+54 9 11 4444-5555') {
  await usuario.type(screen.getByLabelText('Nombre completo'), nombre);
  await usuario.type(screen.getByLabelText('Teléfono (WhatsApp)'), telefono);
}

const conflicto = (alternativas = [{ inicio: '2031-11-18T11:30:00-03:00', fin: '2031-11-18T12:00:00-03:00', sillon_id: 2 }]) =>
  ({ ok: false as const, error: { tipo: 'conflicto', motivo: 'profesional', alternativas } satisfies ErrorAlta });

describe('AltaManual: horarios', () => {
  it('no consulta la disponibilidad hasta elegir tratamiento y profesional', async () => {
    const { api } = montar();
    expect(api.disponibilidad).not.toHaveBeenCalled();
    await usuario.elegir(screen.getByLabelText('Tratamiento'), 'Limpieza dental');
    expect(api.disponibilidad).not.toHaveBeenCalled();
    await usuario.elegir(screen.getByLabelText('Profesional'), 'Dra. Ana Ficticia');
    expect(api.disponibilidad).toHaveBeenCalledTimes(1);
    expect(api.disponibilidad).toHaveBeenCalledWith(1, 3, '2031-11-18');
  });

  it('al cambiar el día vuelve a consultar y muestra los horarios en hora de la clínica', async () => {
    const { api } = montar();
    await elegirTratamientoYProfesional();
    expect(await screen.findByRole('button', { name: '11:00' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '11:30' })).toBeInTheDocument();
    const dia = screen.getByLabelText('Día');
    await act(async () => {
      await base.clear(dia);
      await base.type(dia, '2031-11-19');
    });
    expect(api.disponibilidad).toHaveBeenLastCalledWith(1, 3, '2031-11-19');
  });

  it('sin horarios libres lo dice y sugiere otro día', async () => {
    const api = apiFalsa({ disponibilidad: vi.fn().mockResolvedValue([]) });
    montar(api);
    await elegirTratamientoYProfesional();
    expect(await screen.findByText('No hay horarios libres ese día. Probá con otro día.')).toBeInTheDocument();
  });

  it('si la consulta de horarios falla ofrece reintentar', async () => {
    const api = apiFalsa({ disponibilidad: vi.fn().mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(SLOTS) });
    montar(api);
    await elegirTratamientoYProfesional();
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('No pudimos consultar los horarios');
    await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByRole('button', { name: '11:00' })).toBeInTheDocument();
  });
});

describe('AltaManual: validación y alta', () => {
  it('con un teléfono inválido explica cómo corregirlo y no envía', async () => {
    const { api } = montar();
    await elegirTratamientoYProfesional();
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await completarDatos('Carlos Sintético', '11 5555 6666');
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(screen.getByText(/Ingresá el teléfono con \+ y código de país/)).toBeInTheDocument();
    expect(screen.getByLabelText('Teléfono (WhatsApp)')).toHaveAttribute('aria-invalid', 'true');
    expect(api.crearTurno).not.toHaveBeenCalled();
  });

  it('sin horario elegido pide elegir uno', async () => {
    const { api } = montar();
    await elegirTratamientoYProfesional();
    await completarDatos();
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Elegí un horario libre.');
    expect(api.crearTurno).not.toHaveBeenCalled();
  });

  it('envía el teléfono normalizado, muestra el código de gestión una sola vez y avisa a la agenda', async () => {
    const { api, onCreado, onCerrar } = montar();
    await elegirTratamientoYProfesional();
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await completarDatos();
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(api.crearTurno).toHaveBeenCalledWith({
      profesionalId: 1, tratamientoId: 3, inicio: '2031-11-18T11:00:00-03:00', nombre: 'Carlos Sintético', telefono: '+5491144445555',
    });
    expect(await screen.findByRole('heading', { name: 'Turno creado' })).toBeInTheDocument();
    expect(screen.getByText(CREADO.codigo_gestion)).toBeInTheDocument();
    expect(screen.getByText(/se muestra una sola vez/i)).toBeInTheDocument();
    expect(onCreado).toHaveBeenCalledTimes(1);
    await usuario.click(screen.getByRole('button', { name: 'Listo' }));
    expect(onCerrar).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(CREADO.codigo_gestion)).toBeNull();
  });

  it('mientras guarda deshabilita el botón: no hay doble alta', async () => {
    let resolver: (r: Resultado<TurnoCreado, ErrorAlta>) => void = () => undefined;
    const api = apiFalsa({
      crearTurno: vi.fn(() => new Promise<Resultado<TurnoCreado, ErrorAlta>>((res) => { resolver = res; })),
    });
    montar(api);
    await elegirTratamientoYProfesional();
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await completarDatos();
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(screen.getByRole('button', { name: 'Creando…' })).toBeDisabled();
    await act(async () => {
      resolver({ ok: true, valor: CREADO });
      await Promise.resolve();
    });
    expect(api.crearTurno).toHaveBeenCalledTimes(1);
  });
});

describe('AltaManual: rechazos', () => {
  it('un horario tomado muestra alternativas sin perder los datos y permite elegir otra', async () => {
    const api = apiFalsa({
      crearTurno: vi.fn().mockResolvedValueOnce(conflicto()).mockResolvedValueOnce({ ok: true, valor: CREADO }),
    });
    montar(api);
    await elegirTratamientoYProfesional();
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await completarDatos();
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    const aviso = await screen.findByRole('alert');
    expect(aviso).toHaveTextContent('Ese horario ya no está disponible');
    expect(screen.getByLabelText('Nombre completo')).toHaveValue('Carlos Sintético');
    expect(screen.getByLabelText('Teléfono (WhatsApp)')).toHaveValue('+54 9 11 4444-5555');
    await usuario.click(within(aviso).getByRole('button', { name: '11:30' }));
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(api.crearTurno).toHaveBeenLastCalledWith(expect.objectContaining({ inicio: '2031-11-18T11:30:00-03:00' }));
    expect(await screen.findByRole('heading', { name: 'Turno creado' })).toBeInTheDocument();
  });

  it('un conflicto sin alternativas lo dice y sugiere otro día', async () => {
    const api = apiFalsa({ crearTurno: vi.fn().mockResolvedValue(conflicto([])) });
    montar(api);
    await elegirTratamientoYProfesional();
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await completarDatos();
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Probá con otro día');
  });

  it.each([
    [{ tipo: 'fuera_de_disponibilidad' }, 'Ese horario está fuera de la atención de la profesional. Elegí otro.'],
    [{ tipo: 'inicio_pasado' }, 'Ese horario ya pasó. Elegí uno futuro.'],
    [{ tipo: 'validacion', mensaje: 'nombre inválido' }, 'nombre inválido'],
    [{ tipo: 'sin_permiso' }, 'Tu usuario no puede cargar turnos.'],
    [{ tipo: 'desconocido' }, 'No pudimos crear el turno. Probá de nuevo; si sigue igual, avisá a la clínica.'],
  ] as const)('%j muestra "%s"', async (error, texto) => {
    const api = apiFalsa({ crearTurno: vi.fn().mockResolvedValue({ ok: false, error }) });
    montar(api);
    await elegirTratamientoYProfesional();
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await completarDatos();
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(texto);
    expect(screen.getByLabelText('Nombre completo')).toHaveValue('Carlos Sintético');
  });

  it('cancelar cierra sin crear nada', async () => {
    const { api, onCerrar } = montar();
    await usuario.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(onCerrar).toHaveBeenCalledTimes(1);
    expect(api.crearTurno).not.toHaveBeenCalled();
  });
});
