import { expect, test, type Page } from '@playwright/test';
import { API, ingresar } from './ayudas';
import { sembrar } from './datos';

/**
 * Sesión del panel (C-08, D10) contra el backend real y el proxy de 5174: el refresh vive en una cookie HttpOnly,
 * el access solo en memoria, y la renovación sobrevive a recargas, pestañas nuevas y pestañas simultáneas.
 */
test.beforeEach(async () => {
  await sembrar();
});

const agenda = (page: Page) => page.getByRole('heading', { name: 'Agenda', level: 1 });
const ingreso = (page: Page) => page.getByRole('heading', { name: 'Ingresá al panel' });

test('(a) ingresa, recarga y abre una pestaña nueva sin pedir ingreso; la cookie es HttpOnly, Secure y Strict', async ({ page, context }) => {
  await ingresar(page);

  const cookies = (await context.cookies()).filter((c) => c.name === 'refresh_token');
  expect(cookies, 'el navegador guardó la cookie de refresh a través del proxy de 5174').toHaveLength(1);
  expect(cookies[0]).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Strict', path: '/api/auth' });

  await page.reload();
  await expect(agenda(page)).toBeVisible();
  await expect(ingreso(page)).toHaveCount(0);

  const otra = await context.newPage();
  await otra.goto('/');
  await expect(agenda(otra)).toBeVisible();
  await expect(ingreso(otra)).toHaveCount(0);
});

test('(b) ningún token queda en el almacenamiento ni en cookies legibles por JavaScript', async ({ page }) => {
  await ingresar(page);
  const visto = await page.evaluate(() => ({
    local: localStorage.length,
    sesion: sessionStorage.length,
    cookies: document.cookie,
  }));
  expect(visto.local).toBe(0);
  expect(visto.sesion).toBe(0);
  expect(visto.cookies).not.toContain('refresh_token');
  expect(visto.cookies).not.toContain('eyJ'); // ningún JWT
});

test('(c) dos pestañas que se recargan a la vez conservan la sesión (una sola rotación gana, la otra espera)', async ({ page, context }) => {
  await ingresar(page);
  const otra = await context.newPage();
  await otra.goto('/');
  await expect(agenda(otra)).toBeVisible();

  const respuestas: number[] = [];
  for (const p of [page, otra]) {
    p.on('response', (r) => {
      if (r.url().endsWith('/api/auth/refresh')) respuestas.push(r.status());
    });
  }
  await Promise.all([page.reload(), otra.reload()]);
  await expect(agenda(page)).toBeVisible();
  await expect(agenda(otra)).toBeVisible();
  await expect(ingreso(page)).toHaveCount(0);
  await expect(ingreso(otra)).toHaveCount(0);
  expect(respuestas.length, 'cada pestaña renovó al abrir').toBeGreaterThanOrEqual(2);
  expect(respuestas.every((s) => s === 200), `todas las renovaciones fueron 200, no hubo un 401 que cierre la sesión: ${respuestas.join(',')}`).toBe(true);
});

test('(d) salir revoca de verdad: al recargar pide ingreso y el refresh viejo ya no sirve', async ({ page, context, request }) => {
  await ingresar(page);
  const antes = (await context.cookies()).find((c) => c.name === 'refresh_token');
  expect(antes).toBeDefined();

  await page.getByRole('button', { name: 'Salir' }).click();
  await expect(ingreso(page)).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Saliste del panel.');
  expect((await context.cookies()).filter((c) => c.name === 'refresh_token')).toHaveLength(0);

  await page.reload();
  await expect(ingreso(page)).toBeVisible();
  await expect(agenda(page)).toHaveCount(0);

  // Aunque alguien conserve el valor de la cookie, el servidor lo rechaza.
  const robado = await request.post(`${API}/api/auth/refresh`, {
    headers: { Cookie: `refresh_token=${antes?.value ?? ''}`, 'X-Panel-Csrf': '1' },
  });
  expect(robado.status()).toBe(401);
});

