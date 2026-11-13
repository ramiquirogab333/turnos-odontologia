import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Agenda as DatosAgenda, Opciones } from '../lib/tipos';
import { agenda, apiFalsa, SOLO_LECTURA, turno } from '../test/datos';
import { Agenda } from './Agenda';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  elegir: (el: Element, valor: string) => act(() => base.selectOptions(el, valor)),
};

async function montar(api = apiFalsa(), hoy = '2031-11-18') {
  await act(() => {
    render(<Agenda api={api} hoy={hoy} />);
    return Promise.resolve();
  });
  return api;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Agenda: carga', () => {
  it('pide la agenda y las opciones en paralelo, antes de que cualquiera responda (R2)', async () => {
    const api = apiFalsa({
      agenda: vi.fn(() => new Promise<DatosAgenda>(() => undefined)),
      opciones: vi.fn(() => new Promise<Opciones>(() => undefined)),
    });
    await montar(api);
    expect(api.agenda).toHaveBeenCalledTimes(1);
    expect(api.opciones).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent('Cargando la agenda…');
  });

  it('si falla explica qué pasó y ofrece reintentar, sin mostrar una agenda vacía', async () => {
    const api = apiFalsa({ agenda: vi.fn().mockRejectedValueOnce(new Error('x')).mockResolvedValue(agenda([turno()])) });
    await montar(api);
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('No pudimos cargar la agenda');
    expect(screen.queryByText(/No hay turnos/)).toBeNull();
    await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Carlos Sintético')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('un 403 con motivo muestra el mensaje del servidor en vez del genérico', async () => {
    const { ErrorApiPanel } = await import('../lib/api');
    const api = apiFalsa({
      agenda: vi.fn().mockRejectedValue(new ErrorApiPanel(403, 'Tu usuario todavía no está asociado a un profesional.', 'sin_profesional_asociado')),
    });
    await montar(api);
    expect(await screen.findByRole('alert')).toHaveTextContent('Tu usuario todavía no está asociado a un profesional.');
  });
});

describe('Agenda: vista día', () => {
  it('muestra hora, paciente, tratamiento, sillón y el estado como texto', async () => {
    const api = apiFalsa({
      agenda: vi.fn().mockResolvedValue(
        agenda([
          turno({ id: 1, estado: 'reservado' }),
          turno({ id: 2, estado: 'confirmado', inicio: '2031-11-18T09:30:00-03:00', fin: '2031-11-18T10:15:00-03:00', paciente_nombre: 'Lucía Ejemplo' }),
          turno({ id: 3, estado: 'atendido', inicio: '2031-11-18T10:30:00-03:00', fin: '2031-11-18T11:00:00-03:00', paciente_nombre: 'Marcos Ficticio' }),
          turno({ id: 4, estado: 'ausente', inicio: '2031-11-18T11:30:00-03:00', fin: '2031-11-18T12:00:00-03:00', paciente_nombre: 'Paula Demo', sena: { estado: 'no_reembolsado', monto: '3000.00' } }),
        ]),
      ),
    });
    await montar(api);
    const lista = await screen.findByRole('list', { name: 'Turnos del día' });
    const items = within(lista).getAllByRole('listitem');
    expect(items).toHaveLength(4);
    const primero = items[0] as HTMLElement;
    expect(primero).toHaveTextContent('09:00 a 09:30');
    expect(primero).toHaveTextContent('Carlos Sintético');
    expect(primero).toHaveTextContent('Limpieza dental');
    expect(primero).toHaveTextContent('Sillón 1');
    expect(primero).toHaveTextContent('Reservado');
    expect(primero).toHaveTextContent(/Seña acreditada: \$\s?3\.000,00/);
    expect(items[1]).toHaveTextContent('Confirmado');
    expect(items[2]).toHaveTextContent('Atendido');
    expect(items[3]).toHaveTextContent('Ausente');
    expect(items[3]).toHaveTextContent('Seña retenida');
  });

  it('muestra siempre la hora de la clínica aunque el navegador esté en otra zona', async () => {
    const api = apiFalsa({
      agenda: vi.fn().mockResolvedValue(agenda([turno({ inicio: '2031-11-18T12:00:00Z', fin: '2031-11-18T12:30:00Z' })])),
    });
    await montar(api);
    expect(await screen.findByText(/09:00 a 09:30/)).toBeInTheDocument();
  });

  it('el alta manual sin seña se rotula como tal', async () => {
    const api = apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno({ origen: 'manual', sena: null })])) });
    await montar(api);
    expect(await screen.findByText('Alta manual, sin seña')).toBeInTheDocument();
  });

  it('las pre-reservas van en una banda aparte con el aviso "No ocupan horario"', async () => {
    const api = apiFalsa({
      agenda: vi.fn().mockResolvedValue(
        agenda([
          turno({ id: 1 }),
          turno({
            id: 2, estado: 'en_espera', bloquea_agenda: false, paciente_nombre: 'Sofía Muestra',
            inicio: '2031-11-18T09:00:00-03:00', sena: { estado: 'pendiente', monto: '3000.00' }, acciones: ['cancelar'],
          }),
        ]),
      ),
    });
    await montar(api);
    const principal = await screen.findByRole('list', { name: 'Turnos del día' });
    expect(within(principal).getAllByRole('listitem')).toHaveLength(1);
    expect(within(principal).queryByText('Sofía Muestra')).toBeNull();
    const banda = screen.getByRole('region', { name: 'Pre-reservas sin pagar' });
    expect(banda).toHaveTextContent('No ocupan horario');
    expect(banda).toHaveTextContent('Sofía Muestra');
    expect(banda).toHaveTextContent('Esperando seña');
  });

  it('sin turnos invita a cargar uno', async () => {
    await montar();
    expect(await screen.findByText(/No hay turnos para este día/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Nuevo turno' })).toBeInTheDocument();
  });

  it('un turno sin datos de contacto dice "Sin datos del paciente"', async () => {
    const api = apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno({ paciente_nombre: null, paciente_telefono: null })])) });
    await montar(api);
    expect(await screen.findByText('Sin datos del paciente')).toBeInTheDocument();
  });
});

