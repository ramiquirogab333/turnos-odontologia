import { expect, test, type Page } from '@playwright/test';
import { API, enMs, HORA, ingresar, irASeccion, verificarPantalla } from './ayudas';
import { EMAIL_ODONTOLOGA, leerCodigoGestion, leerRecordatorios, sembrar, sembrarTurno, type Semilla } from './datos';

/**
 * Recordatorios de WhatsApp (C-09; R7, R3) contra el backend real y el WORKER real (docker compose up -d postgres redis
 * backend worker, con RECORDATORIOS_INTERVALO_SEGUNDOS=3), a 360 px y a 1280 px. Datos 100 % sintéticos (R19).
 */
let semilla: Semilla;

test.beforeEach(async () => {
  semilla = await sembrar();
});

/** Espera a que el worker genere el recordatorio del turno (el trabajo corre cada 3 s). */
async function esperarRecordatorio(turnoId: number): Promise<void> {
  await expect
    .poll(async () => (await leerRecordatorios()).find((r) => r.turno_id === turnoId)?.estado, { timeout: 20_000 })
    .toBe('pendiente');
}

async function abrirSeccion(page: Page): Promise<void> {
  await ingresar(page);
  await irASeccion(page, 'Recordatorios');
}

test('el worker genera el recordatorio y el panel muestra el link de WhatsApp con el mensaje', async ({ page }) => {
  const turno = await sembrarTurno(semilla, { inicio: enMs(30 * HORA) });
  await esperarRecordatorio(turno);
  await abrirSeccion(page);

  const fila = page.getByRole('listitem').filter({ hasText: 'Carlos Sintético' });
  await expect(fila).toBeVisible();
  await expect(fila.getByText('Pendiente')).toBeVisible();
  const enlace = fila.getByRole('link', { name: 'Abrir WhatsApp' });
  const href = (await enlace.getAttribute('href')) ?? '';
  expect(href.startsWith('https://wa.me/5491144445555?text=')).toBe(true);
  const mensaje = new URL(href).searchParams.get('text') ?? '';
  expect(mensaje).toContain('Carlos Sintético');
  expect(mensaje).toMatch(/\d{2}:\d{2}/);
  expect(mensaje).toContain('/confirmar#');
  expect(mensaje).toContain('/gestionar#');
  await expect(enlace).toHaveAttribute('target', '_blank');
  await verificarPantalla(page, 'recordatorios');
});

test('Abrir WhatsApp abre otra pestaña, registra el envío y la fila pasa a Enviado', async ({ page, context }) => {
  const turno = await sembrarTurno(semilla, { inicio: enMs(30 * HORA) });
  await esperarRecordatorio(turno);
  // Sin red real: la pestaña de WhatsApp se atiende con una página vacía.
  await context.route('https://wa.me/**', (ruta) => ruta.fulfill({ contentType: 'text/html', body: '<p>WhatsApp (simulado)</p>' }));
  await abrirSeccion(page);

  const [popup] = await Promise.all([
    context.waitForEvent('page'),
    page.getByRole('link', { name: 'Abrir WhatsApp' }).click(),
  ]);
  expect(popup.url()).toContain('https://wa.me/5491144445555');
  await popup.close();

  const fila = page.getByRole('listitem').filter({ hasText: 'Carlos Sintético' });
  await expect(fila.getByText('Enviado')).toBeVisible();
  await verificarPantalla(page, 'recordatorio enviado');
  expect((await leerRecordatorios()).find((r) => r.turno_id === turno)?.estado).toBe('enviado');
});

test('cancelar el turno desde la gestión del paciente lo saca de la lista', async ({ page, request }) => {
  const turno = await sembrarTurno(semilla, { inicio: enMs(30 * HORA) });
  await esperarRecordatorio(turno);
  await abrirSeccion(page);
  await expect(page.getByRole('listitem').filter({ hasText: 'Carlos Sintético' })).toBeVisible();

  const codigo = await leerCodigoGestion(turno);
  const r = await request.post(`${API}/api/public/gestion/cancelar`, { headers: { 'X-Codigo-Gestion': codigo } });
  expect(r.status()).toBe(200);

  await page.getByRole('button', { name: 'Actualizar' }).click();
  await expect(page.getByText('No hay recordatorios por enviar')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Abrir WhatsApp' })).toHaveCount(0);
  expect((await leerRecordatorios()).find((x) => x.turno_id === turno)).toMatchObject({
    estado: 'anulado',
    motivo: 'turno_cancelado',
  });
});

test('"No se pudo enviar" deja el recordatorio fallido con el motivo', async ({ page }) => {
  const turno = await sembrarTurno(semilla, { inicio: enMs(30 * HORA) });
  await esperarRecordatorio(turno);
  await abrirSeccion(page);

  await page.getByRole('button', { name: 'No se pudo enviar' }).click();
  const dialogo = page.getByRole('dialog');
  await verificarPantalla(page, 'diálogo no se pudo enviar');
  await dialogo.getByRole('radio', { name: 'No tiene WhatsApp' }).check();
  await dialogo.getByRole('button', { name: 'Marcar como no enviado' }).click();

  await expect(page.getByText(/No se pudo enviar: no tiene WhatsApp/)).toBeVisible();
  expect((await leerRecordatorios()).find((r) => r.turno_id === turno)).toMatchObject({
    estado: 'fallido',
    motivo: 'sin_whatsapp',
  });
});

test('sin recordatorios por enviar se ve el estado vacío', async ({ page }) => {
  await sembrarTurno(semilla, { inicio: enMs(60 * HORA) }); // fuera de la anticipación de 48 h
  await abrirSeccion(page);
  await expect(page.getByText('No hay recordatorios por enviar')).toBeVisible();
  await verificarPantalla(page, 'recordatorios vacíos');
});

test('la odontóloga no ve la sección y #recordatorios la deja en la agenda', async ({ page }) => {
  const turno = await sembrarTurno(semilla, { inicio: enMs(30 * HORA) });
  await esperarRecordatorio(turno);
  await ingresar(page, EMAIL_ODONTOLOGA);
  await expect(page.getByRole('navigation', { name: 'Secciones del panel' })).toHaveCount(0);
  await page.goto('/#/recordatorios');
  await expect(page.getByRole('heading', { name: 'Agenda', level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Abrir WhatsApp' })).toHaveCount(0);
});
