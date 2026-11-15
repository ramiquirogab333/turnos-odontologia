import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ErrorApiPanel, type Api } from '../lib/api';
import type { RegistroOdontograma } from '../lib/tipos';
import { apiFalsa, registroOdonto } from '../test/datos';
import { HistorialOdontograma } from './HistorialOdontograma';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

/** `n` registros con ids descendentes desde `desde` (del más reciente al más antiguo). */
const registros = (desde: number, n: number): RegistroOdontograma[] =>
  Array.from({ length: n }, (_, i) => registroOdonto({ id: desde - i, pieza: 16, nota: `Registro ${String(desde - i)} (sintético)` }));

function montar(historial: Api['historialOdontograma']) {
  const api = apiFalsa({ historialOdontograma: vi.fn<Api['historialOdontograma']>(historial) });
  render(<HistorialOdontograma api={api} pacienteId={7} />);
  return api;
}

describe('Historial del odontograma', () => {
  it('abre con 50 registros y «Cargar más» suma los 10 restantes sin repetir', async () => {
    const api = montar((_, antes) =>
      Promise.resolve(antes === null ? { registros: registros(60, 50), siguiente_antes_de_id: 11 } : { registros: registros(10, 10), siguiente_antes_de_id: null }),
    );
    await usuario.click(screen.getByRole('button', { name: 'Ver historial' }));
    const lista = await screen.findByRole('list', { name: 'Historial de hallazgos' });
    expect(within(lista).getAllByRole('listitem')).toHaveLength(50);
    await usuario.click(screen.getByRole('button', { name: 'Cargar más' }));
    await within(await screen.findByRole('list', { name: 'Historial de hallazgos' })).findByText(/Registro 1 \(sintético\)/);
    const items = within(screen.getByRole('list', { name: 'Historial de hallazgos' })).getAllByRole('listitem');
    expect(items).toHaveLength(60);
    expect(new Set(items.map((li) => li.textContent)).size).toBe(60);
    expect(items[0]).toHaveTextContent('Registro 60');
    expect(screen.queryByRole('button', { name: 'Cargar más' })).toBeNull();
    expect(api.historialOdontograma).toHaveBeenNthCalledWith(1, 7, null);
    expect(api.historialOdontograma).toHaveBeenNthCalledWith(2, 7, 11);
  });

  it('un registro repetido entre páginas no se muestra dos veces', async () => {
    montar((_, antes) =>
      Promise.resolve(antes === null ? { registros: registros(3, 2), siguiente_antes_de_id: 2 } : { registros: registros(2, 2), siguiente_antes_de_id: null }),
    );
    await usuario.click(screen.getByRole('button', { name: 'Ver historial' }));
    await screen.findByRole('list', { name: 'Historial de hallazgos' });
    await usuario.click(screen.getByRole('button', { name: 'Cargar más' }));
    await within(screen.getByRole('list', { name: 'Historial de hallazgos' })).findByText(/Registro 1 /);
    expect(within(screen.getByRole('list', { name: 'Historial de hallazgos' })).getAllByRole('listitem')).toHaveLength(3);
  });

  it('si falla la segunda página conserva lo cargado y ofrece reintentar', async () => {
    let llamadas = 0;
    montar((_, antes) => {
      llamadas += 1;
      if (antes === null) return Promise.resolve({ registros: registros(60, 50), siguiente_antes_de_id: 11 });
      return llamadas === 2 ? Promise.reject(new ErrorApiPanel(500, 'x', null)) : Promise.resolve({ registros: registros(10, 10), siguiente_antes_de_id: null });
    });
    await usuario.click(screen.getByRole('button', { name: 'Ver historial' }));
    await screen.findByRole('list', { name: 'Historial de hallazgos' });
    await usuario.click(screen.getByRole('button', { name: 'Cargar más' }));
    expect(await screen.findByText('No pudimos cargar más registros')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Historial de hallazgos' })).getAllByRole('listitem')).toHaveLength(50);
    await usuario.click(screen.getByRole('button', { name: 'Reintentar' }));
    await within(await screen.findByRole('list', { name: 'Historial de hallazgos' })).findByText(/Registro 1 /);
    expect(within(screen.getByRole('list', { name: 'Historial de hallazgos' })).getAllByRole('listitem')).toHaveLength(60);
  });

  it('un paciente sin registros dice que no hay hallazgos y no ofrece «Cargar más»', async () => {
    montar(() => Promise.resolve({ registros: [], siguiente_antes_de_id: null }));
    await usuario.click(screen.getByRole('button', { name: 'Ver historial' }));
    expect(await screen.findByText('Todavía no hay hallazgos registrados')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cargar más' })).toBeNull();
  });

  it('si falla la primera página ofrece reintentar y no muestra la lista vacía', async () => {
    const historial = vi.fn<Api['historialOdontograma']>().mockRejectedValueOnce(new ErrorApiPanel(500, 'x', null)).mockResolvedValue({ registros: registros(2, 1), siguiente_antes_de_id: null });
    const api = apiFalsa({ historialOdontograma: historial });
    render(<HistorialOdontograma api={api} pacienteId={7} />);
    await usuario.click(screen.getByRole('button', { name: 'Ver historial' }));
    expect(await screen.findByText('No pudimos cargar el historial')).toBeInTheDocument();
    expect(screen.queryByText('Todavía no hay hallazgos registrados')).toBeNull();
    await usuario.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText(/Registro 2 /)).toBeInTheDocument();
  });

  it('cada registro muestra fecha y hora de la clínica, pieza, cara, estado y nota', async () => {
    montar(() => Promise.resolve({ registros: [registroOdonto({ id: 5, pieza: 36, cara: null, estado: 'endodoncia', nota: 'Conducto (sintético)' })], siguiente_antes_de_id: null }));
    await usuario.click(screen.getByRole('button', { name: 'Ver historial' }));
    const item = within(await screen.findByRole('list', { name: 'Historial de hallazgos' })).getByRole('listitem');
    expect(item).toHaveTextContent('18/11');
    expect(item).toHaveTextContent('09:00');
    expect(item).toHaveTextContent('36');
    expect(item).toHaveTextContent('Endodoncia');
    expect(item).toHaveTextContent('Conducto (sintético)');
  });
});
