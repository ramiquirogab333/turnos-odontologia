import { expect, test } from '@playwright/test';
import {
  accesoPorApi,
  API,
  conectarGooglePorApi,
  controlGoogle,
  diaDe,
  enMs,
  eventosGoogle,
  HORA,
  ingresar,
  irAlDia,
  irASeccion,
  verificarPantalla,
} from './ayudas';
import { cambiarEstadoTurno, EMAIL_ODONTOLOGA, leerCodigoGestion, sembrar, sembrarTurno, type Semilla } from './datos';

/**
 * Google Calendar (C-10; R7, R3) contra el backend REAL, el WORKER real (GCAL_SYNC_INTERVALO_SEGUNDOS=3) y el Google
 * FALSO del perfil e2e de Compose (docker compose --profile e2e up -d postgres redis gcal-falso y luego backend worker,
 * con las GCAL_* del CI). A 360 px y a 1280 px. Datos 100 % sintéticos (R19).
 */
let semilla: Semilla;

test.beforeEach(async ({ request }) => {
  semilla = await sembrar();
  await controlGoogle(request, 'reiniciar');
});

/** El worker corre cada 3 s: se espera con margen. */
const ESPERA = { timeout: 30_000 };

async function esperarEventos(request: Parameters<typeof eventosGoogle>[0], cantidad: number): Promise<void> {
  await expect.poll(async () => (await eventosGoogle(request)).length, ESPERA).toBe(cantidad);
}

async function conflictosAbiertos(request: Parameters<typeof accesoPorApi>[0]): Promise<number> {
  const cabecera = await accesoPorApi(request);
  const r = await request.get(`${API}/api/panel/google-calendar/conflictos?estado=abierto`, { headers: cabecera });
  return ((await r.json()) as unknown[]).length;
}

test('13.1 la odontóloga conecta su Google Calendar: consentimiento falso y vuelta al panel conectada', async ({ page }) => {
  await ingresar(page, EMAIL_ODONTOLOGA);
  await irASeccion(page, 'Google Calendar');
  await expect(page.getByRole('button', { name: 'Conectar Google Calendar' })).toBeVisible();
  await verificarPantalla(page, 'google calendar sin conectar');

  await page.getByRole('button', { name: 'Conectar Google Calendar' }).click();
  // Google falso (localhost:8090) -> callback del backend -> vuelta al panel con el resultado.
  await expect(page.getByText('Conectado como profesional.prueba@example.com')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Google Calendar quedó conectado/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Desconectar' })).toBeVisible();
  await expect(page.getByText('No hay conflictos con Google Calendar')).toBeVisible();
  await verificarPantalla(page, 'google calendar conectada');
});

test('13.2 eventos por transición: pre-reserva sin evento, seña acreditada con evento sin datos del paciente, cancelación lo borra', async ({
  request,
}) => {
  await conectarGooglePorApi(request, EMAIL_ODONTOLOGA);
  const turno = await sembrarTurno(semilla, { inicio: enMs(30 * HORA), estado: 'en_espera', sena: 'pendiente' });
  await new Promise((resolver) => setTimeout(resolver, 8_000)); // más de dos ciclos del worker
  expect(await eventosGoogle(request)).toEqual([]); // una pre-reserva nunca tiene evento (R8)

  await cambiarEstadoTurno(turno, 'reservado'); // la seña se acredita
  await esperarEventos(request, 1);
  const [evento] = await eventosGoogle(request);
  expect(evento?.summary).toBe('Turno · Limpieza dental');
  const todo = JSON.stringify(evento);
  expect(todo).not.toContain('Carlos Sintético');
  expect(todo).not.toContain('+5491144445555');

  const codigo = await leerCodigoGestion(turno);
  const cancelar = await request.post(`${API}/api/public/gestion/cancelar`, { headers: { 'X-Codigo-Gestion': codigo } });
  expect(cancelar.status()).toBe(200);
  await esperarEventos(request, 0);
});

test('13.2 mover el evento en Google abre un conflicto visible y "Restaurar en Google" lo devuelve (sin desbordar)', async ({
  page,
  request,
}) => {
  await conectarGooglePorApi(request, EMAIL_ODONTOLOGA);
  const inicio = enMs(40 * HORA);
  await sembrarTurno(semilla, { inicio, estado: 'reservado', sena: 'acreditado' });
  await esperarEventos(request, 1);
  const [original] = await eventosGoogle(request);
  const movido = new Date(inicio.getTime() + 2 * HORA);
  await controlGoogle(request, 'mover', {
    id: original?.id,
    inicio: movido.toISOString(),
    fin: new Date(movido.getTime() + 30 * 60_000).toISOString(),
  });
  await expect.poll(() => conflictosAbiertos(request), ESPERA).toBe(1);

  await ingresar(page); // recepción
  await irAlDia(page, diaDe(inicio));
  const tarjeta = page.getByRole('listitem').filter({ hasText: 'Carlos Sintético' });
  await expect(tarjeta.getByText('Conflicto con Google Calendar')).toBeVisible();
  await verificarPantalla(page, 'agenda con conflicto');
  await tarjeta.getByRole('link', { name: 'Ver conflicto' }).click();

  await expect(page.getByRole('heading', { level: 1, name: 'Google Calendar' })).toBeVisible();
  const conflicto = page.getByRole('listitem').filter({ hasText: 'Sistema:' });
  await expect(conflicto.getByText(/Sistema: \d{2}:\d{2}–\d{2}:\d{2} \/ Google: \d{2}:\d{2}–\d{2}:\d{2}/)).toBeVisible();
  await verificarPantalla(page, 'conflictos de google calendar');

  await conflicto.getByRole('button', { name: 'Restaurar en Google' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Restaurar en Google' }).click();
  await expect(page.getByText('No hay conflictos con Google Calendar')).toBeVisible();

  // En el ciclo siguiente el evento vuelve al horario del turno.
  await expect
    .poll(async () => Date.parse((await eventosGoogle(request))[0]?.start.dateTime ?? ''), ESPERA)
    .toBe(Math.floor(inicio.getTime() / 60_000) * 60_000);
});
