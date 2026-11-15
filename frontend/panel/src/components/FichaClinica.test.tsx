import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { Ficha, PacienteDetalle } from '../lib/tipos';
import { ACCESO_COMPLETO, ACCESO_LECTURA, apiFalsa, ficha, pacienteClinico, pacienteDetalle } from '../test/datos';
import { FichaClinica } from './FichaClinica';
import type { AvisoCambios } from './useCambiosPendientes';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
  paste: (texto: string) => act(() => base.paste(texto)),
};

const VACIA: Ficha = ficha({ alergias: '', medicacion: '', antecedentes_medicos: '', observaciones: '', version: 0, actualizado_por: null, historia: [] });

function montar(opciones: { datos?: Ficha; paciente?: PacienteDetalle; api?: Partial<Api> } = {}) {
  const api = apiFalsa(opciones.api);
  const alReemplazar = vi.fn<(f: Ficha) => void>();
  const alActualizar = vi.fn<() => void>();
  const alVencer = vi.fn<() => void>();
  const registrar = vi.fn<(aviso: AvisoCambios | null) => void>();
  render(
    <FichaClinica
      api={api}
      paciente={opciones.paciente ?? pacienteDetalle()}
      datos={opciones.datos ?? ficha()}
      onActualizar={alActualizar}
      onReemplazar={alReemplazar}
      onAccesoVencido={alVencer}
      registrarCambios={registrar}
    />,
  );
  return { api, alReemplazar, alActualizar, alVencer, registrar };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Lectura de la ficha', () => {
  it('muestra los cuatro campos y la historia en hora de la clínica, del más reciente al más antiguo', () => {
    montar({ datos: ficha({ observaciones: 'Control en 6 meses (sintético)' }) });
    expect(screen.getByText('Penicilina (sintético)')).toBeInTheDocument();
    expect(screen.getByText('Control en 6 meses (sintético)')).toBeInTheDocument();
    const historia = screen.getByRole('list', { name: 'Historia de turnos' });
    const filas = within(historia).getAllByRole('listitem');
    expect(filas).toHaveLength(2);
    expect(filas[0]).toHaveTextContent('18/11');
    expect(filas[0]).toHaveTextContent('09:00');
    expect(filas[0]).toHaveTextContent('Dra. Ana Ficticia');
    expect(filas[0]).toHaveTextContent('Limpieza dental');
    expect(filas[1]).toHaveTextContent('Dr. Juan Ejemplo');
    expect(document.body.textContent).not.toContain('+549');
  });

  it('una ficha nunca editada invita a completarla y dice que no hay turnos', () => {
    montar({ datos: VACIA });
    expect(screen.getByText('Todavía no hay antecedentes cargados')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Completar ficha' })).toBeInTheDocument();
    expect(screen.getByText('Sin turnos registrados')).toBeInTheDocument();
  });

  it('quien no puede escribir no ve «Editar ficha» ni «Completar ficha»', () => {
    montar({ datos: ficha(), paciente: pacienteClinico({ acceso_clinico: ACCESO_LECTURA }) });
    expect(screen.queryByRole('button', { name: 'Editar ficha' })).toBeNull();
    montar({ datos: VACIA, paciente: pacienteClinico({ acceso_clinico: ACCESO_LECTURA }) });
    expect(screen.queryByRole('button', { name: 'Completar ficha' })).toBeNull();
  });

  it('la odontóloga con acceso completo puede editar', () => {
    montar({ paciente: pacienteClinico({ acceso_clinico: ACCESO_COMPLETO }) });
    expect(screen.getByRole('button', { name: 'Editar ficha' })).toBeInTheDocument();
  });
});

