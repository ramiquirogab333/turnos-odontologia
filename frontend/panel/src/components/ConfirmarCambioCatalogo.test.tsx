import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ErrorApiPanel } from '../lib/api';
import type { ErrorCatalogo, Impacto, Resultado } from '../lib/tipos';
import { apiFalsa } from '../test/datos';
import { ConfirmarCambioCatalogo } from './ConfirmarCambioCatalogo';

const base = userEvent.setup();
const tocar = (el: Element) => act(() => base.click(el));

const OK: Resultado<null, ErrorCatalogo> = { ok: true, valor: null };

async function montar(opciones: {
  impacto?: Impacto | Error;
  alConfirmar?: () => Promise<Resultado<unknown, ErrorCatalogo>>;
  alternativa?: { etiqueta: string; alElegir: () => void };
}) {
  const impacto = opciones.impacto ?? { turnos_futuros: 0, primero: null };
  const api = apiFalsa({
    impactoCatalogo: vi.fn(() => (impacto instanceof Error ? Promise.reject(impacto) : Promise.resolve(impacto))),
  });
  const alConfirmar = vi.fn(opciones.alConfirmar ?? (() => Promise.resolve(OK)));
  const alHecho = vi.fn();
  const alVolver = vi.fn();
  await act(async () => {
    render(
      <ConfirmarCambioCatalogo
        api={api}
        recurso="disponibilidad"
        id={10}
        titulo="Quitar franja"
        donde="en esta franja"
        consecuencia="Los pacientes nuevos ya no podrán reservar en ese horario."
        confirmar="Quitar franja"
        alConfirmar={alConfirmar}
        alHecho={alHecho}
        alVolver={alVolver}
        {...(opciones.alternativa === undefined ? {} : { alternativa: opciones.alternativa })}
      />,
    );
    await Promise.resolve();
  });
  return { api, alConfirmar, alHecho, alVolver };
}

describe('ConfirmarCambioCatalogo', () => {
  it('con turnos tomados dice cuántos, que no se cancelan y qué pasa con los pacientes nuevos; al confirmar avisa que terminó', async () => {
    const { api, alConfirmar, alHecho } = await montar({ impacto: { turnos_futuros: 3, primero: '2026-11-16T14:30:00-03:00' } });
    expect(api.impactoCatalogo).toHaveBeenCalledWith('disponibilidad', 10);
    expect(screen.getByRole('dialog', { name: 'Quitar franja' })).toBeInTheDocument();
    expect(screen.getByText('Hay 3 turnos tomados en esta franja. No se cancelan: siguen en la agenda.')).toBeInTheDocument();
    expect(screen.getByText('Los pacientes nuevos ya no podrán reservar en ese horario.')).toBeInTheDocument();
    await tocar(screen.getByRole('button', { name: 'Quitar franja' }));
    expect(alConfirmar).toHaveBeenCalledTimes(1);
    expect(alHecho).toHaveBeenCalledTimes(1);
  });

  it('sin turnos alcanzados lo dice', async () => {
    await montar({ impacto: { turnos_futuros: 0, primero: null } });
    expect(screen.getByText('No hay turnos tomados en esta franja.')).toBeInTheDocument();
  });

  it('si no se pudo consultar el impacto lo dice y deja confirmar o volver', async () => {
    const { alConfirmar, alVolver } = await montar({ impacto: new ErrorApiPanel(500, 'boom', null) });
    expect(
      screen.getByText('No pudimos revisar los turnos tomados; los turnos existentes no se cancelan igual.'),
    ).toBeInTheDocument();
    await tocar(screen.getByRole('button', { name: 'Volver' }));
    expect(alVolver).toHaveBeenCalledTimes(1);
    await tocar(screen.getByRole('button', { name: 'Quitar franja' }));
    expect(alConfirmar).toHaveBeenCalledTimes(1);
  });

  it('un 409 en uso explica por qué y ofrece la alternativa de desactivar, sin dar el cambio por hecho', async () => {
    const alElegir = vi.fn();
    const { alHecho } = await montar({
      alConfirmar: () => Promise.resolve({ ok: false, error: { tipo: 'en_uso' } }),
      alternativa: { etiqueta: 'Desactivar', alElegir },
    });
    await tocar(screen.getByRole('button', { name: 'Quitar franja' }));
    expect(screen.getByRole('alert')).toHaveTextContent('No se puede borrar porque tiene turnos registrados. Podés desactivarlo para que no se ofrezca más.');
    expect(alHecho).not.toHaveBeenCalled();
    await tocar(screen.getByRole('button', { name: 'Desactivar' }));
    expect(alElegir).toHaveBeenCalledTimes(1);
  });

  it('un rechazo cualquiera se muestra como alerta y el diálogo sigue abierto', async () => {
    const { alHecho } = await montar({ alConfirmar: () => Promise.resolve({ ok: false, error: { tipo: 'desconocido' } }) });
    await tocar(screen.getByRole('button', { name: 'Quitar franja' }));
    expect(screen.getByRole('alert')).toHaveTextContent('No pudimos guardar el cambio');
    expect(alHecho).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Desactivar' })).toBeNull();
  });
});
