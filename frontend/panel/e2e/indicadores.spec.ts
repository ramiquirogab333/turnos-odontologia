import { expect, test } from '@playwright/test';
import { hoyClinica } from '../src/lib/tiempo';
import { ingresar, instanteClinica, irASeccion, verificarPantalla } from './ayudas';
import { cambiarEstadoTurno, sembrar, sembrarTurno, type Semilla } from './datos';

/** Indicadores (C-12) contra el backend real: ocupación por sillón y ausentismo con lo recuperado en señas. */
let semilla: Semilla;

test.beforeEach(async () => {
  semilla = await sembrar();
});

test('un sillón cuyo único turno es una pre-reserva figura con 0 %; con el mismo turno reservado, con su porcentaje', async ({ page }) => {
  const hoy = hoyClinica(new Date());
  // La ocupación no depende de la hora en que corre la suite: el turno de hoy a las 12:00 cuenta o no cuenta por su estado.
  const turno = await sembrarTurno(semilla, { inicio: instanteClinica(hoy, '12:00'), estado: 'en_espera', sena: 'pendiente' });

  await ingresar(page);
  await irASeccion(page, 'Indicadores');

  const sillon1 = page.getByRole('region', { name: 'Ocupación de Sillón 1' });
  await expect(sillon1).toContainText('0 % ocupado');
  await expect(sillon1).toContainText('0 de ');
  // El otro sillón no tiene turnos: también 0 %, y tampoco cuenta la pre-reserva de Sillón 1.
  await expect(page.getByRole('region', { name: 'Ocupación de Sillón 2' })).toContainText('0 turnos');
  await verificarPantalla(page, 'indicadores con una pre-reserva');

  await cambiarEstadoTurno(turno, 'reservado');
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Indicadores' })).toBeVisible();
  await expect(sillon1).toContainText(/2,1 % ocupado/);
  await expect(sillon1).toContainText(/30 de 14\d\d minutos/);
  await expect(sillon1).toContainText('1 turno');
});

test('la tasa de ausentismo suma a quien faltó y muestra la seña retenida en pesos', async ({ page }) => {
  const hoy = hoyClinica(new Date());
  await sembrarTurno(semilla, { inicio: instanteClinica(hoy, '09:00'), estado: 'ausente', sena: 'no_reembolsado', nombre: 'Carlos Sintético' });
  await sembrarTurno(semilla, { inicio: instanteClinica(hoy, '10:00'), estado: 'atendido', nombre: 'Lucía Ejemplo' });

  await ingresar(page);
  await irASeccion(page, 'Indicadores');

  const bloque = page.getByRole('region', { name: 'Ausentismo' });
  await expect(bloque).toContainText('Tasa de ausentismo: 50 %');
  await expect(bloque).toContainText('1 ausente de 2 turnos marcados');
  await expect(bloque).toContainText('Señas retenidas: $ 4.500,00 (1 seña)');
  await expect(bloque.getByText('Dra. Ana Ficticia')).toBeVisible();
  await verificarPantalla(page, 'indicadores con ausentismo');

  // Cambiar de período vuelve a pedir los dos bloques sin recargar la página.
  await page.getByRole('button', { name: 'Últimos 30 días' }).click();
  await expect(page.getByRole('button', { name: 'Últimos 30 días' })).toHaveAttribute('aria-pressed', 'true');
  await expect(bloque).toContainText('Tasa de ausentismo: 50 %');
  await verificarPantalla(page, 'indicadores de 30 días');
});
