import { expect, test, type Page } from '@playwright/test';
import { diaDe, enMs, HORA, ingresar, irAlDia, verificarPantalla } from './ayudas';
import { EMAIL_ODONTOLOGA, EMAIL_RECEPCION, sembrar, sembrarTurno, type Semilla } from './datos';

/** Agenda por rol y por vista, a 360px y a 1280px, contra el backend real. */
let semilla: Semilla;

test.beforeEach(async () => {
  semilla = await sembrar();
});

const cabecera = (page: Page) => page.getByRole('heading', { name: 'Agenda', level: 1 });

test('una pre-reserva va en la banda "No ocupan horario" y no entre los turnos del día', async ({ page }) => {
  // Dentro de ~1 día: está en el día de hoy o de mañana de la clínica; irAlDia lo encuentra.
  const inicio = enMs(26 * HORA);
  await sembrarTurno(semilla, { inicio, nombre: 'Carlos Sintético', sena: 'acreditado' });
  await sembrarTurno(semilla, { inicio, estado: 'en_espera', nombre: 'Sofía Muestra', sena: 'pendiente', profesional: 'bruno', sillon: 2 });
  await ingresar(page);
  await irAlDia(page, diaDe(inicio));

  const principal = page.getByRole('list', { name: 'Turnos del día' });
  await expect(principal.getByText('Carlos Sintético')).toBeVisible();
  await expect(principal.getByText('Sofía Muestra')).toHaveCount(0);
  const banda = page.getByRole('region', { name: 'Pre-reservas sin pagar' });
  await expect(banda).toContainText('No ocupan horario');
  await expect(banda).toContainText('Sofía Muestra');
  await expect(banda).toContainText('Esperando seña');
  await verificarPantalla(page, 'agenda del día con banda de pre-reservas');
});

test('la odontóloga ve solo su agenda, sin teléfonos ni acciones de escritura', async ({ page }) => {
  const inicio = enMs(26 * HORA);
  await sembrarTurno(semilla, { inicio, nombre: 'Carlos Sintético', sena: 'acreditado' });
  await sembrarTurno(semilla, { inicio, nombre: 'Lucía Ejemplo', profesional: 'bruno', sillon: 2 });
  await ingresar(page, EMAIL_ODONTOLOGA);
  await irAlDia(page, diaDe(inicio));

  await expect(page.getByText('Carlos Sintético')).toBeVisible();
  await expect(page.getByText('Lucía Ejemplo')).toHaveCount(0);
  await expect(page.getByText('+5491144445555')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Nuevo turno' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^(Marcar|Cancelar turno)/ })).toHaveCount(0);
  await expect(page.getByLabel('Profesional')).toHaveCount(0);
});

test('recepción ve el teléfono y las acciones que el servidor habilita, y puede filtrar por sillón', async ({ page }) => {
  const inicio = enMs(26 * HORA);
  await sembrarTurno(semilla, { inicio, nombre: 'Carlos Sintético', sena: 'acreditado' }); // sillón 1
  await sembrarTurno(semilla, { inicio, nombre: 'Lucía Ejemplo', profesional: 'bruno', sillon: 2 });
  await ingresar(page, EMAIL_RECEPCION);
  await irAlDia(page, diaDe(inicio));

  await expect(page.getByText('+5491144445555').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancelar turno' }).first()).toBeVisible(); // faltan más de 24 h
  await page.getByLabel('Sillón').selectOption({ label: 'Sillón 2' });
  await expect(page.getByText('Lucía Ejemplo')).toBeVisible();
  await expect(page.getByText('Carlos Sintético')).toHaveCount(0);
  await page.getByLabel('Sillón').selectOption({ label: 'Todos los sillones' });
  await expect(page.getByText('Carlos Sintético')).toBeVisible();
});

test('cambia a la vista semana: lista por día a 360px y grilla de lunes a domingo a 1280px', async ({ page }, info) => {
  const inicio = enMs(26 * HORA);
  await sembrarTurno(semilla, { inicio, nombre: 'Carlos Sintético' });
  await ingresar(page);
  await irAlDia(page, diaDe(inicio));
  await page.getByRole('button', { name: 'Semana' }).click();
  await expect(page.getByRole('heading', { level: 2, name: /^Semana del / })).toBeVisible();

  if (info.project.name === 'chromium-1280') {
    const grilla = page.getByRole('table', { name: /^Semana del / });
    await expect(grilla.getByRole('columnheader')).toHaveCount(7);
    await expect(grilla.getByText('Carlos Sintético')).toBeVisible();
  } else {
    await expect(page.getByRole('table')).toHaveCount(0);
    await expect(page.getByRole('heading', { level: 3 })).toHaveCount(1);
    await expect(page.getByText('Carlos Sintético')).toBeVisible();
  }
  await verificarPantalla(page, `vista semana (${info.project.name})`);
});

test('a 360px no hay scroll horizontal y todo lo tocable mide 48px, también en el ingreso y en el alta manual', async ({ page }, info) => {
  test.skip(info.project.name !== 'chromium-360', 'verificación específica del viewport de 360px');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Ingresá al panel' })).toBeVisible();
  await verificarPantalla(page, 'ingreso');
  await ingresar(page);
  await expect(cabecera(page)).toBeVisible();
  await verificarPantalla(page, 'agenda vacía');

  await page.getByRole('button', { name: 'Nuevo turno' }).click();
  await expect(page.getByRole('dialog', { name: 'Nuevo turno' })).toBeVisible();
  await verificarPantalla(page, 'alta manual');
});
