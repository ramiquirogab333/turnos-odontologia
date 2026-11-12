import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { apiFalsa, recordatorio } from '../test/datos';
import { Recordatorios } from './Recordatorios';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

async function montar(api = apiFalsa()) {
  await act(async () => {
    render(<Recordatorios api={api} />);
    await Promise.resolve();
  });
  return api;
}

const PENDIENTE = recordatorio();
const OTRO = recordatorio({ id: 8, turno_id: 12, contacto_nombre: 'Lucía Ficticia', turno_inicio: '2031-11-18T10:00:00-03:00' });

describe('Pantalla de recordatorios', () => {
  it('lista los turnos por avisar con nombre, horario, tratamiento y profesional', async () => {
    await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([PENDIENTE, OTRO]) }));
    const filas = await screen.findAllByRole('listitem');
    expect(filas).toHaveLength(2);
    const primera = within(filas[0] as HTMLElement);
    expect(primera.getByText('Carlos Sintético')).toBeInTheDocument();
    expect(primera.getByText(/09:00/)).toBeInTheDocument();
    expect(primera.getByText(/Limpieza dental · Dra\. Ana Ficticia/)).toBeInTheDocument();
    expect(primera.getByText('Pendiente')).toBeInTheDocument();
  });

  it('pide la lista una sola vez (sin cascadas, R2)', async () => {
    const api = await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([PENDIENTE]) }));
    expect(api.recordatorios).toHaveBeenCalledTimes(1);
  });

  it('sin recordatorios dice "No hay recordatorios por enviar" y no dibuja una lista vacía', async () => {
    await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([]) }));
    expect(await screen.findByText('No hay recordatorios por enviar')).toBeInTheDocument();
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('con solo enviados igual dice que no hay por enviar y los muestra aparte', async () => {
    await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([recordatorio({ estado: 'enviado' })]) }));
    expect(await screen.findByText('No hay recordatorios por enviar')).toBeInTheDocument();
    expect(screen.getByText('Enviado')).toBeInTheDocument();
  });

  it('una falla al cargar muestra el error con reintento', async () => {
    const recordatorios = vi.fn().mockRejectedValueOnce(new Error('x')).mockResolvedValue([PENDIENTE]);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await montar(apiFalsa({ recordatorios }));
    await usuario.click(await screen.findByRole('button', { name: /reintentar/i }));
    expect(await screen.findByText('Carlos Sintético')).toBeInTheDocument();
  });

  describe('Abrir WhatsApp', () => {
    it('es un enlace wa.me que abre otra pestaña de forma segura', async () => {
      await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([PENDIENTE]) }));
      const enlace = await screen.findByRole('link', { name: 'Abrir WhatsApp' });
      expect(enlace).toHaveAttribute('href', PENDIENTE.link);
      expect(enlace).toHaveAttribute('target', '_blank');
      expect(enlace).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('al tocarlo registra el envío sin bloquear la apertura y la fila pasa a Enviado', async () => {
      const enviado = recordatorio({ estado: 'enviado', enviado_en: '2031-11-17T10:00:00-03:00' });
      const api = apiFalsa({
        recordatorios: vi.fn().mockResolvedValue([PENDIENTE]),
        marcarRecordatorioEnviado: vi.fn().mockResolvedValue({ ok: true, valor: enviado }),
      });
      await montar(api);
      const enlace = await screen.findByRole('link', { name: 'Abrir WhatsApp' });
      let predeterminadoEvitado = false;
      enlace.addEventListener('click', (e) => {
        predeterminadoEvitado = e.defaultPrevented;
        e.preventDefault(); // jsdom no navega; solo se mide que la app no lo haya evitado
      });
      await usuario.click(enlace);
      expect(predeterminadoEvitado).toBe(false);
      expect(api.marcarRecordatorioEnviado).toHaveBeenCalledWith(7);
      expect(await screen.findByText('Enviado')).toBeInTheDocument();
    });

    it('si el registro falla muestra el error y permite reintentar sin perder el enlace', async () => {
      const enviado = recordatorio({ estado: 'enviado' });
      const marcar = vi
        .fn()
        .mockResolvedValueOnce({ ok: false, error: { tipo: 'desconocido' } })
        .mockResolvedValueOnce({ ok: true, valor: enviado });
      await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([PENDIENTE]), marcarRecordatorioEnviado: marcar }));
      const enlace = await screen.findByRole('link', { name: 'Abrir WhatsApp' });
      enlace.addEventListener('click', (e) => {
        e.preventDefault();
      });
      await usuario.click(enlace);
      expect(await screen.findByRole('alert')).toHaveTextContent(/No pudimos registrar el envío/);
      expect(screen.getByRole('link', { name: 'Abrir WhatsApp' })).toBeInTheDocument();
      await usuario.click(screen.getByRole('button', { name: 'Reintentar registro' }));
      expect(marcar).toHaveBeenCalledTimes(2);
      expect(await screen.findByText('Enviado')).toBeInTheDocument();
      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('un recordatorio vencido en el servidor (no vigente) se saca de la lista con un aviso', async () => {
      const marcar = vi.fn().mockResolvedValue({ ok: false, error: { tipo: 'no_vigente' } });
      await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([PENDIENTE]), marcarRecordatorioEnviado: marcar }));
      const enlace = await screen.findByRole('link', { name: 'Abrir WhatsApp' });
      enlace.addEventListener('click', (e) => {
        e.preventDefault();
      });
      await usuario.click(enlace);
      expect(await screen.findByRole('alert')).toHaveTextContent(/ya no corresponde/);
      expect(screen.queryByRole('link', { name: 'Abrir WhatsApp' })).toBeNull();
    });

    it('sin link (sin teléfono) no hay enlace y se explica por qué', async () => {
      const sinTel = recordatorio({ estado: 'fallido', motivo: 'sin_telefono', link: null });
      await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([sinTel]) }));
      expect(await screen.findByText(/Sin teléfono/)).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'Abrir WhatsApp' })).toBeNull();
    });
  });

  describe('No se pudo enviar', () => {
    it('ofrece los tres motivos, no hace nada hasta confirmar y deja la fila como fallida', async () => {
      const fallido = recordatorio({ estado: 'fallido', motivo: 'sin_whatsapp' });
      const api = apiFalsa({
        recordatorios: vi.fn().mockResolvedValue([PENDIENTE]),
        marcarRecordatorioFallido: vi.fn().mockResolvedValue({ ok: true, valor: fallido }),
      });
      await montar(api);
      await usuario.click(await screen.findByRole('button', { name: 'No se pudo enviar' }));
      const dialogo = screen.getByRole('dialog');
      expect(within(dialogo).getAllByRole('radio').map((r) => (r as HTMLInputElement).value)).toEqual([
        'numero_invalido',
        'sin_whatsapp',
        'otro',
      ]);
      expect(api.marcarRecordatorioFallido).not.toHaveBeenCalled();
      await usuario.click(within(dialogo).getByRole('radio', { name: 'No tiene WhatsApp' }));
      await usuario.click(within(dialogo).getByRole('button', { name: 'Marcar como no enviado' }));
      expect(api.marcarRecordatorioFallido).toHaveBeenCalledWith(7, 'sin_whatsapp');
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(await screen.findByText(/No se pudo enviar: no tiene WhatsApp/)).toBeInTheDocument();
    });

    it('sin elegir motivo pide que elija uno y no llama al servidor', async () => {
      const api = apiFalsa({ recordatorios: vi.fn().mockResolvedValue([PENDIENTE]) });
      await montar(api);
      await usuario.click(await screen.findByRole('button', { name: 'No se pudo enviar' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Marcar como no enviado' }));
      expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent(/Elegí un motivo/);
      expect(api.marcarRecordatorioFallido).not.toHaveBeenCalled();
    });

    it('Volver cierra el diálogo sin cambios', async () => {
      const api = await montar(apiFalsa({ recordatorios: vi.fn().mockResolvedValue([PENDIENTE]) }));
      await usuario.click(await screen.findByRole('button', { name: 'No se pudo enviar' }));
      await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Volver' }));
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(api.marcarRecordatorioFallido).not.toHaveBeenCalled();
    });
  });
});
