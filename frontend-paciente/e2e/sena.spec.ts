import { expect, test, type Page } from '@playwright/test';
import {
  API,
  NOMBRE,
  abrirPaciente,
  acreditarTransferencia,
  diaObjetivo,
  enviarWebhook,
  firmarWebhook,
  inicioClinica,
  reservarHastaLaSena,
  reservarPorApi,
  verificarPantalla,
  verificarSinScrollHorizontal,
} from './ayudas';
import {
  ALIAS_TRANSFERENCIA,
  CBU_TRANSFERENCIA,
  leerPagos,
  leerTurnos,
  sembrar,
  vaciarTurnos,
  vencerPreReserva,
  type Semilla,
} from './datos';

/**
 * E2E del flujo de seña (C-06; R7, R8) a 360px contra el backend REAL de Docker Compose con
 * MP_GATEWAY=fake (sin red a Mercado Pago). El webhook se firma con el secreto SINTÉTICO del entorno.
 * Requiere SENA_BARRIDO_SEGUNDOS <= 5 en el backend para el caso de vencimiento (ver README).
 */
let semilla: Semilla;

test.beforeAll(async () => {
  const salud = await fetch(`${API}/api/health`);
  expect(salud.ok, 'el backend debe estar arriba (docker compose up -d postgres backend)').toBe(true);
  semilla = await sembrar();
});

test.beforeEach(async ({ page }) => {
  await vaciarTurnos();
  await page.goto('/');
});

/** El paciente elige Mercado Pago: el backend (pasarela falsa) lo devuelve a la app con `?pago=retorno`. */
async function pagarConMercadoPago(page: Page): Promise<void> {
  await Promise.all([
    page.waitForURL(/\?pago=retorno&turno=\d+/),
    page.getByRole('button', { name: 'Pagar con Mercado Pago' }).click(),
  ]);
  await expect(page.getByRole('status')).toContainText('Esperando la acreditación');
}

