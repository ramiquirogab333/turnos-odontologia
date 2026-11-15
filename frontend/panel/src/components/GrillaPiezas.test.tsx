import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { PiezaVigente } from '../lib/tipos';
import { GrillaPiezas } from './GrillaPiezas';

const base = userEvent.setup();
const usuario = {
  click: (el: Element) => act(() => base.click(el)),
  tab: () => act(() => base.tab()),
  teclas: (t: string) => act(() => base.keyboard(t)),
};

const VIGENTES: readonly PiezaVigente[] = [
  { pieza: 16, estado_pieza: null, caras: { O: 'caries' } },
  { pieza: 36, estado_pieza: 'endodoncia', caras: {} },
];

function montar(sobre: Partial<Parameters<typeof GrillaPiezas>[0]> = {}) {
  const alElegir = vi.fn<(pieza: number) => void>();
  render(<GrillaPiezas vigentes={VIGENTES} temporales={false} seleccionada={null} puedeElegir onElegir={alElegir} {...sobre} />);
  return alElegir;
}

describe('GrillaPiezas', () => {
  it('cada pieza muestra su número y su estado vigente como texto, no solo con color', () => {
    montar();
    expect(screen.getByRole('button', { name: '16 Caries: oclusal' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '36 Endodoncia' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '11 Sin hallazgos' })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(32);
  });

  it('agrupa por cuadrante: cuatro grupos de 8 piezas permanentes en 2 filas de 4 a 360 px', () => {
    montar();
    const grupos = screen.getAllByRole('group');
    expect(grupos).toHaveLength(4);
    expect(within(grupos[0] as HTMLElement).getAllByRole('button')).toHaveLength(8);
    expect(grupos[0]).toHaveClass('cuadrante', 'cuadrante-permanente');
  });

  it('los temporales son 4 cuadrantes de 5 piezas, del 51 al 85', () => {
    montar({ temporales: true });
    expect(screen.getAllByRole('button')).toHaveLength(20);
    expect(screen.getByRole('button', { name: /^51 / })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^85 / })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^11 / })).toBeNull();
    expect(screen.getAllByRole('group')[0]).toHaveClass('cuadrante-temporal');
  });

  it('elegir una pieza avisa su número y marca la seleccionada', async () => {
    const alElegir = montar({ seleccionada: 16 });
    expect(screen.getByRole('button', { name: '16 Caries: oclusal' })).toHaveAttribute('aria-pressed', 'true');
    await usuario.click(screen.getByRole('button', { name: '36 Endodoncia' }));
    expect(alElegir).toHaveBeenCalledWith(36);
  });

  it('con solo lectura las piezas no son botones pero se leen igual', () => {
    montar({ puedeElegir: false });
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('Caries: oclusal')).toBeInTheDocument();
    expect(screen.getByText('48')).toBeInTheDocument();
  });

  it('con teclado: una sola pieza por cuadrante en el orden de tabulación y flechas para moverse dentro', async () => {
    const alElegir = montar();
    await usuario.tab();
    expect(screen.getByRole('button', { name: /^11 / })).toHaveFocus();
    await usuario.teclas('{ArrowRight}{ArrowRight}');
    expect(screen.getByRole('button', { name: /^13 / })).toHaveFocus();
    await usuario.teclas('{ArrowLeft}');
    expect(screen.getByRole('button', { name: /^12 / })).toHaveFocus();
    await usuario.teclas('{End}');
    expect(screen.getByRole('button', { name: /^18 / })).toHaveFocus();
    await usuario.teclas('{Home}');
    expect(screen.getByRole('button', { name: /^11 / })).toHaveFocus();
    await usuario.tab();
    expect(screen.getByRole('button', { name: /^21 / })).toHaveFocus();
    await usuario.teclas('{Enter}');
    expect(alElegir).toHaveBeenCalledWith(21);
  });
});
