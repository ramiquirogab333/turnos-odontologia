import { expect, test, type Page } from '@playwright/test';
import { ingresar, verificarPantalla } from './ayudas';
import {
  EMAIL_ODONTOLOGA,
  EMAIL_RECEPCION,
  idDeUsuario,
  leerRegistrosOdontograma,
  sembrar,
  sembrarAtendido,
  sembrarPaciente,
  type Semilla,
} from './datos';

/** Odontograma del panel (C-16, R7) contra el backend real. Datos 100 % sintéticos (R19). */
let semilla: Semilla;
let lucia: number;

test.beforeEach(async () => {
  semilla = await sembrar();
  lucia = await sembrarPaciente('Lucía', 'Ejemplo', '99000001');
});

async function agregarAlLote(page: Page, pieza: string, estado: string, cara?: string): Promise<void> {
  await page.getByRole('button', { name: new RegExp(`^${pieza} `) }).click();
  await page.getByLabel('Estado').selectOption({ label: estado });
  if (cara !== undefined) await page.getByLabel('Cara').selectOption({ label: cara });
  await page.getByRole('button', { name: 'Agregar al lote' }).click();
}

test('la odontóloga arma un lote de 2 hallazgos, lo registra, corrige con «Sano» y el historial muestra 3 registros', async ({ page }) => {
  await sembrarAtendido(semilla, lucia, 30);
  const ana = await idDeUsuario(EMAIL_ODONTOLOGA);

  await ingresar(page, EMAIL_ODONTOLOGA);
  await page.goto(`/#/pacientes/${String(lucia)}?pestana=odontograma`);
  await expect(page.getByRole('button', { name: '16 Sin hallazgos' })).toBeVisible();
  await verificarPantalla(page, 'odontograma vacío');

  await agregarAlLote(page, '16', 'Caries', 'oclusal');
  await agregarAlLote(page, '36', 'Endodoncia');
  await expect(page.getByRole('list', { name: 'Lote de hallazgos' }).getByRole('listitem')).toHaveCount(2);
  await verificarPantalla(page, 'lote armado');
  await page.getByRole('button', { name: 'Registrar 2 hallazgos' }).click();
  await expect(page.getByText('Registramos 2 hallazgos')).toBeVisible();
  await expect(page.getByRole('button', { name: '16 Caries: oclusal' })).toBeVisible();
  await expect(page.getByRole('button', { name: '36 Endodoncia' })).toBeVisible();

  const guardados = await leerRegistrosOdontograma(lucia);
  expect(guardados.map((r) => [r.pieza, r.cara, r.estado])).toEqual([
    [16, 'O', 'caries'],
    [36, null, 'endodoncia'],
  ]);
  expect(guardados.every((r) => r.registrado_por === ana)).toBe(true);

  // Corregir es registrar un hallazgo nuevo: el historial no se edita ni se borra (RN-CL-01).
  await agregarAlLote(page, '16', 'Sano', 'oclusal');
  await page.getByRole('button', { name: 'Registrar 1 hallazgo' }).click();
  await expect(page.getByRole('button', { name: '16 Sin hallazgos' })).toBeVisible();
  await page.getByRole('button', { name: 'Ver historial' }).click();
  await expect(page.getByRole('list', { name: 'Historial de hallazgos' }).getByRole('listitem')).toHaveCount(3);
  expect(await leerRegistrosOdontograma(lucia)).toHaveLength(3);
  await verificarPantalla(page, 'historial del odontograma');
});

test('recepción registra un hallazgo en cualquier paciente, sin turnos atendidos', async ({ page }) => {
  await ingresar(page, EMAIL_RECEPCION);
  await page.goto(`/#/pacientes/${String(lucia)}?pestana=odontograma`);
  await agregarAlLote(page, '11', 'Obturado', 'vestibular');
  await page.getByRole('button', { name: 'Registrar 1 hallazgo' }).click();
  await expect(page.getByText('Registramos 1 hallazgo')).toBeVisible();
  await expect(page.getByRole('button', { name: '11 Obturado: vestibular' })).toBeVisible();
  const guardados = await leerRegistrosOdontograma(lucia);
  expect(guardados.map((r) => [r.pieza, r.cara, r.estado])).toEqual([[11, 'V', 'obturado']]);
  await verificarPantalla(page, 'odontograma de recepción');
});

test('solo con teclado se elige la pieza 48, su estado y se registra el lote con el foco siempre visible', async ({ page }) => {
  await sembrarAtendido(semilla, lucia, 30);
  await ingresar(page, EMAIL_ODONTOLOGA);
  await page.goto(`/#/pacientes/${String(lucia)}?pestana=odontograma`);
  await expect(page.getByRole('button', { name: '41 Sin hallazgos' })).toBeVisible();

  const primera = page.getByRole('button', { name: /^41 / });
  await primera.focus();
  for (let i = 0; i < 7; i += 1) await page.keyboard.press('ArrowRight');
  const pieza48 = page.getByRole('button', { name: /^48 / });
  await expect(pieza48).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(pieza48).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Pieza 48')).toBeVisible();

  await page.getByLabel('Estado').focus();
  await page.keyboard.type('Implante');
  await expect(page.getByLabel('Estado')).toHaveValue('implante');
  const agregar = page.getByRole('button', { name: 'Agregar al lote' });
  await agregar.focus();
  await expect(agregar).toBeFocused();
  await page.keyboard.press('Enter');
  const registrar = page.getByRole('button', { name: 'Registrar 1 hallazgo' });
  await registrar.focus();
  await expect(registrar).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: '48 Implante' })).toBeVisible();
  expect((await leerRegistrosOdontograma(lucia)).map((r) => [r.pieza, r.estado])).toEqual([[48, 'implante']]);
});
