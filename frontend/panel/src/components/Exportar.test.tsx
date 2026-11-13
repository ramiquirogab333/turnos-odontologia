import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Api } from '../lib/api';
import type { ArchivoExportado, ErrorExportacion, ParametrosExportacion, Resultado, Rol } from '../lib/tipos';
import { apiFalsa } from '../test/datos';
import { Exportar } from './Exportar';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  type: (el: Element, texto: string) => act(() => base.type(el, texto)),
  seleccionar: (el: Element, valor: string) => act(() => base.selectOptions(el, valor)),
};

const HOY = '2026-11-13';
const ARCHIVO: ArchivoExportado = { blob: new Blob(['id']), nombre: 'turnos_2026-11-13.csv' };

type Descarga = Api['descargarExportacion'];

async function montar(roles: readonly Rol[], descargar: Descarga = () => Promise.resolve({ ok: true, valor: ARCHIVO })) {
  const espia = vi.fn<Descarga>(descargar);
  const guardar = vi.fn<(archivo: ArchivoExportado) => void>();
  await act(async () => {
    render(<Exportar api={apiFalsa({ descargarExportacion: espia })} roles={roles} hoy={HOY} guardar={guardar} />);
    await Promise.resolve();
  });
  return { espia, guardar };
}

const opciones = () => screen.getAllByRole('option').map((o) => o.textContent);
const boton = () => screen.getByRole('button', { name: /Descargar CSV|Preparando archivo/ });

describe('Exportar', () => {
  it('recepción elige entre turnos y cierres de caja, no ve pacientes', async () => {
    await montar(['recepcion']);
    expect(opciones()).toEqual(['Turnos', 'Cierres de caja']);
    expect(screen.queryByLabelText('Incluir pacientes inactivos')).toBeNull();
  });

  it('el admin ve además pacientes y su casilla de inactivos', async () => {
    await montar(['admin']);
    expect(opciones()).toEqual(['Turnos', 'Pacientes', 'Cierres de caja']);
    await usuario.seleccionar(screen.getByLabelText('¿Qué querés exportar?'), 'pacientes');
    expect(screen.getByLabelText('Incluir pacientes inactivos')).not.toBeChecked();
  });

  it('avisa que el archivo contiene datos personales', async () => {
    await montar(['recepcion']);
    expect(screen.getByText(/datos personales/i)).toBeInTheDocument();
  });

  it('descarga los turnos del rango, deja el archivo y vuelve a habilitar el botón', async () => {
    const { espia, guardar } = await montar(['recepcion']);
    await usuario.type(screen.getByLabelText('Desde (opcional)'), '2026-11-16');
    await usuario.type(screen.getByLabelText('Hasta (opcional)'), '2026-11-20');
    await usuario.click(boton());
    await waitFor(() => {
      expect(guardar).toHaveBeenCalledWith(ARCHIVO);
    });
    const esperado: ParametrosExportacion = { entidad: 'turnos', desde: '2026-11-16', hasta: '2026-11-20', incluirInactivos: false };
    expect(espia).toHaveBeenCalledWith(esperado, HOY);
    expect(await screen.findByText(/Descargamos turnos_2026-11-13\.csv/)).toBeInTheDocument();
    expect(boton()).toBeEnabled();
    expect(boton()).toHaveTextContent('Descargar CSV');
  });

  it('mientras prepara el archivo el botón está deshabilitado y un segundo toque no pide otra descarga', async () => {
    let terminar: (r: Resultado<ArchivoExportado, ErrorExportacion>) => void = () => undefined;
    const { espia } = await montar(['recepcion'], () => new Promise((res) => { terminar = res; }));
    await usuario.click(boton());
    expect(boton()).toBeDisabled();
    expect(boton()).toHaveTextContent('Preparando archivo…');
    await usuario.click(boton());
    expect(espia).toHaveBeenCalledTimes(1);
    await act(async () => {
      terminar({ ok: true, valor: ARCHIVO });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(boton()).toBeEnabled();
    });
  });

  it('el admin exporta pacientes con inactivos si tilda la casilla', async () => {
    const { espia } = await montar(['admin']);
    await usuario.seleccionar(screen.getByLabelText('¿Qué querés exportar?'), 'pacientes');
    await usuario.click(screen.getByLabelText('Incluir pacientes inactivos'));
    await usuario.click(boton());
    await waitFor(() => {
      expect(espia).toHaveBeenCalledWith({ entidad: 'pacientes', desde: null, hasta: null, incluirInactivos: true }, HOY);
    });
  });

  it('un 403 muestra el mensaje de permiso, no guarda nada y deja reintentar', async () => {
    const { guardar } = await montar(['recepcion'], () => Promise.resolve({ ok: false, error: { tipo: 'sin_permiso' } }));
    await usuario.click(boton());
    expect(await screen.findByRole('alert')).toHaveTextContent('No tenés permiso para exportar esto.');
    expect(guardar).not.toHaveBeenCalled();
    expect(boton()).toBeEnabled();
  });

  it('un 429 con 10 minutos de espera lo dice en lenguaje claro', async () => {
    await montar(['recepcion'], () => Promise.resolve({ ok: false, error: { tipo: 'limite', minutos: 10 } }));
    await usuario.click(boton());
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Hiciste muchas exportaciones seguidas. Probá de nuevo en 10 minutos',
    );
  });

  it('un corte de red tiene su propio mensaje', async () => {
    await montar(['recepcion'], () => Promise.resolve({ ok: false, error: { tipo: 'red' } }));
    await usuario.click(boton());
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos conectarnos');
  });

  it('un rango con «desde» posterior a «hasta» se rechaza sin pedir nada', async () => {
    const { espia } = await montar(['recepcion']);
    await usuario.type(screen.getByLabelText('Desde (opcional)'), '2026-11-20');
    await usuario.type(screen.getByLabelText('Hasta (opcional)'), '2026-11-16');
    await usuario.click(boton());
    expect(await screen.findByRole('alert')).toHaveTextContent('Revisá el rango de fechas');
    expect(espia).not.toHaveBeenCalled();
  });

  it('un error nuevo reemplaza al éxito anterior y un éxito limpia el error', async () => {
    const respuestas: Resultado<ArchivoExportado, ErrorExportacion>[] = [
      { ok: true, valor: ARCHIVO },
      { ok: false, error: { tipo: 'servidor' } },
      { ok: true, valor: ARCHIVO },
    ];
    await montar(['recepcion'], () => Promise.resolve(respuestas.shift() ?? { ok: false, error: { tipo: 'servidor' } }));
    await usuario.click(boton());
    await screen.findByText(/Descargamos/);
    await usuario.click(boton());
    expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos preparar el archivo');
    expect(screen.queryByText(/Descargamos/)).toBeNull();
    await usuario.click(boton());
    await screen.findByText(/Descargamos/);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
