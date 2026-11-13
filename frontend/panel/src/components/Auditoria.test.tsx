import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ErrorApiPanel } from '../lib/api';
import type { ConsultaAuditoria, PaginaAuditoria, UsuarioDirectorio } from '../lib/tipos';
import { apiFalsa, paginaAuditoria, registroAuditoria } from '../test/datos';
import { Auditoria } from './Auditoria';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
  seleccionar: (el: Element, valor: string) => act(() => base.selectOptions(el, valor)),
};

const USUARIOS: readonly UsuarioDirectorio[] = [
  { id: 3, nombre_completo: 'Recepción Ficticia', activo: true },
  { id: 4, nombre_completo: 'Ex Ficticio', activo: false },
];
const SIN_FILTROS: ConsultaAuditoria = { desde: null, hasta: null, usuarioId: null, tipo: null, entidad: null, entidadId: null, cursor: null };

async function montar(consultar: (c: ConsultaAuditoria) => Promise<PaginaAuditoria> = () => Promise.resolve(paginaAuditoria([registroAuditoria()]))) {
  const espia = vi.fn<(c: ConsultaAuditoria) => Promise<PaginaAuditoria>>(consultar);
  const api = apiFalsa({ consultarAuditoria: espia, listarUsuarios: vi.fn().mockResolvedValue(USUARIOS) });
  await act(async () => {
    render(<Auditoria api={api} />);
    await Promise.resolve();
  });
  return { api, espia };
}

/** Título de un registro dentro de la lista (los mismos textos aparecen como opciones del filtro de tipo). */
async function titulo(texto: string): Promise<HTMLElement> {
  return within(await screen.findByRole('list', { name: 'Registros de auditoría' })).findByText(texto);
}

