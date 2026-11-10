import { expect, test, type Page } from '@playwright/test';
import { etiquetaDiaLarga } from '../src/lib/tiempo';
import {
  API,
  HORA,
  MINUTO,
  abrirGestion,
  codigoSintetico,
  diaObjetivo,
  enMs,
  enviarWebhook,
  inicioClinica,
  reservarHastaLaSena,
  verificarPantalla,
} from './ayudas';
import { leerPagos, leerTurnos, sembrar, sembrarTurnoGestion, sembrarTurnoReservado, vaciarTurnos, type Semilla } from './datos';

/**
 * E2E de la gestión del turno por el paciente (C-07; R7, R3, R8, R9) a 360px contra el backend REAL.
 * El reloj del servidor no se puede inyectar desde el navegador (decisión O9): el borde exacto de 24 h se prueba en
 * integración y acá se siembran turnos a cada lado del borde con margen de minutos.
 */
let semilla: Semilla;

test.beforeAll(async () => {
  const salud = await fetch(`${API}/api/health`);
  expect(salud.ok, 'el backend debe estar arriba (docker compose up -d postgres backend)').toBe(true);
  semilla = await sembrar();
});

test.beforeEach(async () => {
  await vaciarTurnos();
});

async function estadoDe(id: number): Promise<string | undefined> {
  return (await leerTurnos()).find((t) => t.id === id)?.estado;
}

test.describe('(a) borde aceptado: 24 h + 5 min', () => {
  test('cancela, la seña queda a reembolsar y el horario vuelve a estar libre', async ({ page }) => {
    const inicio = enMs(24 * HORA + 5 * MINUTO);
    const t = await sembrarTurnoGestion(semilla, { inicio, estado: 'reservado', codigo: codigoSintetico('a') });
    await abrirGestion(page, t.codigo);

    await expect(page.getByRole('heading', { name: 'Gestionar mi turno' })).toBeVisible();
    await expect(page.getByText(/Limpieza dental con Dra\. Sintética/)).toBeVisible();
    await expect(page.getByText(/Podés cancelar o cambiar el horario hasta el/)).toBeVisible();
    expect(new URL(page.url()).hash, 'el código sale de la URL').toBe('');
    await verificarPantalla(page, 'gestión (borde aceptado)');

    await page.getByRole('button', { name: 'Cancelar turno' }).click();
    const dialogo = page.getByRole('alertdialog');
    await expect(dialogo.getByText(/La clínica te va a devolver la seña de \$\s?4\.500,00/)).toBeVisible();
    await verificarPantalla(page, 'confirmar cancelación');
    await dialogo.getByRole('button', { name: 'Sí, cancelar el turno' }).click();

    await expect(page.getByRole('heading', { name: 'Turno cancelado' })).toBeVisible();
    await verificarPantalla(page, 'turno cancelado');
    expect(await estadoDe(t.id)).toBe('cancelado');
    expect((await leerPagos())[0]?.estado).toBe('a_reembolsar'); // RN-SN-04
    // El horario volvió a estar libre: la base (EXCLUDE, R5) acepta otro turno bloqueante en el mismo instante.
    await sembrarTurnoReservado(semilla, inicio.toISOString());
  });
});

test.describe('(b) borde rechazado: 23 h 55 min', () => {
  test('avisa que ya no se puede, sin acciones, y un POST directo recibe 409 sin cambios', async ({ page, request }) => {
    const t = await sembrarTurnoGestion(semilla, {
      inicio: enMs(23 * HORA + 55 * MINUTO), estado: 'reservado', codigo: codigoSintetico('b'),
    });
    await abrirGestion(page, t.codigo);

    await expect(page.getByText(/Ya no podés cancelar ni cambiar el turno online/)).toBeVisible();
    await expect(page.getByText(/Comunicate con la clínica/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancelar turno' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Cambiar horario' })).toHaveCount(0);
    await verificarPantalla(page, 'gestión (fuera de plazo)');

    const r = await request.post(`${API}/api/public/gestion/cancelar`, { headers: { 'X-Codigo-Gestion': t.codigo } });
    expect(r.status()).toBe(409);
    expect(((await r.json()) as { motivo: string }).motivo).toBe('fuera_de_plazo');
    expect(await estadoDe(t.id)).toBe('reservado');
    expect((await leerPagos())[0]?.estado).toBe('acreditado');
  });
});

test.describe('(c) pre-reserva en espera', () => {
  test('se cancela sin ventana ni caja: "No se te cobra nada", pago vencido y nada a reembolsar', async ({ page }) => {
    const t = await sembrarTurnoGestion(semilla, {
      inicio: enMs(3 * HORA), estado: 'en_espera', codigo: codigoSintetico('c'),
    });
    await abrirGestion(page, t.codigo);

    await expect(page.getByRole('button', { name: 'Cambiar horario' })).toHaveCount(0);
    await expect(page.getByText(/Cancelalo y reservá otro horario/)).toBeVisible();
    await page.getByRole('button', { name: 'Cancelar turno' }).click();
    await expect(page.getByRole('alertdialog').getByText('No se te cobra nada.')).toBeVisible();
    await page.getByRole('button', { name: 'Sí, cancelar el turno' }).click();

    await expect(page.getByRole('heading', { name: 'Turno cancelado' })).toBeVisible();
    await verificarPantalla(page, 'pre-reserva cancelada');
    expect(await estadoDe(t.id)).toBe('cancelado');
    const pagos = await leerPagos();
    expect(pagos.map((p) => p.estado)).toEqual(['vencido']); // R8: ningún a_reembolsar
  });
});