test.describe('(a) happy path con Mercado Pago', () => {
  test('Carlos Sintético reserva, paga, vuelve, llega el webhook firmado y ve "Turno reservado"', async ({ page, request }) => {
    const dia = diaObjetivo();
    await reservarHastaLaSena(page, dia, '10:00');
    await verificarPantalla(page, 'pantalla de seña');
    await pagarConMercadoPago(page);
    await verificarPantalla(page, 'espera de acreditación');

    const [pago] = await leerPagos();
    expect(pago).toMatchObject({ medio: 'mercadopago', estado: 'pendiente', monto: '4500.00' });
    expect((await leerTurnos())[0]?.estado).toBe('en_espera'); // R8: todavía no bloquea agenda

    const r = await enviarWebhook(request, pago?.referencia_externa ?? '', pago?.monto ?? '0');
    expect(r.status()).toBe(200);

    await expect(page.getByRole('heading', { name: 'Turno reservado' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/10:00 a 10:30/)).toBeVisible();
    await expect(page.getByText((await leerTurnos())[0]?.codigo_gestion ?? 'x')).toBeVisible();
    await verificarPantalla(page, 'turno reservado');

    expect((await leerTurnos())[0]?.estado).toBe('reservado');
    expect((await leerPagos())[0]?.estado).toBe('acreditado');
  });
});

test.describe('(b) transferencia', () => {
  test('muestra alias, CBU y código; recepción la acredita por la API y la pantalla pasa a "Turno reservado"', async ({ page, request }) => {
    const dia = diaObjetivo();
    await reservarHastaLaSena(page, dia, '10:00');
    await page.getByRole('button', { name: 'Pagar por transferencia' }).click();

    const datos = page.getByRole('region', { name: 'Datos para transferir' });
    await expect(datos.getByText(ALIAS_TRANSFERENCIA)).toBeVisible();
    await expect(datos.getByText(CBU_TRANSFERENCIA)).toBeVisible();
    const [pago] = await leerPagos();
    expect(pago?.medio).toBe('transferencia');
    expect(pago?.referencia_externa).toMatch(/^SENA-\d+-[0-9A-F]{6}$/);
    await expect(datos.getByText(pago?.referencia_externa ?? 'x')).toBeVisible();
    await expect(datos.getByRole('button', { name: /^Copiar/ })).toHaveCount(4);
    await expect(page.getByText('La clínica confirma tu turno al acreditar la transferencia.')).toBeVisible();
    await verificarPantalla(page, 'datos de transferencia');

    const r = await acreditarTransferencia(request, pago?.id ?? 0);
    expect(r.status()).toBe(200);

    await expect(page.getByRole('heading', { name: 'Turno reservado' })).toBeVisible({ timeout: 15_000 });
    expect((await leerTurnos())[0]?.estado).toBe('reservado');
    expect((await leerPagos())[0]?.estado).toBe('acreditado');
  });
});

test.describe('(c) vencimiento', () => {
  test('al vencer la pre-reserva la pantalla avisa, el barrido la cancela y el horario sigue libre', async ({ page }) => {
    const dia = diaObjetivo();
    await reservarHastaLaSena(page, dia, '10:00');
    await pagarConMercadoPago(page);
    const [turno] = await leerTurnos();
    await vencerPreReserva(turno?.id ?? 0);

    await expect(page.getByRole('heading', { name: 'La reserva venció' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('heading', { name: 'Turno reservado' })).toHaveCount(0);
    await verificarPantalla(page, 'reserva vencida');

    // El barrido del backend (cada SENA_BARRIDO_SEGUNDOS) la pasa a cancelado y su pago a vencido.
    await expect.poll(async () => (await leerTurnos())[0]?.estado, { timeout: 30_000 }).toBe('cancelado');
    expect((await leerPagos())[0]?.estado).toBe('vencido');

    // El horario vuelve a estar libre: el paciente puede elegirlo de nuevo.
    await page.getByRole('button', { name: 'Elegir otro horario' }).click();
    await expect(page.getByRole('radio', { name: /limpieza dental/i })).toBeVisible();
    const consulta = await fetch(
      `${API}/api/public/disponibilidad?profesional_id=${String(semilla.profesionalId)}&tratamiento_id=${String(semilla.limpiezaId)}&desde=${dia}&hasta=${dia}`,
    );
    const { slots } = (await consulta.json()) as { slots: { inicio: string }[] };
    expect(slots.map((s) => new Date(s.inicio).toISOString())).toContain(new Date(inicioClinica(dia, '10:00')).toISOString());
  });
});

test.describe('(d) competencia por el mismo horario', () => {
  test('dos pacientes llegan a la seña; se acredita el primero y el segundo ve el mensaje de devolución', async ({ browser, request }) => {
    const dia = diaObjetivo();
    const [uno, dos]: Page[] = [await abrirPaciente(browser), await abrirPaciente(browser)];
    if (!uno || !dos) throw new Error('No se pudieron abrir las dos páginas');
    try {
      await reservarHastaLaSena(uno, dia, '14:00', 'Paciente Uno');
      await reservarHastaLaSena(dos, dia, '14:00', 'Paciente Dos'); // ambos ven la pantalla de seña (R8)
      await pagarConMercadoPago(uno);
      await pagarConMercadoPago(dos);

      const pagos = await leerPagos();
      expect(pagos).toHaveLength(2);
      const [primero, segundo] = pagos;
      expect((await enviarWebhook(request, primero?.referencia_externa ?? '', primero?.monto ?? '0')).status()).toBe(200);
      expect((await enviarWebhook(request, segundo?.referencia_externa ?? '', segundo?.monto ?? '0')).status()).toBe(200);

      await expect(uno.getByRole('heading', { name: 'Turno reservado' })).toBeVisible({ timeout: 15_000 });
      await expect(dos.getByRole('heading', { name: 'El horario se ocupó' })).toBeVisible({ timeout: 15_000 });
      await expect(dos.getByText('La clínica se va a comunicar para devolverte la seña.')).toBeVisible();
      await verificarSinScrollHorizontal(dos, 'mensaje de devolución');

      const turnos = await leerTurnos();
      expect(turnos.filter((t) => t.estado === 'reservado' || t.estado === 'confirmado')).toHaveLength(1);
      expect(turnos.filter((t) => t.estado === 'cancelado')).toHaveLength(1);
      expect((await leerPagos()).map((p) => p.estado).sort()).toEqual(['a_reembolsar', 'acreditado']);
    } finally {
      await Promise.all([uno.context().close(), dos.context().close()]);
    }
  });
});

test.describe('(e) webhook con firma inválida', () => {
  test('responde 401 y la pantalla sigue esperando', async ({ page, request }) => {
    const dia = diaObjetivo();
    await reservarHastaLaSena(page, dia, '10:00');
    await pagarConMercadoPago(page);
    const [pago] = await leerPagos();
    const dataId = `fake-approved-${pago?.referencia_externa ?? ''}@${pago?.monto ?? '0'}@ARS`;

    const conOtroSecreto = await enviarWebhook(request, pago?.referencia_externa ?? '', pago?.monto ?? '0', { secreto: 'otro-secreto-sintetico' });
    expect(conOtroSecreto.status()).toBe(401);
    const sinFirma = await request.post(`${API}/api/webhooks/mercadopago`, {
      params: { 'data.id': dataId, type: 'payment' },
      data: { type: 'payment', data: { id: dataId } },
    });
    expect(sinFirma.status()).toBe(401);
    const vencida = await request.post(`${API}/api/webhooks/mercadopago`, {
      params: { 'data.id': dataId, type: 'payment' },
      headers: firmarWebhook(dataId, { tsMs: Date.now() - 3_600_000 }),
      data: { type: 'payment', data: { id: dataId } },
    });
    expect(vencida.status()).toBe(401);

    await page.waitForTimeout(4_000); // dos sondeos más: nada cambió
    await expect(page.getByRole('status')).toContainText('Esperando la acreditación');
    await expect(page.getByRole('heading', { name: 'Turno reservado' })).toHaveCount(0);
    expect((await leerTurnos())[0]?.estado).toBe('en_espera');
    expect((await leerPagos())[0]?.estado).toBe('pendiente');
  });
});

test.describe('(f) layout a 360px', () => {
  test('sin scroll horizontal en la pantalla de seña, en la espera y con los datos de transferencia', async ({ page }) => {
    const dia = diaObjetivo();
    await reservarHastaLaSena(page, dia, '10:30', NOMBRE);
    await verificarPantalla(page, 'pantalla de seña');
    await page.getByRole('button', { name: 'Pagar por transferencia' }).click();
    await expect(page.getByRole('region', { name: 'Datos para transferir' })).toBeVisible();
    await verificarPantalla(page, 'transferencia y espera');
  });

  test('una reserva por la API que otro paciente deja en espera no cambia el formato de la pantalla', async ({ page }) => {
    const dia = diaObjetivo();
    const { status } = await reservarPorApi(semilla, inicioClinica(dia, '15:00'), 'María Sintética');
    expect(status).toBe(201);
    await reservarHastaLaSena(page, dia, '15:00');
    await verificarSinScrollHorizontal(page, 'seña con otra pre-reserva en el mismo horario');
  });
});