describe('Agenda: navegación y filtros', () => {
  it('Anterior, Siguiente y Hoy mueven la fecha de a un día en la vista día', async () => {
    const api = await montar();
    expect(api.agenda).toHaveBeenLastCalledWith({ vista: 'dia', fecha: '2031-11-18', profesionalId: null, sillonId: null });
    await usuario.click(screen.getByRole('button', { name: 'Día siguiente' }));
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ fecha: '2031-11-19' }));
    await usuario.click(screen.getByRole('button', { name: 'Día anterior' }));
    await usuario.click(screen.getByRole('button', { name: 'Día anterior' }));
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ fecha: '2031-11-17' }));
    await usuario.click(screen.getByRole('button', { name: 'Hoy' }));
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ fecha: '2031-11-18' }));
  });

  it('la etiqueta muestra el día completo en español', async () => {
    await montar();
    expect(await screen.findByRole('heading', { level: 2, name: 'martes 18 de noviembre' })).toBeInTheDocument();
  });

  it('la vista semana avanza de a siete días, agrupa por día y rotula el rango', async () => {
    const api = apiFalsa({
      agenda: vi.fn().mockResolvedValue(
        agenda([turno({ id: 1 }), turno({ id: 2, inicio: '2031-11-20T10:00:00-03:00', fin: '2031-11-20T10:30:00-03:00', paciente_nombre: 'Lucía Ejemplo' })], 'semana'),
      ),
    });
    await montar(api);
    await usuario.click(screen.getByRole('button', { name: 'Semana' }));
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ vista: 'semana', fecha: '2031-11-18' }));
    const dias = await screen.findAllByRole('heading', { level: 3 });
    expect(dias.map((d) => d.textContent)).toEqual(['martes 18 de noviembre', 'jueves 20 de noviembre']);
    await usuario.click(screen.getByRole('button', { name: 'Semana siguiente' }));
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ vista: 'semana', fecha: '2031-11-25' }));
  });

  it('en pantallas anchas la semana es una grilla de lunes a domingo', async () => {
    vi.stubGlobal('matchMedia', (consulta: string) => ({ matches: consulta.includes('1024'), media: consulta, addEventListener: () => undefined, removeEventListener: () => undefined }));
    const api = apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno({ id: 1 })], 'semana')) });
    await montar(api);
    await usuario.click(screen.getByRole('button', { name: 'Semana' }));
    const grilla = await screen.findByRole('table', { name: 'Semana del 17 al 23 de noviembre' });
    const columnas = within(grilla).getAllByRole('columnheader');
    expect(columnas.map((c) => c.textContent?.split(' ')[0])).toEqual(['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']);
    expect(within(grilla).getByText('Carlos Sintético')).toBeInTheDocument();
  });

  it('filtra por profesional y por sillón, y vuelve a "todos"', async () => {
    const api = await montar();
    await usuario.elegir(await screen.findByLabelText('Profesional'), 'Dr. Bruno Ejemplo');
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ profesionalId: 4, sillonId: null }));
    await usuario.elegir(screen.getByLabelText('Sillón'), 'Sillón 2');
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ profesionalId: 4, sillonId: 5 }));
    await usuario.elegir(screen.getByLabelText('Profesional'), 'Todos los profesionales');
    expect(api.agenda).toHaveBeenLastCalledWith(expect.objectContaining({ profesionalId: null, sillonId: 5 }));
  });
});

describe('Agenda: permisos', () => {
  const soloLectura = (opciones: Opciones = SOLO_LECTURA) => apiFalsa({
    opciones: vi.fn().mockResolvedValue(opciones),
    agenda: vi.fn().mockResolvedValue(agenda([turno({ acciones: [], paciente_telefono: null })])),
  });

  it('una persona de solo lectura no ve "Nuevo turno", ni acciones, ni teléfono, ni el filtro de profesional', async () => {
    await montar(soloLectura());
    expect(await screen.findByText('Carlos Sintético')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Nuevo turno' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Marcar|Cancelar turno/ })).toBeNull();
    expect(screen.queryByText('+5491144445555')).toBeNull();
    expect(screen.queryByLabelText('Profesional')).toBeNull();
  });

  it('recepción ve el teléfono y las acciones que informa el servidor', async () => {
    const api = apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno({ acciones: ['atendido', 'ausente'] })])) });
    await montar(api);
    expect(await screen.findByText('+5491144445555')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Marcar atendido' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Marcar ausente' })).toBeInTheDocument();
  });
});