async function elegirNuevoHorario(page: Page, dia: string, hhmm: string): Promise<void> {
  await page.getByRole('button', { name: 'Cambiar horario' }).click();
  await page.getByRole('button', { name: etiquetaDiaLarga(dia), exact: true }).click();
  await page.getByRole('button', { name: hhmm, exact: true }).click();
  await verificarPantalla(page, 'elegir nuevo horario');
  await page.getByRole('button', { name: 'Continuar' }).click();
}

test.describe('(d) reprogramación feliz', () => {
  test('mueve el turno al nuevo horario conservando id y seña acreditada', async ({ page }) => {
    const dia = diaObjetivo();
    const t = await sembrarTurnoGestion(semilla, {
      inicio: new Date(inicioClinica(dia, '10:00')), estado: 'reservado', codigo: codigoSintetico('d'),
    });
    await abrirGestion(page, t.codigo);

    await elegirNuevoHorario(page, dia, '11:00');
    await expect(page.getByText(/Nuevo horario:/)).toBeVisible();
    await verificarPantalla(page, 'confirmar cambio');
    await page.getByRole('button', { name: 'Confirmar cambio' }).click();

    await expect(page.getByRole('heading', { name: 'Turno reprogramado' })).toBeVisible();
    await verificarPantalla(page, 'turno reprogramado');
    const [turno] = await leerTurnos();
    expect(turno?.id).toBe(t.id);
    expect(turno?.estado).toBe('reservado');
    expect(turno?.inicio.toISOString()).toBe(new Date(inicioClinica(dia, '11:00')).toISOString());
    expect(turno?.codigo_gestion).toBe(t.codigo);
    expect((await leerPagos()).map((p) => p.estado)).toEqual(['acreditado']);
  });
});

test.describe('(e) horario ocupado mientras elige', () => {
  test('avisa que el horario ya no está disponible, ofrece alternativas y elegir una funciona', async ({ page }) => {
    const dia = diaObjetivo();
    const t = await sembrarTurnoGestion(semilla, {
      inicio: new Date(inicioClinica(dia, '10:00')), estado: 'reservado', codigo: codigoSintetico('e'),
    });
    await abrirGestion(page, t.codigo);

    await elegirNuevoHorario(page, dia, '11:00');
    await sembrarTurnoReservado(semilla, inicioClinica(dia, '11:00')); // otra persona se lo queda
    await page.getByRole('button', { name: 'Confirmar cambio' }).click();

    const aviso = page.getByRole('alert');
    await expect(aviso.getByText(/Ese horario ya no está disponible/)).toBeVisible();
    await verificarPantalla(page, 'horario ocupado');
    await page.locator('.alternativas button').first().click();
    await page.getByRole('button', { name: 'Confirmar cambio' }).click();

    await expect(page.getByRole('heading', { name: 'Turno reprogramado' })).toBeVisible();
    const mio = (await leerTurnos()).find((x) => x.id === t.id);
    expect(mio?.estado).toBe('reservado');
    expect(mio?.inicio.toISOString()).not.toBe(new Date(inicioClinica(dia, '11:00')).toISOString());
    expect(mio?.inicio.getTime()).toBeGreaterThan(new Date(inicioClinica(dia, '11:00')).getTime());
    expect((await leerPagos()).map((p) => p.estado)).toEqual(['acreditado']);
  });
});

test.describe('(f) enlace desde la confirmación y layout', () => {
  test('"Gestionar mi turno" abre la pantalla con el turno recién reservado, a 360px', async ({ page, request }) => {
    await page.goto('/');
    const dia = diaObjetivo();
    await reservarHastaLaSena(page, dia, '10:00');
    await Promise.all([
      page.waitForURL(/\?pago=retorno&turno=\d+/),
      page.getByRole('button', { name: 'Pagar con Mercado Pago' }).click(),
    ]);
    const [pago] = await leerPagos();
    expect((await enviarWebhook(request, pago?.referencia_externa ?? '', pago?.monto ?? '0')).status()).toBe(200);

    await expect(page.getByRole('heading', { name: 'Turno reservado' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Podés cancelar o cambiar el horario hasta 24 h antes.')).toBeVisible();
    await verificarPantalla(page, 'confirmación con enlace');

    await page.getByRole('link', { name: 'Gestionar mi turno' }).click();
    await expect(page).toHaveURL(/\/gestionar/);
    await expect(page.getByRole('heading', { name: 'Gestionar mi turno' })).toBeVisible();
    await expect(page.getByText(/10:00 a 10:30/)).toBeVisible();
    await expect(page.getByText(/Seña: .*4\.500,00 \(acreditada\)/)).toBeVisible();
    await verificarPantalla(page, 'gestión desde la confirmación');
    await page.getByRole('button', { name: 'Cambiar horario' }).click();
    // La pantalla abre en el primer día con horarios (hoy, si queda alguno): se elige el día objetivo.
    await page.getByRole('button', { name: etiquetaDiaLarga(dia), exact: true }).click();
    await expect(page.getByRole('button', { name: '10:30', exact: true })).toBeVisible();
    await verificarPantalla(page, 'gestión: horarios');
  });

  test('sin código en la URL pide pegarlo y un código desconocido avisa', async ({ page }) => {
    await page.goto('/gestionar');
    await expect(page.getByLabel('Código de gestión')).toBeVisible();
    await verificarPantalla(page, 'pedir código');
    await page.getByLabel('Código de gestión').fill('CODIGO-INEXISTENTE-0000');
    await page.getByRole('button', { name: 'Ver mi turno' }).click();
    await expect(page.getByText(/No encontramos un turno con ese código/)).toBeVisible();
    await verificarPantalla(page, 'código desconocido');
  });
});
