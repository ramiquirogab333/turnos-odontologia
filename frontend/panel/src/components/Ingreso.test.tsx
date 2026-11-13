import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ResultadoIngreso } from '../lib/sesion';
import { Ingreso } from './Ingreso';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
};

async function completar(email: string, clave: string) {
  await usuario.type(screen.getByLabelText('Correo electrónico'), email);
  await usuario.type(screen.getByLabelText('Contraseña'), clave);
}

describe('Ingreso', () => {
  it('pide correo y contraseña y el botón nombra el resultado', () => {
    render(<Ingreso aviso={null} onIngresar={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'Ingresá al panel' })).toBeInTheDocument();
    expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Ingresar al panel' })).toBeInTheDocument();
  });

  it('no envía con campos vacíos y explica qué falta', async () => {
    const onIngresar = vi.fn<(e: string, c: string) => Promise<ResultadoIngreso>>();
    render(<Ingreso aviso={null} onIngresar={onIngresar} />);
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(onIngresar).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Completá el correo y la contraseña.');
  });

  it('envía el correo sin espacios y la contraseña tal cual', async () => {
    const onIngresar = vi.fn<(e: string, c: string) => Promise<ResultadoIngreso>>().mockResolvedValue({ ok: true });
    render(<Ingreso aviso={null} onIngresar={onIngresar} />);
    await completar('  recepcion@turnos.test ', 'clave sintética 123');
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(onIngresar).toHaveBeenCalledWith('recepcion@turnos.test', 'clave sintética 123');
  });

  it.each([
    ['credenciales', 'El correo o la contraseña no son correctos. Revisalos e intentá de nuevo.'],
    ['red', 'No pudimos conectarnos. Revisá tu conexión e intentá de nuevo.'],
    ['servidor', 'El servidor no pudo procesar el ingreso. Intentá de nuevo en unos minutos.'],
  ] as const)('ante "%s" muestra qué pasó y cómo seguir, sin borrar el correo', async (motivo, texto) => {
    const onIngresar = vi.fn<(e: string, c: string) => Promise<ResultadoIngreso>>().mockResolvedValue({ ok: false, motivo });
    render(<Ingreso aviso={null} onIngresar={onIngresar} />);
    await completar('a@turnos.test', 'clave-sintetica-123');
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(texto);
    expect(screen.getByLabelText('Correo electrónico')).toHaveValue('a@turnos.test');
  });

  it.each([
    [10, 'Demasiados intentos. Probá de nuevo en 10 minutos.'],
    [1, 'Demasiados intentos. Probá de nuevo en 1 minuto.'],
  ] as const)('ante un límite de %i minuto(s) lo anuncia con role alert y conserva el correo', async (minutos, texto) => {
    const onIngresar = vi.fn<(e: string, c: string) => Promise<ResultadoIngreso>>().mockResolvedValue({ ok: false, motivo: 'limite', minutos });
    render(<Ingreso aviso={null} onIngresar={onIngresar} />);
    await completar('a@turnos.test', 'clave-sintetica-123');
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(texto);
    expect(screen.getByLabelText('Correo electrónico')).toHaveValue('a@turnos.test');
  });

  it('un correo inexistente y una contraseña errónea dan el mismo mensaje', async () => {
    const mensajes: string[] = [];
    for (const email of ['existe@turnos.test', 'noexiste@turnos.test']) {
      const { unmount } = render(
        <Ingreso aviso={null} onIngresar={vi.fn<(e: string, c: string) => Promise<ResultadoIngreso>>().mockResolvedValue({ ok: false, motivo: 'credenciales' })} />,
      );
      await completar(email, 'clave-sintetica-123');
      await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
      mensajes.push((await screen.findByRole('alert')).textContent);
      unmount();
    }
    expect(mensajes[0]).toBe(mensajes[1]);
  });

  it('mientras envía deshabilita el botón y evita el doble envío', async () => {
    let resolver: (r: ResultadoIngreso) => void = () => undefined;
    const onIngresar = vi.fn<(e: string, c: string) => Promise<ResultadoIngreso>>(() => new Promise((res) => { resolver = res; }));
    render(<Ingreso aviso={null} onIngresar={onIngresar} />);
    await completar('a@turnos.test', 'clave-sintetica-123');
    await usuario.click(screen.getByRole('button', { name: 'Ingresar al panel' }));
    expect(screen.getByRole('button', { name: 'Ingresando…' })).toBeDisabled();
    await act(async () => {
      resolver({ ok: false, motivo: 'red' });
      await Promise.resolve();
    });
    expect(onIngresar).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Ingresar al panel' })).toBeEnabled();
  });

  it.each([
    ['vencida', 'Tu sesión venció. Ingresá de nuevo para seguir.'],
    ['otra_pestana', 'Cerraste la sesión en otra pestaña. Ingresá de nuevo para seguir.'],
    ['salida', 'Saliste del panel.'],
  ] as const)('avisa con "%s" por qué se pide ingresar', (aviso, texto) => {
    render(<Ingreso aviso={aviso} onIngresar={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent(texto);
  });

  it('sin aviso no muestra ningún mensaje ni error', () => {
    render(<Ingreso aviso={null} onIngresar={vi.fn()} />);
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
