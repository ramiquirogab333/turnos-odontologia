import { expect, test } from '@playwright/test';
import {
  API,
  NOMBRE,
  TELEFONO,
  completarContacto,
  diaObjetivo,
  llegarAlPaso3,
  verificarPantalla,
} from './ayudas';
import { leerTurnos, sembrar, vaciarTurnos } from './datos';

/**
 * C-15 (11.3): cuando la API limita los pedidos (429), el paciente ve cuánto esperar, conserva lo que cargó y no ve
 * ningún turno como reservado. El comportamiento del backend lo prueba pytest: acá se intercepta la respuesta.
 */
test.beforeAll(async () => {
  const salud = await fetch(`${API}/api/health`);
  expect(salud.ok, 'el backend debe estar arriba (docker compose up -d postgres redis backend)').toBe(true);
  await sembrar();
});

test.beforeEach(async ({ page }) => {
  await vaciarTurnos();
  await page.goto('/');
});

test('un 429 en la reserva muestra "5 minutos" en el último paso, con los datos intactos y sin turno', async ({ page }) => {
  await page.route(/\/api\/public\/turnos$/, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 429,
      headers: { 'Retry-After': '300', 'Content-Type': 'application/json' },
      body: JSON.stringify({ detail: 'Demasiados intentos. Probá de nuevo más tarde.', motivo: 'demasiados_intentos' }),
    });
  });

  await llegarAlPaso3(page, diaObjetivo(), '10:00');
  await completarContacto(page);
  await page.getByRole('button', { name: 'Confirmar turno' }).click();

  const aviso = page.getByRole('alert');
  await expect(aviso).toContainText('Hiciste muchos pedidos seguidos. Probá de nuevo en 5 minutos.');
  await expect(page.getByRole('heading', { name: 'Confirmá tus datos' })).toBeVisible(); // sigue en el último paso
  await expect(page.getByLabel('Nombre completo')).toHaveValue(NOMBRE);
  await expect(page.getByLabel('Teléfono (WhatsApp)')).toHaveValue(TELEFONO);
  await expect(page.getByText(/código de gestión/i)).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Turno reservado' })).toHaveCount(0);
  await verificarPantalla(page, 'último paso con el aviso de límite (360 px)');
  expect(await leerTurnos()).toHaveLength(0);
});
