import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Confirmacion } from './Confirmacion';

function montar(codigoGestion: string) {
  render(
    <Confirmacion
      inicio="2026-11-16T10:00:00-03:00"
      fin="2026-11-16T10:30:00-03:00"
      codigoGestion={codigoGestion}
      tratamientoNombre="Limpieza"
      profesionalNombre="Dra. Sintética"
      onNueva={vi.fn()}
    />,
  );
}

describe('Confirmacion: gestión del turno (C-07)', () => {
  it('ofrece "Gestionar mi turno" con el código en el fragmento, no en la ruta ni en la query', () => {
    montar('ABCD2345');
    const enlace = screen.getByRole('link', { name: /gestionar mi turno/i });
    expect(enlace).toHaveAttribute('href', '/gestionar#ABCD2345');
  });

  it('escapa el código para que un carácter raro no rompa el enlace', () => {
    montar('a b/c');
    expect(screen.getByRole('link', { name: /gestionar mi turno/i })).toHaveAttribute('href', '/gestionar#a%20b%2Fc');
  });

  it('explica la ventana de 24 h', () => {
    montar('ABCD2345');
    expect(screen.getByText(/Podés cancelar o cambiar el horario hasta 24 h antes/)).toBeInTheDocument();
  });
});