describe('Agenda: alta manual y cambios', () => {
  it('"Nuevo turno" abre el formulario y al crear recarga la agenda', async () => {
    const api = await montar();
    await usuario.click(await screen.findByRole('button', { name: 'Nuevo turno' }));
    expect(screen.getByRole('dialog', { name: 'Nuevo turno' })).toBeInTheDocument();
    const llamadas = vi.mocked(api.agenda).mock.calls.length;
    await usuario.elegir(screen.getByLabelText('Tratamiento'), 'Limpieza dental');
    await usuario.elegir(screen.getByLabelText('Profesional', { selector: '#alta-profesional' }), 'Dra. Ana Ficticia');
    await usuario.click(await screen.findByRole('button', { name: '11:00' }));
    await act(async () => {
      await base.type(screen.getByLabelText('Nombre completo'), 'Carlos Sintético');
      await base.type(screen.getByLabelText('Teléfono (WhatsApp)'), '+5491144445555');
    });
    await usuario.click(screen.getByRole('button', { name: 'Crear turno' }));
    expect(await screen.findByRole('heading', { name: 'Turno creado' })).toBeInTheDocument();
    expect(vi.mocked(api.agenda).mock.calls.length).toBeGreaterThan(llamadas);
    await usuario.click(screen.getByRole('button', { name: 'Listo' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('marcar un turno recarga la agenda', async () => {
    const api = apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno({ acciones: ['atendido'] })])) });
    await montar(api);
    const antes = vi.mocked(api.agenda).mock.calls.length;
    await usuario.click(await screen.findByRole('button', { name: 'Marcar atendido' }));
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, marcar atendido' }));
    expect(api.marcar).toHaveBeenCalledWith(11, 'atendido');
    expect(vi.mocked(api.agenda).mock.calls.length).toBeGreaterThan(antes);
  });
});

describe('Agenda: Google Calendar (C-10)', () => {
  const FRANJA = { profesional_id: 1, inicio: '2031-11-18T15:00:00-03:00', fin: '2031-11-18T16:00:00-03:00' };

  it('muestra cada franja ocupada en Google como "Ocupado en Google" con su horario y sin más datos', async () => {
    const api = apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno()], 'dia', '2031-11-18', [FRANJA])) });
    await montar(api);
    const lista = await screen.findByRole('list', { name: 'Ocupado en Google' });
    const items = within(lista).getAllByRole('listitem');
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent('Ocupado en Google');
    expect(items[0]).toHaveTextContent('15:00 a 16:00');
  });

  it('muestra las franjas aunque no haya turnos ese día', async () => {
    await montar(apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([], 'dia', '2031-11-18', [FRANJA])) }));
    expect(await screen.findByRole('list', { name: 'Ocupado en Google' })).toBeInTheDocument();
    expect(screen.getByText(/No hay turnos para este día/)).toBeInTheDocument();
  });

  it('sin franjas no dibuja la lista', async () => {
    await montar(apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno()])) }));
    await screen.findByText('Carlos Sintético');
    expect(screen.queryByRole('list', { name: 'Ocupado en Google' })).toBeNull();
  });

  it('con varias profesionales rotula la franja con su nombre', async () => {
    await montar(apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([turno()], 'dia', '2031-11-18', [FRANJA])) }));
    const item = within(await screen.findByRole('list', { name: 'Ocupado en Google' })).getByRole('listitem');
    expect(item).toHaveTextContent('Dra. Ana Ficticia');
  });

  it('el turno con un conflicto abierto muestra el aviso con un enlace a la sección', async () => {
    const conflicto = turno({ calendario: { estado: 'sincronizado', conflicto_abierto: true } });
    await montar(apiFalsa({ agenda: vi.fn().mockResolvedValue(agenda([conflicto])) }));
    expect(await screen.findByText('Conflicto con Google Calendar')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver conflicto' })).toHaveAttribute('href', '#/google-calendar');
  });

  it('una pre-reserva sin conflicto y un turno sin conexión no muestran aviso', async () => {
    const api = apiFalsa({
      agenda: vi.fn().mockResolvedValue(
        agenda([
          turno({ id: 1 }),
          turno({ id: 2, estado: 'en_espera', bloquea_agenda: false, acciones: ['cancelar'], sena: { estado: 'pendiente', monto: '3000.00' } }),
        ]),
      ),
    });
    await montar(api);
    await screen.findByText('Pre-reservas sin pagar');
    expect(screen.queryByText('Conflicto con Google Calendar')).toBeNull();
    expect(screen.queryByRole('link', { name: 'Ver conflicto' })).toBeNull();
  });
});
