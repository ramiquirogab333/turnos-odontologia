import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { CatalogoAdmin } from '../lib/tipos';
import { apiFalsa, catalogoAdmin, franjaAdmin, profesionalAdmin, sillonAdmin } from '../test/datos';
import { HorariosCatalogo } from './HorariosCatalogo';

const base = userEvent.setup();
const tocar = (el: Element) => act(() => base.click(el));
const elegir = (el: Element, valor: string) => act(() => base.selectOptions(el, valor));
const poner = async (el: Element, texto: string) => {
  await act(() => base.clear(el));
  await act(() => base.type(el, texto));
};

function Envoltorio({ api, inicial }: { readonly api: Api; readonly inicial: CatalogoAdmin }) {
  const [datos, setDatos] = useState(inicial);
  const [aviso, setAviso] = useState('');
  return (
    <>
      <p data-testid="aviso">{aviso}</p>
      <HorariosCatalogo api={api} datos={datos} cambiar={setDatos} avisar={setAviso} />
    </>
  );
}

async function montar(api: Api, datos: CatalogoAdmin = catalogoAdmin()) {
  await act(async () => {
    render(<Envoltorio api={api} inicial={datos} />);
    await Promise.resolve();
  });
}

const dia = (nombre: string) => screen.getByRole('region', { name: nombre });

describe('HorariosCatalogo: lectura', () => {
  it('muestra un bloque por día de lunes a domingo; el que no tiene franjas dice "Sin atención este día"', async () => {
    await montar(apiFalsa());
    const nombres = screen.getAllByRole('region').map((r) => within(r).getByRole('heading').textContent);
    expect(nombres).toEqual(['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']);
    expect(within(dia('Lunes')).getByText('09:00 a 13:00')).toBeInTheDocument();
    expect(within(dia('Lunes')).getByText('Activa')).toBeInTheDocument();
    expect(within(dia('Martes')).getByText('Sin atención este día')).toBeInTheDocument();
    expect(within(dia('Lunes')).queryByText('Sin atención este día')).toBeNull();
  });

  it('las horas se leen como llegan (hora de la clínica) y el sillón preferido se nombra', async () => {
    const datos = catalogoAdmin({ franjas: [franjaAdmin({ hora_inicio: '14:00:00', hora_fin: '18:30:00', sillon_defecto_id: 5 })] });
    await montar(apiFalsa(), datos);
    expect(within(dia('Lunes')).getByText('14:00 a 18:30')).toBeInTheDocument();
    expect(within(dia('Lunes')).getByText('Sillón 2')).toBeInTheDocument();
  });

  it('solo muestra las franjas de la profesional elegida', async () => {
    const datos = catalogoAdmin({
      profesionales: [profesionalAdmin(), profesionalAdmin({ id: 2, nombre: 'Dr. Juan Ejemplo', matricula: 'MP-99002' })],
      franjas: [franjaAdmin(), franjaAdmin({ id: 11, profesional_id: 2, dia_semana: 3, hora_inicio: '15:00:00', hora_fin: '19:00:00' })],
    });
    await montar(apiFalsa(), datos);
    expect(within(dia('Jueves')).getByText('Sin atención este día')).toBeInTheDocument();
    await elegir(screen.getByLabelText('Profesional'), '2');
    expect(within(dia('Jueves')).getByText('15:00 a 19:00')).toBeInTheDocument();
    expect(within(dia('Lunes')).getByText('Sin atención este día')).toBeInTheDocument();
  });

  it('sin profesionales cargadas pide cargar una primero', async () => {
    await montar(apiFalsa(), catalogoAdmin({ profesionales: [], franjas: [] }));
    expect(screen.getByText(/Primero cargá una profesional/)).toBeInTheDocument();
    expect(screen.queryAllByRole('region')).toHaveLength(0);
  });
});