describe('Edición de antecedentes con control de versión', () => {
  it('guarda con la versión leída, avisa «Ficha guardada» y entrega la ficha nueva', async () => {
    const nueva = ficha({ medicacion: 'Ibuprofeno 400 mg (sintético)', version: 3 });
    const guardarFicha = vi.fn<Api['guardarFicha']>().mockResolvedValue({ ok: true, valor: nueva });
    const { alReemplazar } = montar({ api: { guardarFicha } });
    await usuario.click(screen.getByRole('button', { name: 'Editar ficha' }));
    const medicacion = screen.getByLabelText('Medicación');
    await usuario.click(medicacion);
    await usuario.paste(' + Ibuprofeno 400 mg (sintético)');
    await usuario.click(screen.getByRole('button', { name: 'Guardar ficha' }));
    expect(guardarFicha).toHaveBeenCalledWith(7, {
      alergias: 'Penicilina (sintético)',
      medicacion: 'Ninguna (sintético) + Ibuprofeno 400 mg (sintético)',
      antecedentes_medicos: '',
      observaciones: '',
      version: 2,
    });
    expect(await screen.findByText('Ficha guardada')).toBeInTheDocument();
    expect(alReemplazar).toHaveBeenCalledWith(nueva);
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('si otra persona guardó antes muestra la versión vigente y lo escrito aparte, sin reintentar solo', async () => {
    const vigente = ficha({ medicacion: 'Paracetamol (sintético)', version: 4 });
    const guardarFicha = vi.fn<Api['guardarFicha']>().mockResolvedValue({ ok: false, error: { tipo: 'version_desactualizada' } });
    const pedirFicha = vi.fn<Api['ficha']>().mockResolvedValue(vigente);
    const { alReemplazar } = montar({ api: { guardarFicha, ficha: pedirFicha } });
    await usuario.click(screen.getByRole('button', { name: 'Editar ficha' }));
    await usuario.click(screen.getByLabelText('Medicación'));
    await usuario.paste(' + Ibuprofeno');
    await usuario.click(screen.getByRole('button', { name: 'Guardar ficha' }));
    expect(await screen.findByText('Alguien guardó la ficha mientras la editabas')).toBeInTheDocument();
    expect(pedirFicha).toHaveBeenCalledWith(7);
    expect(guardarFicha).toHaveBeenCalledTimes(1);
    expect(alReemplazar).toHaveBeenCalledWith(vigente);
    expect(screen.getByText('Paracetamol (sintético)')).toBeInTheDocument();
    const propio = screen.getByRole('region', { name: 'Lo que escribiste' });
    expect(within(propio).getByText('Ninguna (sintético) + Ibuprofeno')).toBeInTheDocument();
    expect(within(propio).getByRole('button', { name: 'Copiar Medicación' })).toBeInTheDocument();
  });

  it('el campo acepta 2000 caracteres, muestra 2000/2000 y no deja escribir el siguiente', async () => {
    montar({ datos: VACIA });
    await usuario.click(screen.getByRole('button', { name: 'Completar ficha' }));
    const observaciones = screen.getByLabelText('Observaciones');
    expect(observaciones).toHaveAttribute('maxlength', '2000');
    await usuario.click(observaciones);
    await usuario.paste('a'.repeat(2000));
    expect(screen.getByText('2000/2000')).toBeInTheDocument();
    await usuario.type(observaciones, 'b');
    expect(observaciones).toHaveValue('a'.repeat(2000));
  });
});

describe('Ficha de solo lectura con acceso vencido', () => {
  it('si el guardado responde 403 acceso_clinico_vencido explica, conserva lo escrito y pasa a solo lectura', async () => {
    const guardarFicha = vi.fn<Api['guardarFicha']>().mockResolvedValue({ ok: false, error: { tipo: 'acceso_vencido' } });
    const { alVencer } = montar({ api: { guardarFicha }, paciente: pacienteClinico() });
    await usuario.click(screen.getByRole('button', { name: 'Editar ficha' }));
    await usuario.click(screen.getByLabelText('Observaciones'));
    await usuario.paste('Nota importante (sintético)');
    await usuario.click(screen.getByRole('button', { name: 'Guardar ficha' }));
    expect(await screen.findByText('Tu acceso para editar venció. Para editar, pedí un turno a recepción')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Lo que escribiste' })).getByText('Nota importante (sintético)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Editar ficha' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Guardar ficha' })).toBeNull();
    expect(alVencer).toHaveBeenCalledTimes(1);
  });
});

describe('Guardado sin envíos duplicados', () => {
  it('un doble toque envía un solo pedido y el botón dice «Guardando…»', async () => {
    let resolver: () => void = () => undefined;
    const guardarFicha = vi.fn<Api['guardarFicha']>(() => new Promise((r) => { resolver = () => { r({ ok: true, valor: ficha({ version: 3 }) }); }; }));
    montar({ api: { guardarFicha } });
    await usuario.click(screen.getByRole('button', { name: 'Editar ficha' }));
    await usuario.click(screen.getByRole('button', { name: 'Guardar ficha' }));
    const guardando = screen.getByRole('button', { name: 'Guardando…' });
    expect(guardando).toBeDisabled();
    await usuario.click(guardando);
    expect(guardarFicha).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolver();
      await Promise.resolve();
    });
  });

  it('un error de red conserva lo escrito y permite reintentar con la misma versión', async () => {
    const guardarFicha = vi.fn<Api['guardarFicha']>().mockResolvedValue({ ok: false, error: { tipo: 'desconocido' } });
    montar({ api: { guardarFicha } });
    await usuario.click(screen.getByRole('button', { name: 'Editar ficha' }));
    await usuario.click(screen.getByLabelText('Observaciones'));
    await usuario.paste('Texto (sintético)');
    await usuario.click(screen.getByRole('button', { name: 'Guardar ficha' }));
    expect(await screen.findByText('No pudimos guardar la ficha. Revisá tu conexión e intentá de nuevo')).toBeInTheDocument();
    expect(screen.getByLabelText('Observaciones')).toHaveValue('Texto (sintético)');
    await usuario.click(screen.getByRole('button', { name: 'Guardar ficha' }));
    expect(guardarFicha).toHaveBeenCalledTimes(2);
    expect(guardarFicha.mock.calls[0]?.[1].version).toBe(2);
    expect(guardarFicha.mock.calls[1]?.[1].version).toBe(2);
  });

  it('registra los cambios sin guardar solo mientras los hay, y no escribe nada en el navegador', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const { registrar } = montar();
    await usuario.click(screen.getByRole('button', { name: 'Editar ficha' }));
    expect(registrar).toHaveBeenLastCalledWith(null);
    await usuario.click(screen.getByLabelText('Observaciones'));
    await usuario.paste('Algo (sintético)');
    expect(registrar).toHaveBeenLastCalledWith({
      mensaje: 'Tenés cambios sin guardar en la ficha',
      seguir: 'Seguir editando',
      descartar: 'Descartar cambios',
    });
    expect(setItem).not.toHaveBeenCalled();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});

describe('Actualizar', () => {
  it('«Actualizar» pide la ficha otra vez', async () => {
    const { alActualizar } = montar();
    await usuario.click(screen.getByRole('button', { name: 'Actualizar' }));
    expect(alActualizar).toHaveBeenCalledTimes(1);
  });
});
