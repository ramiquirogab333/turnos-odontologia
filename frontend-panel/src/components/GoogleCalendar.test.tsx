import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ResultadoGoogle } from '../lib/ruta';
import { apiFalsa, CONEXION_ACTIVA, conexionGoogle, conflictoGoogle } from '../test/datos';
import { GoogleCalendar } from './GoogleCalendar';

const base = userEvent.setup();
const usuario = { click: (el: Element) => act(() => base.click(el)) };

interface Opciones {
  readonly puedeResolver?: boolean;
  readonly esAdmin?: boolean;
  readonly esOdontologa?: boolean;
  readonly resultado?: ResultadoGoogle | null;
  readonly irAUrl?: (url: string) => void;
}

async function montar(api = apiFalsa(), { puedeResolver = false, esAdmin = false, esOdontologa = true, resultado = null, irAUrl = () => undefined }: Opciones = {}) {
  await act(async () => {
    render(<GoogleCalendar api={api} puedeResolver={puedeResolver} esAdmin={esAdmin} esOdontologa={esOdontologa} resultado={resultado} irAUrl={irAUrl} />);
    await Promise.resolve();
  });
  return api;
}

const RECEPCION: Opciones = { puedeResolver: true, esOdontologa: false };

describe('Sección Google Calendar: la odontóloga y su conexión', () => {
  it('sin conexión ofrece "Conectar Google Calendar", que pide la URL y lleva a Google', async () => {
    const irAUrl = vi.fn();
    const api = await montar(apiFalsa(), { irAUrl });
    await usuario.click(await screen.findByRole('button', { name: 'Conectar Google Calendar' }));
    expect(api.iniciarGoogle).toHaveBeenCalledTimes(1);
    expect(irAUrl).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?state=x');
  });

  it('conectada muestra la cuenta, la última sincronización y "Desconectar" con confirmación', async () => {
    const api = apiFalsa({ conexionesGoogle: vi.fn().mockResolvedValue([CONEXION_ACTIVA]) });
    await montar(api);
    expect(await screen.findByText('Conectado como ana.prueba@example.com')).toBeInTheDocument();
    expect(screen.getByText(/^Última sincronización:/)).toHaveTextContent('08:30');
    expect(screen.queryByRole('button', { name: 'Conectar Google Calendar' })).toBeNull();
    await usuario.click(screen.getByRole('button', { name: 'Desconectar' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/siguen en tu Google Calendar/)).toBeInTheDocument();
    expect(api.desconectarGoogle).not.toHaveBeenCalled();
    await usuario.click(within(dialogo).getByRole('button', { name: 'Desconectar Google Calendar' }));
    expect(api.desconectarGoogle).toHaveBeenCalledWith(1);
    expect(api.conexionesGoogle).toHaveBeenCalledTimes(2); // se vuelve a leer el estado
  });

  it('una conexión revocada muestra la indicación y deja volver a conectar', async () => {
    await montar(apiFalsa({
      conexionesGoogle: vi.fn().mockResolvedValue([conexionGoogle({ estado: 'revocada', indicacion: 'Volvé a conectar Google Calendar' })]),
    }));
    expect(await screen.findByText('Volvé a conectar Google Calendar')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Conectar Google Calendar' })).toBeInTheDocument();
  });

  it.each([
    ['conectado', /Google Calendar quedó conectado/, 'status'],
    ['error_autorizacion', /No se pudo conectar Google Calendar\. Volvé a intentarlo/, 'alert'],
    ['permiso_denegado', /No se conectó Google Calendar: no se dio el permiso/, 'alert'],
  ] as const)('al volver de Google con "%s" lo dice y el botón sigue disponible si no está conectada', async (resultado, texto, rol) => {
    await montar(apiFalsa(), { resultado });
    expect(within(await screen.findByRole(rol)).getByText(texto)).toBeInTheDocument();
    if (resultado !== 'conectado') expect(screen.getByRole('button', { name: 'Conectar Google Calendar' })).toBeInTheDocument();
  });

  it.each([
    [{ tipo: 'no_configurado' }, /todavía no está configurado/],
    [{ tipo: 'conexion_activa' }, /ya está conectado/],
    [{ tipo: 'sin_permiso' }, /No tenés permiso/],
    [{ tipo: 'desconocido' }, /No pudimos iniciar la conexión/],
  ] as const)('si no se puede iniciar (%o) explica qué pasó', async (error, texto) => {
    const irAUrl = vi.fn();
    await montar(apiFalsa({ iniciarGoogle: vi.fn().mockResolvedValue({ ok: false, error }) }), { irAUrl });
    await usuario.click(await screen.findByRole('button', { name: 'Conectar Google Calendar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(texto);
    expect(irAUrl).not.toHaveBeenCalled();
  });
});

describe('Sección Google Calendar: los conflictos', () => {
  const MOVIDO = conflictoGoogle();
  const BORRADO = conflictoGoogle({
    id: 22, tipo: 'borrado_en_google', google_inicio: null, google_fin: null, criterio: 'El evento se borró en Google Calendar.',
  });
  const SOLAPE = conflictoGoogle({
    id: 23, tipo: 'solapa_evento_externo', acciones: ['revisado'], criterio: 'El turno se superpone con un evento ocupado de Google Calendar.',
    google_inicio: '2031-11-18T10:00:00-03:00', google_fin: '2031-11-18T11:00:00-03:00',
  });

  it('recepción ve todas las profesionales y cada conflicto con el criterio y ambos horarios', async () => {
    await montar(apiFalsa({
      conexionesGoogle: vi.fn().mockResolvedValue([CONEXION_ACTIVA, conexionGoogle({ profesional_id: 4, profesional_nombre: 'Dr. Bruno Ejemplo' })]),
      conflictosGoogle: vi.fn().mockResolvedValue([MOVIDO, BORRADO]),
    }), RECEPCION);
    expect(await screen.findByText('Dra. Ana Ficticia')).toBeInTheDocument();
    expect(screen.getByText('Dr. Bruno Ejemplo')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Conectar Google Calendar' })).toBeNull();
    const tarjetas = screen.getAllByRole('listitem').filter((li) => li.className.includes('conflicto'));
    expect(tarjetas).toHaveLength(2);
    expect(within(tarjetas[0] as HTMLElement).getByText('Sistema: 10:00–10:30 / Google: 12:00–12:30')).toBeInTheDocument();
    expect(within(tarjetas[0] as HTMLElement).getByText(/El evento se movió en Google Calendar/)).toBeInTheDocument();
    expect(within(tarjetas[1] as HTMLElement).getByText('Sistema: 10:00–10:30 / Google: el evento ya no está')).toBeInTheDocument();
  });

  it('cada tipo ofrece sus acciones: restaurar y desvincular, o marcar revisado', async () => {
    await montar(apiFalsa({ conflictosGoogle: vi.fn().mockResolvedValue([MOVIDO, SOLAPE]) }), RECEPCION);
    const tarjetas = (await screen.findAllByRole('listitem')).filter((li) => li.className.includes('conflicto'));
    expect(within(tarjetas[0] as HTMLElement).getAllByRole('button').map((b) => b.textContent)).toEqual(['Restaurar en Google', 'Desvincular']);
    expect(within(tarjetas[1] as HTMLElement).getAllByRole('button').map((b) => b.textContent)).toEqual(['Marcar como revisado']);
  });

  it('la odontóloga ve sus conflictos sin botones', async () => {
    await montar(apiFalsa({
      conexionesGoogle: vi.fn().mockResolvedValue([CONEXION_ACTIVA]),
      conflictosGoogle: vi.fn().mockResolvedValue([conflictoGoogle({ acciones: [] })]),
    }), { puedeResolver: false });
    expect(await screen.findByText('Sistema: 10:00–10:30 / Google: 12:00–12:30')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Restaurar en Google' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Desvincular' })).toBeNull();
  });

  it('resolver pide confirmación, llama a la API con la acción y saca el conflicto de la lista', async () => {
    const api = await montar(apiFalsa({ conflictosGoogle: vi.fn().mockResolvedValue([MOVIDO]) }), RECEPCION);
    await usuario.click(await screen.findByRole('button', { name: 'Restaurar en Google' }));
    const dialogo = await screen.findByRole('dialog');
    expect(api.resolverConflicto).not.toHaveBeenCalled();
    expect(within(dialogo).getByText(/vuelve al horario del turno/)).toBeInTheDocument();
    await usuario.click(within(dialogo).getByRole('button', { name: 'Restaurar en Google' }));
    expect(api.resolverConflicto).toHaveBeenCalledWith(21, 'restaurar_en_google');
    expect(await screen.findByText('No hay conflictos con Google Calendar')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('un conflicto que ya se cerró explica por qué y desaparece', async () => {
    await montar(apiFalsa({
      conflictosGoogle: vi.fn().mockResolvedValue([SOLAPE]),
      resolverConflicto: vi.fn().mockResolvedValue({ ok: false, error: { tipo: 'conflicto_cerrado' } }),
    }), RECEPCION);
    await usuario.click(await screen.findByRole('button', { name: 'Marcar como revisado' }));
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Marcar como revisado' }));
    expect(await screen.findByText(/ya no está abierto/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Marcar como revisado' })).toBeNull();
  });

  it('otro rechazo deja el conflicto y avisa dentro del diálogo', async () => {
    await montar(apiFalsa({
      conflictosGoogle: vi.fn().mockResolvedValue([MOVIDO]),
      resolverConflicto: vi.fn().mockResolvedValue({ ok: false, error: { tipo: 'desconocido' } }),
    }), RECEPCION);
    await usuario.click(await screen.findByRole('button', { name: 'Desvincular' }));
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Desvincular' }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(/No pudimos resolver el conflicto/);
    expect(screen.getAllByText('Sistema: 10:00–10:30 / Google: 12:00–12:30')).toHaveLength(2); // la tarjeta sigue y el diálogo la repite
  });

  it('sin conflictos lo dice e informa la última sincronización correcta', async () => {
    await montar(apiFalsa({ conexionesGoogle: vi.fn().mockResolvedValue([CONEXION_ACTIVA]) }));
    expect(await screen.findByText('No hay conflictos con Google Calendar')).toBeInTheDocument();
    expect(screen.getAllByText(/Última sincronización/).length).toBeGreaterThan(0);
  });

  it('pide las conexiones y los conflictos en paralelo, sin esperar a que termine la primera (R2)', async () => {
    const api = apiFalsa({
      conexionesGoogle: vi.fn().mockReturnValue(new Promise(() => undefined)),
      conflictosGoogle: vi.fn().mockReturnValue(new Promise(() => undefined)),
    });
    await montar(api);
    expect(api.conexionesGoogle).toHaveBeenCalledTimes(1);
    expect(api.conflictosGoogle).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent(/Cargando/);
  });

  it('una falla al cargar muestra el error con reintento', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const conexionesGoogle = vi.fn().mockRejectedValueOnce(new Error('x')).mockResolvedValue([CONEXION_ACTIVA]);
    await montar(apiFalsa({ conexionesGoogle }));
    await usuario.click(await screen.findByRole('button', { name: /reintentar/i }));
    expect(await screen.findByText('Conectado como ana.prueba@example.com')).toBeInTheDocument();
  });

  it('admin puede desconectar a cualquier profesional conectada', async () => {
    const api = await montar(apiFalsa({ conexionesGoogle: vi.fn().mockResolvedValue([CONEXION_ACTIVA]) }), { ...RECEPCION, esAdmin: true });
    await usuario.click(await screen.findByRole('button', { name: 'Desconectar' }));
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Desconectar Google Calendar' }));
    expect(api.desconectarGoogle).toHaveBeenCalledWith(1);
  });

  it('recepción (sin ser admin) no ve "Desconectar" ni "Conectar"', async () => {
    await montar(apiFalsa({ conexionesGoogle: vi.fn().mockResolvedValue([CONEXION_ACTIVA]) }), RECEPCION);
    expect(await screen.findByText('Conectado como ana.prueba@example.com')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Desconectar' })).toBeNull();
  });
});