describe('Auditoría', () => {
  it('pide los usuarios y la primera página a la vez, sin cascada (R2)', async () => {
    let resolverUsuarios: (v: readonly UsuarioDirectorio[]) => void = () => undefined;
    let resolverPagina: (v: PaginaAuditoria) => void = () => undefined;
    const api = apiFalsa({
      listarUsuarios: vi.fn(() => new Promise<readonly UsuarioDirectorio[]>((res) => { resolverUsuarios = res; })),
      consultarAuditoria: vi.fn(() => new Promise<PaginaAuditoria>((res) => { resolverPagina = res; })),
    });
    await act(async () => {
      render(<Auditoria api={api} />);
      await Promise.resolve();
    });
    expect(api.listarUsuarios).toHaveBeenCalledTimes(1);
    expect(api.consultarAuditoria).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolverUsuarios(USUARIOS);
      resolverPagina(paginaAuditoria([registroAuditoria()]));
      await Promise.resolve();
    });
    expect(await titulo('Cierre de caja')).toBeInTheDocument();
  });

  it('cada registro muestra fecha y hora local, usuario, tipo legible, entidad e IP', async () => {
    await montar();
    const lista = await screen.findByRole('list', { name: 'Registros de auditoría' });
    const item = within(lista).getByRole('listitem');
    expect(within(item).getByText('13/11 09:05')).toBeInTheDocument();
    expect(within(item).getByText('Recepción Ficticia')).toBeInTheDocument();
    expect(within(item).getByText('Cierre de caja')).toBeInTheDocument();
    expect(within(item).getByText(/cierre_caja #42/)).toBeInTheDocument();
    expect(within(item).getByText(/IP 203\.0\.113\.20/)).toBeInTheDocument();
  });

  it('un registro sin usuario es del sistema o de un paciente, y sin IP lo dice', async () => {
    await montar(() => Promise.resolve(paginaAuditoria([registroAuditoria({ usuario: null, ip: null })])));
    expect(await screen.findByText('Sistema / paciente')).toBeInTheDocument();
    expect(screen.getByText(/Sin IP/)).toBeInTheDocument();
  });

  it('los datos de antes y después van en un detalle desplegable', async () => {
    await montar(() =>
      Promise.resolve(paginaAuditoria([registroAuditoria({ datos_antes: { estado: 'reservado' }, datos_despues: { estado: 'atendido' } })])),
    );
    const detalle = (await screen.findByText('Ver datos')).closest('details');
    expect(detalle).not.toBeNull();
    expect(detalle).toHaveTextContent(/"estado": "reservado"/);
    expect(detalle).toHaveTextContent(/"estado": "atendido"/);
  });

  it('«Ver más» pide la página siguiente con el cursor, agrega los registros y desaparece al terminar', async () => {
    const { espia } = await montar((c) =>
      Promise.resolve(
        c.cursor === null
          ? paginaAuditoria([registroAuditoria({ id: 91 })], 'cursor-1')
          : paginaAuditoria([registroAuditoria({ id: 90, tipo_etiqueta: 'Anulación de cierre de caja' })], null),
      ),
    );
    await titulo('Cierre de caja');
    await usuario.click(screen.getByRole('button', { name: 'Ver más' }));
    expect(await titulo('Anulación de cierre de caja')).toBeInTheDocument();
    expect(await titulo('Cierre de caja')).toBeInTheDocument(); // la primera página sigue
    expect(espia.mock.calls.map((c) => c[0].cursor)).toEqual([null, 'cursor-1']);
    expect(screen.queryByRole('button', { name: 'Ver más' })).toBeNull();
  });

  it('sin registros dice que no hay y no ofrece «Ver más»', async () => {
    await montar(() => Promise.resolve(paginaAuditoria([])));
    expect(await screen.findByText('No hay registros para estos filtros')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ver más' })).toBeNull();
  });

  it('filtrar por tipo y usuario vuelve a la primera página con esos filtros', async () => {
    const { espia } = await montar();
    await titulo('Cierre de caja');
    await usuario.seleccionar(screen.getByLabelText('Tipo'), 'cierre_caja');
    await usuario.seleccionar(screen.getByLabelText('Usuario'), '3');
    await usuario.type(screen.getByLabelText('Desde'), '2026-11-01');
    await usuario.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => {
      expect(espia.mock.calls.at(-1)?.[0]).toEqual({ ...SIN_FILTROS, tipo: 'cierre_caja', usuarioId: 3, desde: '2026-11-01' });
    });
  });

  it('el filtro de usuario lista también a los desactivados, marcados', async () => {
    await montar();
    await titulo('Cierre de caja');
    expect(within(screen.getByLabelText('Usuario')).getByRole('option', { name: 'Ex Ficticio (inactivo)' })).toBeInTheDocument();
  });

  it('entidad e id se mandan recortados', async () => {
    const { espia } = await montar();
    await titulo('Cierre de caja');
    await usuario.type(screen.getByLabelText('Entidad'), 'turno');
    await usuario.type(screen.getByLabelText('ID de la entidad'), '501');
    await usuario.click(screen.getByRole('button', { name: 'Buscar' }));
    await waitFor(() => {
      expect(espia.mock.calls.at(-1)?.[0]).toMatchObject({ entidad: 'turno', entidadId: '501' });
    });
  });

  it('un 403 dice que falta permiso, sin botón de reintento', async () => {
    await montar(() => Promise.reject(new ErrorApiPanel(403, 'Rol requerido: admin', null)));
    expect(await screen.findByText('No tenés permiso para ver la auditoría.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull();
  });

  it('un error de red o del servidor ofrece reintentar y al reintentar carga', async () => {
    let falla = true;
    const { espia } = await montar(() =>
      falla ? Promise.reject(new ErrorApiPanel(500, 'boom', null)) : Promise.resolve(paginaAuditoria([registroAuditoria()])),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar la auditoría');
    falla = false;
    await usuario.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await titulo('Cierre de caja')).toBeInTheDocument();
    expect(espia).toHaveBeenCalledTimes(2);
  });
});
