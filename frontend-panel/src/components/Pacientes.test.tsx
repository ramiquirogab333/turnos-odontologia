import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { ConsultaPacientes, ListadoPacientes } from '../lib/tipos';
import { apiFalsa, listado, pacienteListado } from '../test/datos';
import { Pacientes } from './Pacientes';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

const LUCIA = pacienteListado();
const MARTIN = pacienteListado({ id: 9, nombre: 'Martín', apellido: 'Prueba', dni: '28999888', atendidos: 5, ausentes: 0, ultimo_turno: null });

type Responder = (consulta: ConsultaPacientes) => Promise<ListadoPacientes>;

/** Monta la pantalla con un listado espía tipado; devuelve el espía para mirar con qué se consultó. */
async function montar(responder: Responder = () => Promise.resolve(listado([LUCIA, MARTIN]))) {
  const listar = vi.fn<Api['listarPacientes']>(responder);
  await act(async () => {
    render(<Pacientes api={apiFalsa({ listarPacientes: listar })} esperaMs={40} />);
    await Promise.resolve();
  });
  return listar;
}

const consultas = (listar: ReturnType<typeof vi.fn<Api['listarPacientes']>>) => listar.mock.calls.map((c) => c[0]);

describe('Pantalla de pacientes', () => {
  it('abre con la primera página: nombre, DNI y ausencias de cada persona', async () => {
    const listar = await montar();
    const lista = await screen.findByRole('list', { name: 'Pacientes' });
    expect(within(lista).getByText('Lucía Ejemplo')).toBeInTheDocument();
    expect(within(lista).getByText(/DNI 30111222/)).toBeInTheDocument();
    expect(within(lista).getByText(/1 ausencia\b/)).toBeInTheDocument();
    expect(within(lista).getByText(/0 ausencias/)).toBeInTheDocument();
    expect(consultas(listar)).toEqual([{ q: null, pagina: 1, porPagina: 20, conAusencias: false }]);
  });

  it('escribir "lucia" consulta una sola vez, tras la espera, y muestra a Lucía Ejemplo', async () => {
    const listar = await montar((c) => Promise.resolve(c.q === 'lucia' ? listado([LUCIA]) : listado([LUCIA, MARTIN])));
    await screen.findByText('Martín Prueba');
    await usuario.type(screen.getByRole('searchbox', { name: 'Buscar por nombre, apellido o DNI' }), 'lucia');
    await waitFor(() => {
      expect(consultas(listar).filter((c) => c.q !== null)).toEqual([{ q: 'lucia', pagina: 1, porPagina: 20, conAusencias: false }]);
    });
    await waitFor(() => {
      expect(screen.queryByText('Martín Prueba')).toBeNull();
    });
    expect(screen.getByText('Lucía Ejemplo')).toBeInTheDocument();
  });

  it('una sola letra no consulta: el servidor pide al menos dos', async () => {
    const listar = await montar();
    await screen.findByText('Lucía Ejemplo');
    await usuario.type(screen.getByRole('searchbox'), 'l');
    await act(() => new Promise((r) => setTimeout(r, 120)));
    expect(consultas(listar)).toHaveLength(1);
    expect(screen.getByText(/al menos 2 letras/)).toBeInTheDocument();
  });

  it('«Con ausencias» filtra y vuelve a la primera página', async () => {
    const listar = await montar();
    await screen.findByText('Lucía Ejemplo');
    const filtro = screen.getByRole('button', { name: 'Con ausencias' });
    expect(filtro).toHaveAttribute('aria-pressed', 'false');
    await usuario.click(filtro);
    await waitFor(() => {
      expect(consultas(listar).at(-1)).toEqual({ q: null, pagina: 1, porPagina: 20, conAusencias: true });
    });
    expect(screen.getByRole('button', { name: 'Con ausencias' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('pagina: muestra "Página 1 de 3", pide la siguiente y deshabilita los extremos', async () => {
    const listar = await montar((c) => Promise.resolve(listado([LUCIA], { total: 45, pagina: c.pagina })));
    await screen.findByText('Página 1 de 3');
    expect(screen.getByRole('button', { name: 'Página anterior' })).toBeDisabled();
    await usuario.click(screen.getByRole('button', { name: 'Página siguiente' }));
    await screen.findByText('Página 2 de 3');
    expect(consultas(listar).at(-1)?.pagina).toBe(2);
    await usuario.click(screen.getByRole('button', { name: 'Página siguiente' }));
    await screen.findByText('Página 3 de 3');
    expect(screen.getByRole('button', { name: 'Página siguiente' })).toBeDisabled();
  });

  it('una sola página no muestra la paginación', async () => {
    await montar();
    await screen.findByText('Lucía Ejemplo');
    expect(screen.queryByRole('button', { name: 'Página siguiente' })).toBeNull();
  });

  it('sin resultados dice qué se buscó y sugiere buscar por DNI', async () => {
    await montar((c) => Promise.resolve(c.q === 'zzz' ? listado([]) : listado([LUCIA])));
    await screen.findByText('Lucía Ejemplo');
    await usuario.type(screen.getByRole('searchbox'), 'zzz');
    expect(await screen.findByText('No encontramos pacientes con «zzz»')).toBeInTheDocument();
    expect(screen.getByText(/buscá por DNI/)).toBeInTheDocument();
  });

  it('sin pacientes cargados explica de dónde salen', async () => {
    await montar(() => Promise.resolve(listado([])));
    expect(await screen.findByText(/Todavía no hay pacientes/)).toBeInTheDocument();
  });

  it('si falla la carga ofrece reintentar y se recupera', async () => {
    let llamadas = 0;
    await montar(() => {
      llamadas += 1;
      return llamadas === 1 ? Promise.reject(new Error('sin red')) : Promise.resolve(listado([LUCIA]));
    });
    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent('No pudimos cargar los pacientes');
    await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Lucía Ejemplo')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
