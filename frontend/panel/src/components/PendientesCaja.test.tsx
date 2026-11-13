import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ErrorCaja, Resultado } from '../lib/tipos';
import { ACREDITACION, apiFalsa, pendiente } from '../test/datos';
import { PendientesCaja } from './PendientesCaja';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

const REVISION = pendiente();
const SENA = pendiente({ tipo: 'sena', id: 6, pago_id: 6, turno_id: 10, estado_turno: 'cancelado', importe: '3000.00' });
const EXCEDENTE = pendiente({ tipo: 'excedente_mp', id: 7, pago_id: 6, turno_id: 10, importe: '1500.00', mp_payment_id: 'MP-SINT-9' });

function montar(pendientes: Parameters<typeof PendientesCaja>[0]['pendientes'], api = apiFalsa(), onCambio = vi.fn()) {
  render(<PendientesCaja pendientes={pendientes} api={api} onCambio={onCambio} />);
  return { api, onCambio };
}

const rechazo = (error: ErrorCaja): Resultado<never, ErrorCaja> => ({ ok: false, error });

describe('Pantalla de pendientes de la seña', () => {
  it('sin pendientes dice que no hay pagos por resolver', () => {
    montar([]);
    expect(screen.getByText('No hay pagos por resolver')).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('cada tipo ofrece sus acciones: revisión acredita o rechaza; seña y excedente registran la devolución', () => {
    montar([REVISION, SENA, EXCEDENTE]);
    const [revision, sena, excedente] = screen.getAllByRole('listitem');
    expect(within(revision as HTMLElement).getByRole('button', { name: 'Acreditar' })).toBeInTheDocument();
    expect(within(revision as HTMLElement).getByRole('button', { name: 'Rechazar' })).toBeInTheDocument();
    expect(within(sena as HTMLElement).getByRole('button', { name: 'Registrar devolución' })).toBeInTheDocument();
    expect(within(sena as HTMLElement).queryByRole('button', { name: 'Acreditar' })).toBeNull();
    expect(within(excedente as HTMLElement).getByRole('button', { name: 'Registrar devolución' })).toBeInTheDocument();
  });

  it('cada pago dice qué es y de cuánto', () => {
    montar([REVISION, SENA, EXCEDENTE]);
    expect(screen.getByText(/Pago en revisión: \$ 2\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/Seña a devolver: \$ 3\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/Pago de más a devolver: \$ 1\.500,00/)).toBeInTheDocument();
  });

  it('si la pasarela no informó el importe lo dice en vez de inventarlo', () => {
    montar([pendiente({ importe: null, importe_a_verificar: true })]);
    expect(screen.getByText(/importe a verificar/i)).toBeInTheDocument();
    expect(screen.queryByText(/\$ 0,00/)).toBeNull();
  });

  describe('acreditar', () => {
    it('el diálogo dice qué pasa con el dinero y el turno, y no hace nada hasta confirmar', async () => {
      const { api } = montar([REVISION]);
      await usuario.click(screen.getByRole('button', { name: 'Acreditar' }));
      const dialogo = screen.getByRole('dialog', { name: '¿Acreditar el pago de $ 2.000,00?' });
      expect(dialogo).toHaveTextContent('se acepta como seña');
      expect(dialogo).toHaveTextContent('el turno pasa a reservado');
      expect(dialogo).toHaveTextContent('queda a devolver');
      expect(api.acreditarRevision).not.toHaveBeenCalled();
    });

    it('confirmar acredita el pago, avisa el cambio y cierra', async () => {
      const { api, onCambio } = montar([REVISION]);
      await usuario.click(screen.getByRole('button', { name: 'Acreditar' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, acreditar el pago' }));
      expect(api.acreditarRevision).toHaveBeenCalledWith(5);
      expect(onCambio).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  describe('rechazar', () => {
    it('el diálogo dice que el dinero queda a devolver y que el turno no cambia', async () => {
      montar([REVISION]);
      await usuario.click(screen.getByRole('button', { name: 'Rechazar' }));
      const dialogo = screen.getByRole('dialog', { name: '¿Rechazar el pago de $ 2.000,00?' });
      expect(dialogo).toHaveTextContent('queda a devolver');
      expect(dialogo).toHaveTextContent('El turno no cambia');
    });

    it('confirmar rechaza el pago y avisa el cambio', async () => {
      const { api, onCambio } = montar([REVISION]);
      await usuario.click(screen.getByRole('button', { name: 'Rechazar' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, rechazar el pago' }));
      expect(api.rechazarRevision).toHaveBeenCalledWith(5);
      expect(onCambio).toHaveBeenCalledTimes(1);
    });
  });

  describe('registrar la devolución', () => {
    async function abrir(item: typeof SENA) {
      const resultado = montar([item]);
      await usuario.click(screen.getByRole('button', { name: 'Registrar devolución' }));
      return resultado;
    }

    it('el diálogo dice que la seña pasa a devuelta y que se resta de la caja', async () => {
      await abrir(SENA);
      const dialogo = screen.getByRole('dialog', { name: '¿Registrar la devolución de $ 3.000,00?' });
      expect(dialogo).toHaveTextContent('Seña devuelta');
      expect(dialogo).toHaveTextContent('egreso de la caja de hoy');
      expect(within(dialogo).getByLabelText('Referencia de la devolución')).toBeInTheDocument();
    });

    it('un excedente avisa que no mueve la caja', async () => {
      await abrir(EXCEDENTE);
      const dialogo = screen.getByRole('dialog', { name: '¿Registrar la devolución de $ 1.500,00?' });
      expect(dialogo).toHaveTextContent('no mueve la caja');
    });

    it.each(['', '   ', 'ab'])('la referencia "%s" no se envía y dice qué escribir', async (texto) => {
      const { api } = await abrir(SENA);
      const dialogo = screen.getByRole('dialog');
      if (texto.trim() !== '') await usuario.type(within(dialogo).getByLabelText('Referencia de la devolución'), texto);
      await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, registrar la devolución' }));
      expect(screen.getByRole('alert')).toHaveTextContent('Escribí la referencia de la devolución (el número de operación)');
      expect(api.registrarDevolucion).not.toHaveBeenCalled();
      expect(api.registrarDevolucionExcedente).not.toHaveBeenCalled();
    });

    it('con referencia registra la devolución de la seña sin espacios sobrantes', async () => {
      const { api, onCambio } = await abrir(SENA);
      const dialogo = screen.getByRole('dialog');
      await usuario.type(within(dialogo).getByLabelText('Referencia de la devolución'), '  DEV-SINT-0001 ');
      await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, registrar la devolución' }));
      expect(api.registrarDevolucion).toHaveBeenCalledWith(6, 'DEV-SINT-0001');
      expect(api.registrarDevolucionExcedente).not.toHaveBeenCalled();
      expect(onCambio).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('dialog')).toBeNull();
    });

    it('un excedente se registra por el id de su aprobación', async () => {
      const { api } = await abrir(EXCEDENTE);
      const dialogo = screen.getByRole('dialog');
      await usuario.type(within(dialogo).getByLabelText('Referencia de la devolución'), 'DEV-SINT-0002');
      await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, registrar la devolución' }));
      expect(api.registrarDevolucionExcedente).toHaveBeenCalledWith(7, 'DEV-SINT-0002');
      expect(api.registrarDevolucion).not.toHaveBeenCalled();
    });
  });

  describe('rechazos del servidor', () => {
    async function acreditarConRechazo(error: ErrorCaja) {
      const api = apiFalsa({ acreditarRevision: vi.fn().mockResolvedValue(rechazo(error)) });
      const onCambio = vi.fn();
      montar([REVISION], api, onCambio);
      await usuario.click(screen.getByRole('button', { name: 'Acreditar' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, acreditar el pago' }));
      return { api, onCambio };
    }

    it('caja_cerrada dice qué día está cerrado y cómo seguir, sin recargar', async () => {
      const { onCambio } = await acreditarConRechazo({ tipo: 'caja_cerrada', dia: '2031-11-17' });
      const alerta = screen.getByRole('alert');
      expect(alerta).toHaveTextContent('17 de noviembre');
      expect(alerta).toHaveTextContent('está cerrada');
      expect(alerta).toHaveTextContent('anule el cierre');
      expect(onCambio).not.toHaveBeenCalled();
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('estado_cambiado avisa que el pago ya cambió y recarga la lista', async () => {
      const { onCambio } = await acreditarConRechazo({ tipo: 'estado_cambiado' });
      expect(screen.getByRole('alert')).toHaveTextContent('Este pago ya cambió de estado. Actualizamos la lista.');
      expect(onCambio).toHaveBeenCalledTimes(1);
    });

    it.each([
      [{ tipo: 'no_encontrado' }, 'Ese pago ya no existe. Actualizamos la lista.', 1],
      [{ tipo: 'sin_permiso' }, 'Tu usuario no puede hacer este cambio.', 0],
      [{ tipo: 'reintentar' }, 'El servidor está ocupado. Probá de nuevo en unos segundos.', 0],
      [{ tipo: 'validacion', mensaje: 'La fecha no puede ser futura' }, 'La fecha no puede ser futura', 0],
      [{ tipo: 'desconocido' }, 'No pudimos guardar el cambio. Probá de nuevo; si sigue igual, avisá a la clínica.', 0],
    ] as const)('%j muestra "%s"', async (error, texto, recargas) => {
      const { onCambio } = await acreditarConRechazo(error);
      expect(screen.getByRole('alert')).toHaveTextContent(texto);
      expect(onCambio).toHaveBeenCalledTimes(recargas);
    });

    it('mientras envía deshabilita la confirmación y no envía dos veces', async () => {
      let resolver: (v: Resultado<typeof ACREDITACION, ErrorCaja>) => void = () => undefined;
      const api = apiFalsa({
        acreditarRevision: vi.fn(() => new Promise<Resultado<typeof ACREDITACION, ErrorCaja>>((res) => { resolver = res; })),
      });
      montar([REVISION], api);
      await usuario.click(screen.getByRole('button', { name: 'Acreditar' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, acreditar el pago' }));
      const enCurso = within(screen.getByRole('dialog')).getByRole('button', { name: 'Guardando…' });
      expect(enCurso).toBeDisabled();
      await act(async () => {
        resolver({ ok: true, valor: ACREDITACION });
        await Promise.resolve();
      });
      expect(api.acreditarRevision).toHaveBeenCalledTimes(1);
    });
  });
});