describe('HorariosCatalogo: agregar', () => {
  it('agrega una franja el martes de 09:00 a 13:00 con sillón preferido y queda "Activa"', async () => {
    const nueva = franjaAdmin({ id: 20, dia_semana: 1, hora_inicio: '09:00:00', hora_fin: '13:00:00', sillon_defecto_id: 2 });
    const api = apiFalsa({ crearCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: nueva }) });
    await montar(api);
    await tocar(within(dia('Martes')).getByRole('button', { name: 'Agregar franja' }));
    await poner(screen.getByLabelText('Desde'), '09:00');
    await poner(screen.getByLabelText('Hasta'), '13:00');
    await elegir(screen.getByLabelText('Sillón preferido'), '2');
    await tocar(screen.getByRole('button', { name: 'Guardar franja' }));
    expect(api.crearCatalogo).toHaveBeenCalledWith('disponibilidad', {
      profesional_id: 1,
      dia_semana: 1,
      hora_inicio: '09:00',
      hora_fin: '13:00',
      sillon_defecto_id: 2,
    });
    expect(within(dia('Martes')).getByText('09:00 a 13:00')).toBeInTheDocument();
    expect(within(dia('Martes')).getByText('Activa')).toBeInTheDocument();
    expect(within(dia('Martes')).queryByText('Sin atención este día')).toBeNull();
  });

  it('una franja que se pisa con otra dice con cuál, conserva lo escrito y no crea nada', async () => {
    const api = apiFalsa({
      crearCatalogo: vi.fn().mockResolvedValue({
        ok: false,
        error: { tipo: 'franja_superpuesta', franja: { id: 10, dia_semana: 0, hora_inicio: '09:00:00', hora_fin: '13:00:00' } },
      }),
    });
    await montar(api);
    await tocar(within(dia('Lunes')).getByRole('button', { name: 'Agregar franja' }));
    await poner(screen.getByLabelText('Desde'), '12:00');
    await poner(screen.getByLabelText('Hasta'), '15:00');
    await tocar(screen.getByRole('button', { name: 'Guardar franja' }));
    expect(screen.getByText('Se superpone con la franja de 09:00 a 13:00 del lunes')).toBeInTheDocument();
    expect(screen.getByLabelText('Desde')).toHaveValue('12:00');
    expect(screen.getByLabelText('Hasta')).toHaveValue('15:00');
    expect(within(dia('Lunes')).getAllByText(/^\d\d:\d\d a \d\d:\d\d$/)).toHaveLength(1);
  });

  it('dos franjas contiguas conviven y se listan en orden de inicio', async () => {
    const tarde = franjaAdmin({ id: 21, hora_inicio: '13:00:00', hora_fin: '17:00:00' });
    const api = apiFalsa({ crearCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: tarde }) });
    await montar(api, catalogoAdmin({ franjas: [franjaAdmin({ id: 10, hora_inicio: '09:00:00', hora_fin: '13:00:00' })] }));
    await tocar(within(dia('Lunes')).getByRole('button', { name: 'Agregar franja' }));
    await poner(screen.getByLabelText('Desde'), '13:00');
    await poner(screen.getByLabelText('Hasta'), '17:00');
    await tocar(screen.getByRole('button', { name: 'Guardar franja' }));
    const horas = within(dia('Lunes')).getAllByText(/\d\d:\d\d a \d\d:\d\d/).map((e) => e.textContent);
    expect(horas).toEqual(['09:00 a 13:00', '13:00 a 17:00']);
  });

  it('una hora de fin anterior al inicio se corrige en el campo sin llamar al servidor', async () => {
    const api = apiFalsa();
    await montar(api);
    await tocar(within(dia('Martes')).getByRole('button', { name: 'Agregar franja' }));
    await poner(screen.getByLabelText('Desde'), '13:00');
    await poner(screen.getByLabelText('Hasta'), '09:00');
    await tocar(screen.getByRole('button', { name: 'Guardar franja' }));
    expect(screen.getByText('La hora de fin tiene que ser posterior a la de inicio')).toBeInTheDocument();
    expect(api.crearCatalogo).not.toHaveBeenCalled();
  });

  it('un doble toque en guardar sale como un solo pedido de alta', async () => {
    let resolver: (v: { ok: true; valor: ReturnType<typeof franjaAdmin> }) => void = () => undefined;
    const api = apiFalsa({
      crearCatalogo: vi.fn(
        () =>
          new Promise((r) => {
            resolver = r;
          }),
      ) as unknown as Api['crearCatalogo'],
    });
    await montar(api);
    await tocar(within(dia('Martes')).getByRole('button', { name: 'Agregar franja' }));
    await poner(screen.getByLabelText('Desde'), '09:00');
    await poner(screen.getByLabelText('Hasta'), '13:00');
    await act(async () => {
      await base.dblClick(screen.getByRole('button', { name: 'Guardar franja' }));
    });
    expect(api.crearCatalogo).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled();
    await act(async () => {
      resolver({ ok: true, valor: franjaAdmin({ id: 22, dia_semana: 1 }) });
      await Promise.resolve();
    });
    expect(within(dia('Martes')).getAllByText(/^\d\d:\d\d a \d\d:\d\d$/)).toHaveLength(1);
  });
});

