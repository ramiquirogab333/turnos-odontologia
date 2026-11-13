import { expect, test } from '@playwright/test';
import { accesoPorApi, API, enMs, HORA, ingresar, irASeccion, MINUTO, verificarPantalla } from './ayudas';
import { EMAIL_ODONTOLOGA, sembrar, sembrarPaciente, sembrarTurno, type Semilla } from './datos';

/** Listado de pacientes (C-12) contra el backend real. Datos 100 % sintéticos (R19). */
let semilla: Semilla;

test.beforeEach(async () => {
  semilla = await sembrar();
});

test('la búsqueda de pacientes funciona a 360 px sin desplazamiento horizontal y filtra por nombre y por ausencias', async ({ page }) => {
  const lucia = await sembrarPaciente('Lucía', 'Ejemplo', '30111222');
  await sembrarPaciente('Martín', 'Prueba', '28999888');
  await sembrarTurno(semilla, { inicio: enMs(-3 * HORA), estado: 'ausente', nombre: 'Lucía Ejemplo', pacienteId: lucia });

  await ingresar(page);
  await irASeccion(page, 'Pacientes');

  const lista = page.getByRole('list', { name: 'Pacientes' });
  await expect(lista.getByText('Lucía Ejemplo')).toBeVisible();
  await expect(lista.getByText('Martín Prueba')).toBeVisible();
  await verificarPantalla(page, 'listado de pacientes');

  await page.getByRole('searchbox', { name: 'Buscar por nombre, apellido o DNI' }).fill('lucia');
  await expect(lista.getByText('Martín Prueba')).toHaveCount(0);
  await expect(lista.getByText('Lucía Ejemplo')).toBeVisible();
  await expect(lista.getByText(/DNI 30111222/)).toBeVisible();
  await expect(lista.getByText(/1 ausencia\b/)).toBeVisible();
  await verificarPantalla(page, 'resultado de la búsqueda');

  await page.getByRole('searchbox').fill('zzz');
  await expect(page.getByText('No encontramos pacientes con «zzz»')).toBeVisible();
  await expect(page.getByText(/buscá por DNI/)).toBeVisible();
  await verificarPantalla(page, 'búsqueda sin resultados');

  await page.getByRole('searchbox').fill('');
  await page.getByRole('button', { name: 'Con ausencias' }).click();
  await expect(page.getByRole('button', { name: 'Con ausencias' })).toHaveAttribute('aria-pressed', 'true');
  await expect(lista.getByText('Martín Prueba')).toHaveCount(0);
  await expect(lista.getByText('Lucía Ejemplo')).toBeVisible();

  // También se encuentra por el comienzo del DNI.
  await page.getByRole('button', { name: 'Con ausencias' }).click();
  await page.getByRole('searchbox').fill('2899');
  await expect(lista.getByText('Martín Prueba')).toBeVisible();
  await expect(lista.getByText('Lucía Ejemplo')).toHaveCount(0);
});

test('la odontóloga no ve la sección de pacientes y el servidor tampoco se la da', async ({ page, request }) => {
  await sembrarPaciente('Lucía', 'Ejemplo', '30111222');
  await sembrarTurno(semilla, { inicio: enMs(2 * HORA + 5 * MINUTO) });

  await ingresar(page, EMAIL_ODONTOLOGA);
  // C-10: la odontóloga ve una navegación acotada a su agenda y a Google Calendar (nada de pacientes ni caja).
  await expect(page.getByRole('navigation', { name: 'Secciones del panel' }).getByRole('link')).toHaveText(['Agenda', 'Google Calendar']);

  await page.goto('/#/pacientes');
  await expect(page.getByRole('heading', { level: 1, name: 'Agenda' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Pacientes' })).toHaveCount(0);

  const r = await request.get(`${API}/api/panel/pacientes/listado`, { headers: await accesoPorApi(request, EMAIL_ODONTOLOGA) });
  expect(r.status()).toBe(403);
});
