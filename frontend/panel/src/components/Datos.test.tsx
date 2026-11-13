import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { Rol } from '../lib/tipos';
import { apiFalsa } from '../test/datos';
import { Datos } from './Datos';

const base = userEvent.setup();
const hacer = (el: Element) => act(() => base.click(el));

async function montar(roles: readonly Rol[], pestanaInicial: 'exportar' | 'auditoria' = 'exportar') {
  const api = apiFalsa();
  await act(async () => {
    render(<Datos api={api} roles={roles} hoy="2026-11-13" pestanaInicial={pestanaInicial} />);
    await Promise.resolve();
  });
  return api;
}

describe('Datos', () => {
  it('recepción ve la exportación y no la pestaña de auditoría', async () => {
    const api = await montar(['recepcion']);
    expect(screen.getByRole('tab', { name: 'Exportar' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('tab', { name: 'Auditoría' })).toBeNull();
    expect(screen.getByLabelText('¿Qué querés exportar?')).toBeInTheDocument();
    expect(api.consultarAuditoria).not.toHaveBeenCalled();
  });

  it('el admin ve las dos pestañas y cambia a auditoría, que recién entonces consulta', async () => {
    const api = await montar(['admin']);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Exportar', 'Auditoría']);
    expect(api.consultarAuditoria).not.toHaveBeenCalled();
    await hacer(screen.getByRole('tab', { name: 'Auditoría' }));
    expect(screen.getByRole('tab', { name: 'Auditoría' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('No hay registros para estos filtros')).toBeInTheDocument();
    expect(api.consultarAuditoria).toHaveBeenCalledTimes(1);
  });

  it('si recepción fuerza la ruta de auditoría recibe el mensaje de permiso y no se consulta nada', async () => {
    const api = await montar(['recepcion'], 'auditoria');
    expect(screen.getByText('No tenés permiso para ver la auditoría.')).toBeInTheDocument();
    expect(api.consultarAuditoria).not.toHaveBeenCalled();
    expect(api.listarUsuarios).not.toHaveBeenCalled();
  });

  it('con roles recepción y admin vale el permiso más amplio', async () => {
    await montar(['recepcion', 'admin']);
    expect(screen.getByRole('tab', { name: 'Auditoría' })).toBeInTheDocument();
  });
});
