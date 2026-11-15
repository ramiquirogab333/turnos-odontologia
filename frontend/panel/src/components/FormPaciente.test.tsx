import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { PacienteDetalle } from '../lib/tipos';
import { apiFalsa, pacienteDetalle } from '../test/datos';
import { FormPaciente } from './FormPaciente';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
  clear: (el: Element) => act(() => base.clear(el)),
  select: (el: Element, valor: string) => act(() => base.selectOptions(el, valor)),
};

interface Montaje {
  readonly api: ReturnType<typeof apiFalsa>;
  readonly guardado: ReturnType<typeof vi.fn<(p: PacienteDetalle) => void>>;
}

async function montar(opciones: { paciente?: PacienteDetalle | null; precargado?: { dni?: string; telefono?: string; nombre?: string; apellido?: string }; api?: Partial<Api> } = {}): Promise<Montaje> {
  const api = apiFalsa(opciones.api);
  const guardado = vi.fn<(p: PacienteDetalle) => void>();
  await act(async () => {
    render(<FormPaciente api={api} paciente={opciones.paciente ?? null} precargado={opciones.precargado} onGuardado={guardado} />);
    await Promise.resolve();
  });
  await screen.findByRole('combobox', { name: 'Obra social' });
  return { api, guardado };
}

async function completar(): Promise<void> {
  await usuario.type(screen.getByLabelText('Nombre'), 'Mateo');
  await usuario.type(screen.getByLabelText('Apellido'), 'Prueba');
  await usuario.type(screen.getByLabelText('DNI'), '99000002');
  await usuario.type(screen.getByLabelText('Teléfono'), '+5491100000002');
}

describe('Alta de paciente', () => {
  it('con datos válidos y «Sin obra social» crea el paciente y avisa para abrir su detalle', async () => {
    const { api, guardado } = await montar();
    await completar();
    await usuario.click(screen.getByRole('button', { name: 'Guardar paciente' }));
    expect(api.crearPaciente).toHaveBeenCalledWith({
      nombre: 'Mateo', apellido: 'Prueba', dni: '99000002', telefono: '+5491100000002', email: null, obra_social_id: null, numero_afiliado: null,
    });
    expect(guardado).toHaveBeenCalledTimes(1);
  });

  it('elegir una obra social manda su id', async () => {
    const { api } = await montar();
    await completar();
    await usuario.select(screen.getByRole('combobox', { name: 'Obra social' }), 'Swiss Medical');
    await usuario.type(screen.getByLabelText('Número de afiliado (opcional)'), 'SM-0001');
    await usuario.click(screen.getByRole('button', { name: 'Guardar paciente' }));
    expect(api.crearPaciente).toHaveBeenCalledWith(expect.objectContaining({ obra_social_id: 2, numero_afiliado: 'SM-0001' }));
  });

  it('un DNI ya registrado dice qué pasó, enlaza al paciente existente y conserva lo escrito', async () => {
    const crearPaciente = vi.fn<Api['crearPaciente']>().mockResolvedValue({ ok: false, error: { tipo: 'dni_duplicado' } });
    const buscarPorDni = vi.fn<Api['buscarPorDni']>().mockResolvedValue([pacienteDetalle()]);
    const { guardado } = await montar({ api: { crearPaciente, buscarPorDni } });
    await completar();
    await usuario.click(screen.getByRole('button', { name: 'Guardar paciente' }));
    expect(await screen.findByText('Ya hay un paciente con ese DNI')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Ver a Lucía Ejemplo' })).toHaveAttribute('href', '#/pacientes/7');
    expect(buscarPorDni).toHaveBeenCalledWith('99000002');
    expect(screen.getByLabelText('Nombre')).toHaveValue('Mateo');
    expect(guardado).not.toHaveBeenCalled();
  });

  it('datos con formato inválido muestran un error junto a cada campo y no envían nada', async () => {
    const { api } = await montar();
    await usuario.type(screen.getByLabelText('Nombre'), 'Mateo');
    await usuario.type(screen.getByLabelText('Apellido'), 'Prueba');
    await usuario.type(screen.getByLabelText('DNI'), '9900001a');
    await usuario.type(screen.getByLabelText('Teléfono'), '1100000002');
    await usuario.click(screen.getByRole('button', { name: 'Guardar paciente' }));
    expect(screen.getByText('El DNI tiene 7 u 8 números, sin puntos')).toBeInTheDocument();
    expect(screen.getByText('Escribí el teléfono con código de país, por ejemplo +5491100000002')).toBeInTheDocument();
    expect(screen.getByLabelText('DNI')).toHaveAttribute('aria-invalid', 'true');
    expect(api.crearPaciente).not.toHaveBeenCalled();
  });

  it('un doble toque envía un solo pedido', async () => {
    let resolver: () => void = () => undefined;
    const crearPaciente = vi.fn<Api['crearPaciente']>(() => new Promise((r) => { resolver = () => { r({ ok: true, valor: pacienteDetalle() }); }; }));
    await montar({ api: { crearPaciente } });
    await completar();
    const boton = screen.getByRole('button', { name: 'Guardar paciente' });
    await usuario.click(boton);
    await usuario.click(screen.getByRole('button', { name: 'Guardando…' }));
    expect(crearPaciente).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolver();
      await Promise.resolve();
    });
  });

  it('con un alta precargada (DNI, teléfono y nombre separado) muestra esos valores', async () => {
    await montar({ precargado: { dni: '99000003', telefono: '+5491100000003', nombre: 'Carlos', apellido: 'Sintético' } });
    expect(screen.getByLabelText('DNI')).toHaveValue('99000003');
    expect(screen.getByLabelText('Teléfono')).toHaveValue('+5491100000003');
    expect(screen.getByLabelText('Nombre')).toHaveValue('Carlos');
    expect(screen.getByLabelText('Apellido')).toHaveValue('Sintético');
  });
});

