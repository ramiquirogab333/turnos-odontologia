import { expect, test } from '@playwright/test';
import { API, diaObjetivo, elegirTratamiento, inicioClinica, verificarPantalla } from './ayudas';
import { CLAVE_RECEPCION, EMAIL_ODONTOLOGA, sembrar, sembrarOdontologa, vaciarTurnos } from './datos';
import { etiquetaDiaLarga } from '../src/lib/tiempo';

/**
 * Google Calendar (C-10; R7, R3) desde el lado del paciente, a 360 px: un horario ocupado en el Google Calendar de la
 * profesional no se ofrece en la reserva pública. Contra el backend REAL, el worker real (ciclo de 3 s) y el Google
 * FALSO del perfil e2e de Compose. Datos 100 % sintéticos (R19).
 */
const GCAL = process.env['E2E_GCAL_URL'] ?? 'http://localhost:8090';
const ESPERA = { timeout: 30_000 };

test.beforeAll(async () => {
  const salud = await fetch(`${API}/api/health`);
  expect(salud.ok, 'el backend debe estar arriba (docker compose up -d postgres redis gcal-falso backend worker)').toBe(true);
});

test('un horario ocupado en Google Calendar no se ofrece en la reserva y los contiguos sí', async ({ page, request }) => {
  const semilla = await sembrar();
  await sembrarOdontologa(semilla.profesionalId);
  await vaciarTurnos();
  expect((await request.post(`${GCAL}/_control/reiniciar`)).ok()).toBe(true);

  // La odontóloga conecta su calendario (consentimiento falso + callback) por la API.
  const login = await request.post(`${API}/api/auth/login`, { data: { email: EMAIL_ODONTOLOGA, password: CLAVE_RECEPCION } });
  expect(login.status()).toBe(200);
  const { access_token: token } = (await login.json()) as { access_token: string };
  const cabecera = { Authorization: `Bearer ${token}` };
  const iniciar = await request.post(`${API}/api/panel/google-calendar/conexion/iniciar`, { headers: cabecera });
  expect(iniciar.status(), 'iniciar la conexión (¿GCAL_* configuradas en el backend?)').toBe(200);
  const { url_autorizacion: url } = (await iniciar.json()) as { url_autorizacion: string };
  const consentimiento = await request.get(url, { maxRedirects: 0 });
  const callback = await request.get(consentimiento.headers()['location'] ?? '', { maxRedirects: 0 });
  expect(callback.headers()['location']).toContain('resultado=conectado');

  // La profesional ocupa 10:00-11:00 del día objetivo en su Google Calendar.
  const dia = diaObjetivo();
  const ocupado = await request.post(`${GCAL}/_control/ocupado`, {
    data: { inicio: inicioClinica(dia, '10:00'), fin: inicioClinica(dia, '11:00') },
  });
  expect(ocupado.ok()).toBe(true);

  // Tras un ciclo del worker, la API deja de ofrecer 10:00 y 10:30 (esperando con la API, no con la pantalla).
  await expect
    .poll(
      async () => {
        const r = await request.get(`${API}/api/public/disponibilidad`, {
          params: { profesional_id: semilla.profesionalId, tratamiento_id: semilla.limpiezaId, desde: dia, hasta: dia },
        });
        const horas = ((await r.json()) as { slots: { inicio: string }[] }).slots.map((s) => s.inicio.slice(11, 16));
        return horas.includes('10:00') || horas.includes('10:30');
      },
      ESPERA,
    )
    .toBe(false);

  await page.goto('/');
  await elegirTratamiento(page);
  await page.getByRole('button', { name: etiquetaDiaLarga(dia), exact: true }).click();
  await expect(page.getByRole('button', { name: '09:30', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '11:00', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '10:00', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '10:30', exact: true })).toHaveCount(0);
  await verificarPantalla(page, 'reserva con franja ocupada en Google');
});