describe('HorariosCatalogo: pausar, reactivar, editar y quitar', () => {
  it('pausar muestra el impacto, guarda activo=false y la franja queda "Pausada"', async () => {
    const api = apiFalsa({
      impactoCatalogo: vi.fn().mockResolvedValue({ turnos_futuros: 3, primero: '2031-11-17T14:30:00-03:00' }),
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: franjaAdmin({ activo: false }) }),
    });
    await montar(api);
    await tocar(within(dia('Lunes')).getByRole('button', { name: 'Pausar franja' }));
    expect(await screen.findByText('Hay 3 turnos tomados en esta franja. No se cancelan: siguen en la agenda.')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Pausar franja' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('disponibilidad', 10, { activo: false });
    expect(within(dia('Lunes')).getByText('Pausada')).toBeInTheDocument();
  });

  it('reactivar una franja que se superpone con otra muestra el motivo y la deja pausada', async () => {
    const api = apiFalsa({
      actualizarCatalogo: vi.fn().mockResolvedValue({
        ok: false,
        error: { tipo: 'franja_superpuesta', franja: { id: 11, dia_semana: 0, hora_inicio: '09:00:00', hora_fin: '13:00:00' } },
      }),
    });
    await montar(api, catalogoAdmin({ franjas: [franjaAdmin({ activo: false, hora_inicio: '12:00:00', hora_fin: '15:00:00' })] }));
    await tocar(screen.getByRole('button', { name: 'Reactivar franja' }));
    expect(screen.getByTestId('aviso')).toHaveTextContent('Se superpone con la franja de 09:00 a 13:00 del lunes');
    expect(within(dia('Lunes')).getByText('Pausada')).toBeInTheDocument();
  });

  it('reactivar una franja sin conflicto la deja "Activa" sin pedir confirmación', async () => {
    const api = apiFalsa({ actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: franjaAdmin({ activo: true }) }) });
    await montar(api, catalogoAdmin({ franjas: [franjaAdmin({ activo: false })] }));
    await tocar(screen.getByRole('button', { name: 'Reactivar franja' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('disponibilidad', 10, { activo: true });
    expect(api.impactoCatalogo).not.toHaveBeenCalled();
    expect(within(dia('Lunes')).getByText('Activa')).toBeInTheDocument();
  });

  it('quitar una franja con 3 turnos lo explica y, al confirmar, desaparece de la lista', async () => {
    const api = apiFalsa({ impactoCatalogo: vi.fn().mockResolvedValue({ turnos_futuros: 3, primero: '2031-11-17T14:30:00-03:00' }) });
    await montar(api, catalogoAdmin({ franjas: [franjaAdmin({ hora_inicio: '14:00:00', hora_fin: '18:00:00' })] }));
    await tocar(within(dia('Lunes')).getByRole('button', { name: 'Quitar franja' }));
    expect(await screen.findByText('Hay 3 turnos tomados en esta franja. No se cancelan: siguen en la agenda.')).toBeInTheDocument();
    expect(screen.getByText('Los pacientes nuevos ya no podrán reservar en ese horario.')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Quitar franja' }));
    expect(api.borrarCatalogo).toHaveBeenCalledWith('disponibilidad', 10);
    expect(within(dia('Lunes')).getByText('Sin atención este día')).toBeInTheDocument();
  });

  it('cambiar el horario de una franja pide confirmar con el impacto y guarda las horas nuevas', async () => {
    const api = apiFalsa({
      impactoCatalogo: vi.fn().mockResolvedValue({ turnos_futuros: 1, primero: '2031-11-17T12:30:00-03:00' }),
      actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: franjaAdmin({ hora_fin: '12:00:00' }) }),
    });
    await montar(api);
    await tocar(within(dia('Lunes')).getByRole('button', { name: 'Editar' }));
    await poner(screen.getByLabelText('Hasta'), '12:00');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(api.actualizarCatalogo).not.toHaveBeenCalled();
    expect(await screen.findByText('Hay 1 turno tomado en esta franja. No se cancela: sigue en la agenda.')).toBeInTheDocument();
    await tocar(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmar cambio' }));
    expect(api.actualizarCatalogo).toHaveBeenCalledWith('disponibilidad', 10, {
      dia_semana: 0,
      hora_inicio: '09:00',
      hora_fin: '12:00',
      sillon_defecto_id: null,
    });
    expect(within(dia('Lunes')).getByText('09:00 a 12:00')).toBeInTheDocument();
  });

  it('cambiar solo el sillón preferido guarda directo, sin diálogo', async () => {
    const api = apiFalsa({ actualizarCatalogo: vi.fn().mockResolvedValue({ ok: true, valor: franjaAdmin({ sillon_defecto_id: 5 }) }) });
    await montar(api, catalogoAdmin({ sillones: [sillonAdmin(), sillonAdmin({ id: 5, nombre: 'Sillón 2' })] }));
    await tocar(within(dia('Lunes')).getByRole('button', { name: 'Editar' }));
    await elegir(screen.getByLabelText('Sillón preferido'), '5');
    await tocar(screen.getByRole('button', { name: 'Guardar cambios' }));
    expect(api.impactoCatalogo).not.toHaveBeenCalled();
    expect(within(dia('Lunes')).getByText('Sillón 2')).toBeInTheDocument();
  });
});