describe('Edición de datos administrativos', () => {
  it('abre precargado y al guardar muestra «Cambios guardados» y avisa el paciente nuevo', async () => {
    const editado = pacienteDetalle({ obra_social: { id: 2, nombre: 'Swiss Medical' }, numero_afiliado: 'SM-0002' });
    const editarPaciente = vi.fn<Api['editarPaciente']>().mockResolvedValue({ ok: true, valor: editado });
    const { guardado } = await montar({ paciente: pacienteDetalle({ obra_social: null, numero_afiliado: null }), api: { editarPaciente } });
    expect(screen.getByLabelText('Nombre')).toHaveValue('Lucía');
    expect(screen.getByLabelText('DNI')).toHaveValue('99000001');
    await usuario.select(screen.getByRole('combobox', { name: 'Obra social' }), 'Swiss Medical');
    await usuario.type(screen.getByLabelText('Número de afiliado (opcional)'), 'SM-0002');
    await usuario.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(editarPaciente).toHaveBeenCalledWith(7, expect.objectContaining({ obra_social_id: 2, numero_afiliado: 'SM-0002' }));
    expect(await screen.findByText('Cambios guardados')).toBeInTheDocument();
    expect(guardado).toHaveBeenCalledWith(editado);
  });

  it('una obra social desactivada mientras se edita explica qué hacer y vuelve a pedir la lista', async () => {
    const editarPaciente = vi.fn<Api['editarPaciente']>().mockResolvedValue({ ok: false, error: { tipo: 'obra_social_inactiva' } });
    const { api, guardado } = await montar({ paciente: pacienteDetalle(), api: { editarPaciente } });
    await usuario.click(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(await screen.findByText('Esa obra social ya no está activa. Elegí otra o «Sin obra social»')).toBeInTheDocument();
    expect(api.obrasSociales).toHaveBeenCalledTimes(2);
    expect(guardado).not.toHaveBeenCalled();
  });
});
