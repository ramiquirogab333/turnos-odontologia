import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { OdontogramaVigente, PacienteDetalle } from '../lib/tipos';
import { ACCESO_COMPLETO, ACCESO_LECTURA, apiFalsa, odontograma, pacienteClinico, pacienteDetalle } from '../test/datos';
import { Odontograma } from './Odontograma';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  select: (el: Element, v: string) => act(() => base.selectOptions(el, v)),
};

const CON_HALLAZGOS = odontograma([
  { pieza: 16, estado_pieza: null, caras: { O: 'caries' } },
  { pieza: 36, estado_pieza: 'endodoncia', caras: {} },
]);

function montar(opciones: { datos?: OdontogramaVigente; paciente?: PacienteDetalle; api?: Partial<Api> } = {}) {
  const api = apiFalsa(opciones.api);
  const alReemplazar = vi.fn<(o: OdontogramaVigente) => void>();
  const alVencer = vi.fn<() => void>();
  render(
    <Odontograma
      api={api}
      paciente={opciones.paciente ?? pacienteDetalle()}
      datos={opciones.datos ?? CON_HALLAZGOS}
      onActualizar={() => undefined}
      onReemplazar={alReemplazar}
      onAccesoVencido={alVencer}
      registrarCambios={() => undefined}
    />,
  );
  return { api, alReemplazar, alVencer };
}

describe('Estado vigente por pieza y cara', () => {
  it('la pieza 16 dice «Caries: oclusal», la 36 «Endodoncia» y las demás «Sin hallazgos»', () => {
    montar();
    expect(screen.getByRole('button', { name: '16 Caries: oclusal' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '36 Endodoncia' })).toBeInTheDocument();
    expect(screen.getAllByText('Sin hallazgos')).toHaveLength(30);
  });

  it('una pieza devuelta a sano (sin estado ni caras) dice «Sin hallazgos»', () => {
    montar({ datos: odontograma([{ pieza: 16, estado_pieza: null, caras: {} }]) });
    expect(screen.getByRole('button', { name: '16 Sin hallazgos' })).toBeInTheDocument();
  });

  it('«Temporales» muestra las piezas 51 a 85 y «Permanentes» vuelve a las 11 a 48', async () => {
    montar();
    await usuario.click(screen.getByRole('button', { name: 'Temporales' }));
    expect(screen.getByRole('button', { name: /^51 / })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^16 / })).toBeNull();
    await usuario.click(screen.getByRole('button', { name: 'Permanentes' }));
    expect(screen.getByRole('button', { name: /^16 / })).toBeInTheDocument();
  });

  it('recepción ve el estado vigente, el formulario de registro y el historial', () => {
    montar();
    expect(screen.getByRole('button', { name: 'Agregar al lote' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ver historial' })).toBeInTheDocument();
  });
});

describe('Registro de hallazgos y estado vigente', () => {
  it('al registrar un lote vuelve a pedir el estado vigente y lo muestra', async () => {
    const nuevo = odontograma([
      { pieza: 16, estado_pieza: null, caras: { O: 'caries' } },
      { pieza: 36, estado_pieza: 'endodoncia', caras: {} },
      { pieza: 11, estado_pieza: null, caras: { V: 'obturado' } },
    ]);
    const pedir = vi.fn<Api['odontograma']>().mockResolvedValue(nuevo);
    const { api, alReemplazar } = montar({ api: { odontograma: pedir } });
    await usuario.click(screen.getByRole('button', { name: '11 Sin hallazgos' }));
    await usuario.select(screen.getByLabelText('Estado'), 'Obturado');
    await usuario.select(screen.getByLabelText('Cara'), 'vestibular');
    await usuario.click(screen.getByRole('button', { name: 'Agregar al lote' }));
    await usuario.click(screen.getByRole('button', { name: 'Registrar 1 hallazgo' }));
    expect(api.registrarOdontograma).toHaveBeenCalledWith(7, [{ pieza: 11, cara: 'V', estado: 'obturado', nota: null }]);
    expect(await screen.findByRole('button', { name: '11 Obturado: vestibular' })).toBeInTheDocument();
    expect(pedir).toHaveBeenCalledWith(7);
    expect(alReemplazar).toHaveBeenCalledWith(nuevo);
  });

  it('con acceso vencido al registrar el lote queda visible y el estado vigente no cambia', async () => {
    const registrarOdontograma = vi.fn<Api['registrarOdontograma']>().mockResolvedValue({ ok: false, error: { tipo: 'acceso_vencido' } });
    const { alVencer } = montar({ api: { registrarOdontograma }, paciente: pacienteClinico() });
    await usuario.click(screen.getByRole('button', { name: '11 Sin hallazgos' }));
    await usuario.select(screen.getByLabelText('Estado'), 'Corona');
    await usuario.click(screen.getByRole('button', { name: 'Agregar al lote' }));
    await usuario.click(screen.getByRole('button', { name: 'Registrar 1 hallazgo' }));
    expect(await screen.findByText('Tu acceso para editar venció. Para editar, pedí un turno a recepción')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Lote de hallazgos' })).getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByRole('button', { name: '11 Sin hallazgos' })).toBeInTheDocument();
    expect(alVencer).toHaveBeenCalledTimes(1);
  });
});

describe('Odontograma de solo lectura', () => {
  it('con acceso de solo lectura ve el estado vigente y el historial, sin «Agregar al lote» ni «Registrar»', () => {
    montar({ paciente: pacienteClinico({ acceso_clinico: ACCESO_LECTURA }) });
    expect(screen.getByText('Caries: oclusal')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Agregar al lote' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Registrar/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Ver historial' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^16 / })).toBeNull();
  });

  it('con acceso completo de la odontóloga (el límite de 365 días es inclusivo) ve el formulario', () => {
    montar({ paciente: pacienteClinico({ acceso_clinico: ACCESO_COMPLETO }) });
    expect(screen.getByRole('button', { name: 'Agregar al lote' })).toBeInTheDocument();
  });
});