test('(d2) salir en una pestaña saca a la otra del panel', async ({ page, context }) => {
  await ingresar(page);
  const otra = await context.newPage();
  await otra.goto('/');
  await expect(agenda(otra)).toBeVisible();

  await page.getByRole('button', { name: 'Salir' }).click();
  await expect(ingreso(page)).toBeVisible();
  await expect(ingreso(otra)).toBeVisible();
  await expect(otra.getByRole('status')).toContainText('Cerraste la sesión en otra pestaña.');
  await expect(agenda(otra)).toHaveCount(0);
});

test('(e) volver con "atrás" después de salir no muestra la agenda', async ({ page }) => {
  await page.goto('about:blank');
  await ingresar(page);
  await page.getByRole('button', { name: 'Salir' }).click();
  await expect(ingreso(page)).toBeVisible();

  await page.goBack(); // sale del panel (about:blank)
  await page.goForward(); // vuelve: puede ser una página restaurada desde la memoria del navegador
  await expect(ingreso(page)).toBeVisible();
  await expect(agenda(page)).toHaveCount(0);
});

test('credenciales inválidas: mismo mensaje, sin cookie y sin agenda', async ({ page, context }) => {
  await page.goto('/');
  await expect(ingreso(page)).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0); // abrir sin sesión no es un error
  await page.getByLabel('Correo electrónico').fill('nadie@turnos.test');
  await page.getByLabel('Contraseña').fill('clave-incorrecta-123');
  await page.getByRole('button', { name: 'Ingresar al panel' }).click();
  await expect(page.getByRole('alert')).toContainText('El correo o la contraseña no son correctos.');
  expect((await context.cookies()).filter((c) => c.name === 'refresh_token')).toHaveLength(0);
  await expect(agenda(page)).toHaveCount(0);
});

test('(f) salir en una pestaña y, en la otra sin recargar ni aviso entre pestañas, el siguiente pedido lleva al ingreso (el access ya no sirve)', async ({ page, context }) => {
  await ingresar(page);
  const otra = await context.newPage();
  // Sin BroadcastChannel: la otra pestaña no se entera por aviso, solo puede enterarse porque el servidor la rechaza (C-15).
  await otra.addInitScript(() => {
    Object.defineProperty(window, 'BroadcastChannel', { value: undefined, configurable: true });
  });
  await otra.goto('/');
  await expect(agenda(otra)).toBeVisible();

  await page.getByRole('button', { name: 'Salir' }).click();
  await expect(ingreso(page)).toBeVisible();
  await expect(agenda(otra)).toBeVisible(); // todavía no pidió nada: no se enteró

  await otra.getByRole('button', { name: 'Día siguiente' }).click(); // el siguiente pedido autenticado
  await expect(ingreso(otra)).toBeVisible();
  await expect(agenda(otra)).toHaveCount(0);
});

test('(g) la sexta contraseña incorrecta de un email propio muestra el bloqueo con minutos, a 360 px y sin scroll horizontal', async ({ page }) => {
  const email = `bloqueo.${String(Date.now())}@turnos.test`; // un email por corrida: el contador sobrevive entre proyectos
  await page.goto('/');
  for (let i = 0; i < 5; i += 1) {
    await page.getByLabel('Correo electrónico').fill(email);
    await page.getByLabel('Contraseña').fill('clave-incorrecta-123');
    await page.getByRole('button', { name: 'Ingresar al panel' }).click();
    await expect(page.getByRole('alert')).toContainText('El correo o la contraseña no son correctos.');
  }
  await page.getByLabel('Contraseña').fill('clave-incorrecta-123');
  await page.getByRole('button', { name: 'Ingresar al panel' }).click();
  await expect(page.getByRole('alert')).toContainText('Demasiados intentos. Probá de nuevo en 15 minutos');
  await expect(agenda(page)).toHaveCount(0);
  const medidas = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    ancho: document.documentElement.clientWidth,
  }));
  expect(medidas.scroll).toBeLessThanOrEqual(medidas.ancho);
});
