import { expect, test } from '@playwright/test';
import { diaClinica, etiquetaDiaNumerica, horaClinica } from '../src/lib/tiempo';
import { API, HORA, codigoSintetico, enMs, verificarPantalla } from './ayudas';
import { leerTurnos, sembrar, sembrarTurnoGestion, vaciarTurnos, type Semilla } from './datos';

/**
 * E2E de la confirmación de asistencia (C-09; R7, R3, R8) a 360px contra el backend REAL: el paciente abre el enlace
 * `/confirmar#<código>` del mensaje de WhatsApp. Abrirlo nunca confirma; solo el botón.
 */
let semilla: Semilla;

test.beforeAll(async () => {
  const salud = await fetch(`${API}/api/health`);
  expect(salud.ok, 'el backend debe estar arriba (docker compose up -d postgres redis backend worker)').toBe(true);
  semilla = await sembrar();
});

test.beforeEach(async () => {
  await vaciarTurnos();
});

async function estadoDe(id: number): Promise<string | undefined> {
  return (await leerTurnos()).find((t) => t.id === id)?.estado;
}

test('abrir el enlace no confirma; tocar el botón sí, y se ve el mensaje de éxito', async ({ page }) => {
  const inicio = enMs(30 * HORA);
  const t = await sembrarTurnoGestion(semilla, { inicio, estado: 'reservado', codigo: codigoSintetico('conf1') });
  await page.goto(`/confirmar#${encodeURIComponent(t.codigo)}`);

  await expect(page.getByRole('heading', { name: 'Confirmar asistencia' })).toBeVisible();
  await expect(page.getByText(/Limpieza dental con Dra\. Sintética/)).toBeVisible();
  expect(new URL(page.url()).hash, 'el código sale de la URL').toBe('');
  await verificarPantalla(page, 'confirmar asistencia');

  // Abrir (y recargar) la pantalla no cambia el turno: solo el botón confirma.
  expect(await estadoDe(t.id)).toBe('reservado');
  await page.waitForTimeout(500);
  expect(await estadoDe(t.id)).toBe('reservado');

  await page.getByRole('button', { name: 'Confirmar asistencia' }).click();
  const dia = diaClinica(inicio.toISOString());
  await expect(
    page.getByRole('heading', {
      name: `¡Listo! Confirmaste tu turno del ${etiquetaDiaNumerica(dia)} a las ${horaClinica(inicio.toISOString())}`,
    }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirmar asistencia' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Gestionar mi turno' })).toBeVisible();
  await verificarPantalla(page, 'turno confirmado');
  expect(await estadoDe(t.id)).toBe('confirmado');
});

test('una pre-reserva en espera (sin seña acreditada) no ofrece confirmar y el turno no cambia (R8)', async ({ page, request }) => {
  const t = await sembrarTurnoGestion(semilla, {
    inicio: enMs(30 * HORA), estado: 'en_espera', codigo: codigoSintetico('conf2'),
  });
  await page.goto(`/confirmar#${encodeURIComponent(t.codigo)}`);

  await expect(page.getByRole('heading', { name: 'Este turno ya no se puede confirmar' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirmar asistencia' })).toHaveCount(0);
  await verificarPantalla(page, 'pre-reserva sin confirmar');

  const r = await request.post(`${API}/api/public/gestion/confirmar`, { headers: { 'X-Codigo-Gestion': t.codigo } });
  expect(r.status()).toBe(409);
  expect(((await r.json()) as { motivo: string }).motivo).toBe('sena_pendiente');
  expect(await estadoDe(t.id)).toBe('en_espera');
});

test('un código desconocido avisa que no se encontró el turno', async ({ page }) => {
  await page.goto('/confirmar#CODIGO-SINTETICO-INEXISTENTE');
  await expect(page.getByText(/No encontramos un turno con ese código/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirmar asistencia' })).toHaveCount(0);
  await verificarPantalla(page, 'código desconocido');
});
