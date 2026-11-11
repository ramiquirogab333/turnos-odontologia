import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ErrorCaja, Resultado } from '../lib/tipos';
import { apiFalsa, caja, cierre } from '../test/datos';
import { CierreCaja } from './CierreCaja';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

const HOY = '2031-11-18';
const AYER = '2031-11-17';

interface Opciones {
  readonly sobreCaja?: Parameters<typeof caja>[0];
  readonly esAdmin?: boolean;
  readonly api?: ReturnType<typeof apiFalsa>;
  readonly onCambio?: () => void;
}

async function montar({ sobreCaja = {}, esAdmin = false, api = apiFalsa(), onCambio = vi.fn() }: Opciones = {}) {
  await act(async () => {
    render(<CierreCaja caja={caja({ dia: AYER, ...sobreCaja })} hoy={HOY} esAdmin={esAdmin} api={api} onCambio={onCambio} />);
    await Promise.resolve();
  });
  return { api, onCambio };
}

const CERRADA = { dia: AYER, estado: 'cerrado' as const, cierre_id: 3 };
const rechazo = (error: ErrorCaja): Resultado<never, ErrorCaja> => ({ ok: false, error });

describe('Pantalla de cierre de caja', () => {
  describe('día terminado y abierto', () => {
    it('ofrece «Cerrar caja»', async () => {
      await montar();
      expect(screen.getByRole('button', { name: 'Cerrar caja' })).toBeInTheDocument();
    });

    it('la confirmación muestra los totales y avisa que el día queda cerrado', async () => {
      const { api } = await montar({ sobreCaja: { total_egresos: '500.00', total_neto: '2500.00' } });
      await usuario.click(screen.getByRole('button', { name: 'Cerrar caja' }));
      const dialogo = screen.getByRole('dialog', { name: /¿Cerrar la caja del .*17 de noviembre\?/ });
      expect(dialogo).toHaveTextContent('Ingresos $ 3.000,00');
      expect(dialogo).toHaveTextContent('Egresos $ 500,00');
      expect(dialogo).toHaveTextContent('Total del día $ 2.500,00');
      expect(dialogo).toHaveTextContent('no se pueden cargar ni quitar movimientos');
      expect(api.cerrarCaja).not.toHaveBeenCalled();
    });

    it('confirmar cierra el día elegido y avisa el cambio', async () => {
      const { api, onCambio } = await montar();
      await usuario.click(screen.getByRole('button', { name: 'Cerrar caja' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, cerrar la caja' }));
      expect(api.cerrarCaja).toHaveBeenCalledWith(AYER);
      expect(onCambio).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('dialog')).toBeNull();
    });

    it('«Volver» no cierra nada', async () => {
      const { api } = await montar();
      await usuario.click(screen.getByRole('button', { name: 'Cerrar caja' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Volver' }));
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(api.cerrarCaja).not.toHaveBeenCalled();
    });

    it.each([
      [{ tipo: 'dia_no_terminado', cerrableDesde: '2031-11-18T00:15:00-03:00' }, 'Todavía no se puede cerrar este día. Probá desde las 00:15.', 0],
      [{ tipo: 'dia_ya_cerrado' }, 'Este día ya tiene un cierre. Actualizamos la pantalla.', 1],
      [{ tipo: 'sin_permiso' }, 'Tu usuario no puede hacer este cambio.', 0],
      [{ tipo: 'desconocido' }, 'No pudimos guardar el cambio. Probá de nuevo; si sigue igual, avisá a la clínica.', 0],
    ] as const)('%j muestra "%s"', async (error, texto, recargas) => {
      const api = apiFalsa({ cerrarCaja: vi.fn().mockResolvedValue(rechazo(error)) });
      const { onCambio } = await montar({ api });
      await usuario.click(screen.getByRole('button', { name: 'Cerrar caja' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, cerrar la caja' }));
      expect(screen.getByRole('alert')).toHaveTextContent(texto);
      expect(onCambio).toHaveBeenCalledTimes(recargas);
    });
  });

  describe('hoy', () => {
    it('no ofrece cerrar y avisa desde cuándo se puede', async () => {
      await montar({ sobreCaja: { dia: HOY } });
      expect(screen.queryByRole('button', { name: 'Cerrar caja' })).toBeNull();
      expect(screen.getByText(/desde mañana a las 00:15/)).toBeInTheDocument();
    });
  });

  describe('día cerrado', () => {
    it('dice quién cerró, cuándo, y que el cierre cuadra', async () => {
      const { api } = await montar({ sobreCaja: CERRADA });
      expect(api.cierre).toHaveBeenCalledWith(3);
      expect(await screen.findByText(/Cerrada por Rita Recepción el 18\/11 a las 00:20/)).toBeInTheDocument();
      expect(screen.getByText('El cierre cuadra')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Cerrar caja' })).toBeNull();
    });

    it('un cierre que no cuadra muestra las diferencias por concepto y medio', async () => {
      const descuadrado = cierre({
        cuadra: false,
        diferencias: [
          { concepto: 'sena', medio: 'mercadopago', total_cierre: '3000.00', total_actual: '3500.00', cantidad_cierre: 1, cantidad_actual: 2 },
        ],
      });
      await montar({ sobreCaja: CERRADA, api: apiFalsa({ cierre: vi.fn().mockResolvedValue(descuadrado) }) });
      expect(await screen.findByText('El cierre no cuadra con los movimientos del día')).toBeInTheDocument();
      expect(screen.queryByText('El cierre cuadra')).toBeNull();
      expect(
        screen.getByText('Señas por Mercado Pago: al cerrar $ 3.000,00 (1), ahora $ 3.500,00 (2)'),
      ).toBeInTheDocument();
    });

    it('si falla la lectura del cierre ofrece reintentar', async () => {
      const api = apiFalsa({ cierre: vi.fn().mockRejectedValueOnce(new Error('caído')).mockResolvedValue(cierre()) });
      await montar({ sobreCaja: CERRADA, api });
      const alerta = await screen.findByRole('alert');
      expect(alerta).toHaveTextContent('No pudimos cargar el cierre');
      await usuario.click(within(alerta).getByRole('button', { name: 'Reintentar' }));
      expect(await screen.findByText('El cierre cuadra')).toBeInTheDocument();
    });
  });

  describe('anular el cierre', () => {
    it('solo lo ve el administrador', async () => {
      await montar({ sobreCaja: CERRADA, esAdmin: false });
      await screen.findByText('El cierre cuadra');
      expect(screen.queryByRole('button', { name: 'Anular cierre' })).toBeNull();
    });

    it('el administrador lo ve, y el diálogo explica que el día vuelve a estar abierto', async () => {
      await montar({ sobreCaja: CERRADA, esAdmin: true });
      await screen.findByText('El cierre cuadra');
      await usuario.click(screen.getByRole('button', { name: 'Anular cierre' }));
      const dialogo = screen.getByRole('dialog', { name: /¿Anular el cierre del .*17 de noviembre\?/ });
      expect(dialogo).toHaveTextContent('vuelve a estar abierto');
      expect(within(dialogo).getByLabelText('Motivo de la anulación')).toBeInTheDocument();
    });

    it.each(['', '  ', 'ab'])('el motivo "%s" no se envía y dice qué falta', async (texto) => {
      const { api } = await montar({ sobreCaja: CERRADA, esAdmin: true });
      await screen.findByText('El cierre cuadra');
      await usuario.click(screen.getByRole('button', { name: 'Anular cierre' }));
      const dialogo = screen.getByRole('dialog');
      if (texto.trim() !== '') await usuario.type(within(dialogo).getByLabelText('Motivo de la anulación'), texto);
      await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, anular el cierre' }));
      expect(screen.getByRole('alert')).toHaveTextContent('Escribí el motivo de la anulación (al menos 3 letras)');
      expect(api.anularCierre).not.toHaveBeenCalled();
    });

    it('con motivo anula el cierre indicado y avisa el cambio', async () => {
      const { api, onCambio } = await montar({ sobreCaja: CERRADA, esAdmin: true });
      await screen.findByText('El cierre cuadra');
      await usuario.click(screen.getByRole('button', { name: 'Anular cierre' }));
      const dialogo = screen.getByRole('dialog');
      await usuario.type(within(dialogo).getByLabelText('Motivo de la anulación'), ' Cargamos mal un cobro ');
      await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, anular el cierre' }));
      expect(api.anularCierre).toHaveBeenCalledWith(3, 'Cargamos mal un cobro');
      expect(onCambio).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('dialog')).toBeNull();
    });

    it('un 403 se explica y no recarga', async () => {
      const api = apiFalsa({ anularCierre: vi.fn().mockResolvedValue(rechazo({ tipo: 'sin_permiso' })) });
      const { onCambio } = await montar({ sobreCaja: CERRADA, esAdmin: true, api });
      await screen.findByText('El cierre cuadra');
      await usuario.click(screen.getByRole('button', { name: 'Anular cierre' }));
      const dialogo = screen.getByRole('dialog');
      await usuario.type(within(dialogo).getByLabelText('Motivo de la anulación'), 'Cargamos mal un cobro');
      await usuario.click(within(dialogo).getByRole('button', { name: 'Sí, anular el cierre' }));
      expect(screen.getByRole('alert')).toHaveTextContent('Tu usuario no puede hacer este cambio.');
      expect(onCambio).not.toHaveBeenCalled();
    });
  });
});
