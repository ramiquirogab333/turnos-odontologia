import { expect, test, type Page } from '@playwright/test';
import {
  accesoPorApi,
  API,
  diaDe,
  diaObjetivo,
  enMs,
  HORA,
  ingresar,
  inicioClinica,
  irAlDia,
  MINUTO,
  proximaMediaHora,
  verificarPantalla,
} from './ayudas';
import { contarPagos, EMAIL_ODONTOLOGA, leerEstadoPago, leerTurnos, sembrar, sembrarTurno, type Semilla } from './datos';

/** Alta manual y gestión del turno (ausente, atendido, cancelar) contra el backend real. */
let semilla: Semilla;

test.beforeEach(async () => {
  semilla = await sembrar();
});

async function abrirAlta(page: Page, dia: string): Promise<void> {
  await page.getByRole('button', { name: 'Nuevo turno' }).click();
  await expect(page.getByRole('dialog', { name: 'Nuevo turno' })).toBeVisible();
  await page.getByLabel('Tratamiento').selectOption({ label: 'Limpieza dental' });
  await page.locator('#alta-profesional').selectOption({ label: 'Dra. Ana Ficticia' });
  await page.getByLabel('Día', { exact: true }).fill(dia);
}

async function completarContacto(page: Page): Promise<void> {
  await page.getByLabel('Nombre completo').fill('Carlos Sintético');
  await page.getByLabel('Teléfono (WhatsApp)').fill('+54 9 11 4444-5555');
}

test('alta manual completa: elige horario libre, crea el turno y muestra el código de gestión una sola vez', async ({ page }) => {
  const dia = diaObjetivo();
  await ingresar(page);
  await abrirAlta(page, dia);
  await expect(page.getByRole('button', { name: '11:00', exact: true })).toBeVisible();
  await verificarPantalla(page, 'alta manual con horarios');
  await page.getByRole('button', { name: '11:00', exact: true }).click();
  await completarContacto(page);
  await page.getByRole('button', { name: 'Crear turno' }).click();

  await expect(page.getByRole('heading', { name: 'Turno creado' })).toBeVisible();
  const codigo = await page.locator('.codigo').innerText();
  expect(codigo.length).toBeGreaterThanOrEqual(8);
  await expect(page.getByText(/se muestra una sola vez/)).toBeVisible();
  await page.getByRole('button', { name: 'Listo' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  // El código no vuelve a verse en el panel.
  await irAlDia(page, dia);
  await expect(page.getByText('Carlos Sintético')).toBeVisible();
  await expect(page.getByText('Alta manual, sin seña')).toBeVisible();
  await expect(page.getByText(codigo)).toHaveCount(0);

  const turnos = await leerTurnos();
  expect(turnos).toHaveLength(1);
  expect(turnos[0]).toMatchObject({ estado: 'reservado', origen: 'manual', contacto_nombre: 'Carlos Sintético' });
  expect(await contarPagos()).toBe(0); // O7: sin seña
});

test('un horario tomado mientras se completa el formulario muestra alternativas y conserva los datos', async ({ page }) => {
  const dia = diaObjetivo();
  await ingresar(page);
  await abrirAlta(page, dia);
  await page.getByRole('button', { name: '11:00', exact: true }).click();
  await completarContacto(page);

  // Otra persona ocupa las 11:00 de la misma profesional antes de que recepción confirme.
  await sembrarTurno(semilla, { inicio: new Date(inicioClinica(dia, '11:00')), nombre: 'Lucía Ejemplo', sillon: 2 });
  await page.getByRole('button', { name: 'Crear turno' }).click();

  const aviso = page.getByRole('alert');
  await expect(aviso).toContainText('Ese horario ya no está disponible');
  await expect(page.getByLabel('Nombre completo')).toHaveValue('Carlos Sintético');
  await expect(page.getByLabel('Teléfono (WhatsApp)')).toHaveValue('+54 9 11 4444-5555');
  await aviso.getByRole('button', { name: '11:30', exact: true }).click();
  await page.getByRole('button', { name: 'Crear turno' }).click();
  await expect(page.getByRole('heading', { name: 'Turno creado' })).toBeVisible();

  const turnos = await leerTurnos();
  expect(turnos.map((t) => t.origen).sort()).toEqual(['manual', 'web']);
});

test('dos altas simultáneas sobre el mismo horario: exactamente un 201 y un 409, nunca 500 (cierra el pendiente de C-01)', async ({
  page,
  request,
}) => {
  await ingresar(page);
  const cuerpo = {
    profesional_id: semilla.profesionalId,
    tratamiento_id: semilla.limpiezaId,
    inicio: inicioClinica(diaObjetivo(), '14:00'),
    nombre: 'Carlos Sintético',
    telefono: '+5491144445555',
  };
  const cabecera = await accesoPorApi(request);
  const [a, b] = await Promise.all([
    request.post(`${API}/api/panel/turnos`, { headers: cabecera, data: cuerpo }),
    request.post(`${API}/api/panel/turnos`, { headers: cabecera, data: cuerpo }),
  ]);
  expect([a.status(), b.status()].sort()).toEqual([201, 409]);
  const perdedor = a.status() === 409 ? a : b;
  const motivo = ((await perdedor.json()) as { motivo: string }).motivo;
  expect(['profesional', 'sillon']).toContain(motivo);
  expect(await leerTurnos()).toHaveLength(1);
});

test('ausente con seña acreditada: el diálogo avisa que no se devuelve y la seña queda retenida', async ({ page }) => {
  const inicio = enMs(-15 * MINUTO);
  const id = await sembrarTurno(semilla, { inicio, estado: 'confirmado', sena: 'acreditado' });
  await ingresar(page);
  await irAlDia(page, diaDe(inicio));

  await page.getByRole('button', { name: 'Marcar ausente' }).click();
  const dialogo = page.getByRole('dialog', { name: '¿Marcar a Carlos Sintético como ausente?' });
  await expect(dialogo).toContainText('4.500,00');
  await expect(dialogo).toContainText('no se devuelve');
  await expect(dialogo).toContainText('no se puede deshacer');
  expect(await leerEstadoPago(id)).toBe('acreditado'); // nada cambia hasta confirmar
  await dialogo.getByRole('button', { name: 'Sí, marcar ausente' }).click();

  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('Seña retenida')).toBeVisible();
  expect((await leerTurnos())[0]?.estado).toBe('ausente');
  expect(await leerEstadoPago(id)).toBe('no_reembolsado'); // R9
});

test('ausente antes de cumplirse la tolerancia: la pantalla no ofrece la acción y el servidor la rechaza', async ({ page, request }) => {
  const inicio = enMs(-5 * MINUTO); // tolerancia de 10 minutos: faltan ~5, con margen de sobra
  const id = await sembrarTurno(semilla, { inicio, sena: 'acreditado' });
  await ingresar(page);
  await irAlDia(page, diaDe(inicio));

  await expect(page.getByText('Carlos Sintético')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Marcar ausente' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Marcar atendido' })).toBeVisible();

  const r = await request.post(`${API}/api/panel/turnos/${String(id)}/ausente`, { headers: await accesoPorApi(request) });
  expect(r.status()).toBe(409);
  expect(((await r.json()) as { motivo: string }).motivo).toBe('marcado_no_habilitado');
  expect(await leerEstadoPago(id)).toBe('acreditado');
});

test('atendido el mismo día antes de la hora: se acepta, la seña no cambia y el horario sigue ocupado en la reserva pública', async ({
  page,
  request,
}) => {
  const inicio = proximaMediaHora(enMs(2 * MINUTO));
  test.skip(diaDe(inicio) !== diaDe(new Date()), 'Muy cerca de la medianoche de la clínica: el turno cae en el día siguiente.');
  // La aserción final necesita otros horarios libres ese día: a partir de ~3 h antes de la medianoche de la clínica no
  // queda lugar para otro turno después de este y la disponibilidad del día vuelve vacía (falló así en la CI de C-09).
  test.skip(diaDe(new Date(inicio.getTime() + 3 * HORA)) !== diaDe(inicio), 'Sin lugar para otro turno ese día: muy cerca de la medianoche de la clínica.');
  const id = await sembrarTurno(semilla, { inicio, sena: 'acreditado' });
  await ingresar(page);

  await page.getByRole('button', { name: 'Marcar atendido' }).click();
  const dialogo = page.getByRole('dialog', { name: '¿Marcar a Carlos Sintético como atendido?' });
  await expect(dialogo).toContainText('sigue ocupado');
  await dialogo.getByRole('button', { name: 'Sí, marcar atendido' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await expect(page.getByText('Atendido', { exact: true })).toBeVisible();
  expect(await leerEstadoPago(id)).toBe('acreditado');
  const dia = diaDe(inicio);
  const disp = await request.get(`${API}/api/public/disponibilidad`, {
    params: { profesional_id: semilla.profesionalId, tratamiento_id: semilla.limpiezaId, desde: dia, hasta: dia },
  });
  const slots = ((await disp.json()) as { slots: { inicio: string }[] }).slots.map((s) => Date.parse(s.inicio));
  expect(slots.length, 'la semilla tiene franja todo el día: hay otros horarios libres').toBeGreaterThan(0);
  expect(slots, 'el horario del atendido no figura libre').not.toContain(inicio.getTime());
});

test('la odontóloga marca atendido su propio turno de hoy a 360px y no ve ninguna otra acción (C-11, O15)', async ({ page }, info) => {
  test.skip(info.project.name !== 'chromium-360', 'verificación específica del viewport de 360px');
  const inicio = enMs(-5 * MINUTO);
  test.skip(diaDe(inicio) !== diaDe(new Date()), 'Muy cerca de la medianoche de la clínica: el turno cae en otro día.');
  await sembrarTurno(semilla, { inicio, nombre: 'Carlos Sintético' });
  await sembrarTurno(semilla, { inicio, nombre: 'Lucía Ejemplo', profesional: 'bruno', sillon: 2 });
  await ingresar(page, EMAIL_ODONTOLOGA);

  await expect(page.getByText('Carlos Sintético')).toBeVisible();
  await expect(page.getByText('Lucía Ejemplo')).toHaveCount(0); // el turno de otra profesional no aparece
  await expect(page.getByRole('button', { name: 'Marcar atendido' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Marcar ausente' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Cancelar turno' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Nuevo turno' })).toHaveCount(0);
  await verificarPantalla(page, 'agenda de la odontóloga con el botón Marcar atendido');

  await page.getByRole('button', { name: 'Marcar atendido' }).click();
  const dialogo = page.getByRole('dialog', { name: '¿Marcar a Carlos Sintético como atendido?' });
  await verificarPantalla(page, 'diálogo de confirmación de la odontóloga');
  await dialogo.getByRole('button', { name: 'Sí, marcar atendido' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await expect(page.getByText('Atendido', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Marcar atendido' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^(Marcar ausente|Cancelar turno|Nuevo turno)/ })).toHaveCount(0);
  const turnos = await leerTurnos();
  expect(turnos.find((t) => t.contacto_nombre === 'Carlos Sintético')?.estado).toBe('atendido');
  expect(turnos.find((t) => t.contacto_nombre === 'Lucía Ejemplo')?.estado).toBe('reservado');
});

test('cancelar a 24 h + 5 min se acepta y devuelve la seña; a 23 h 55 min la pantalla no lo ofrece y el servidor lo rechaza', async ({
  page,
  request,
}) => {
  const margen = 5 * MINUTO;
  const dentro = enMs(24 * HORA + margen);
  const fuera = enMs(24 * HORA - margen);
  const idDentro = await sembrarTurno(semilla, { inicio: dentro, nombre: 'Carlos Sintético', sena: 'acreditado' });
  const idFuera = await sembrarTurno(semilla, { inicio: fuera, nombre: 'Lucía Ejemplo', sena: 'acreditado', profesional: 'bruno', sillon: 2 });
  await ingresar(page);

  await irAlDia(page, diaDe(fuera));
  const tarjetaFuera = page.getByRole('listitem').filter({ hasText: 'Lucía Ejemplo' });
  await expect(tarjetaFuera).toBeVisible();
  await expect(tarjetaFuera.getByRole('button', { name: 'Cancelar turno' })).toHaveCount(0);
  const rechazo = await request.post(`${API}/api/panel/turnos/${String(idFuera)}/cancelar`, { headers: await accesoPorApi(request) });
  expect(rechazo.status()).toBe(409);
  expect(((await rechazo.json()) as { motivo: string }).motivo).toBe('fuera_de_plazo');
  expect(await leerEstadoPago(idFuera)).toBe('acreditado');

  await irAlDia(page, diaDe(dentro), diaDe(fuera));
  const tarjeta = page.getByRole('listitem').filter({ hasText: 'Carlos Sintético' });
  await tarjeta.getByRole('button', { name: 'Cancelar turno' }).click();
  const dialogo = page.getByRole('dialog', { name: '¿Cancelar el turno de Carlos Sintético?' });
  await expect(dialogo).toContainText('a devolver');
  await dialogo.getByRole('button', { name: 'Sí, cancelar el turno' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('listitem').filter({ hasText: 'Carlos Sintético' })).toHaveCount(0); // los cancelados se ocultan
  expect(await leerEstadoPago(idDentro)).toBe('a_reembolsar');
});

// --- C-12: corrección de un atendido -----------------------------------------------------------------------------

test('recepción deshace un atendido de hoy: el turno vuelve a ofrecer «Marcar atendido» y «Marcar ausente»', async ({ page }) => {
  const inicio = enMs(-15 * MINUTO);
  const id = await sembrarTurno(semilla, { inicio, estado: 'atendido', sena: 'acreditado' });
  await ingresar(page);
  await irAlDia(page, diaDe(inicio));

  await expect(page.getByText('Atendido', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Marcar atendido' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Deshacer atendido' }).click();
  const dialogo = page.getByRole('dialog', { name: '¿Deshacer el atendido de Carlos Sintético?' });
  await expect(dialogo).toContainText('vuelve a reservado');
  await expect(dialogo).toContainText('puede perder el acceso a la ficha');
  await verificarPantalla(page, 'diálogo para deshacer un atendido');

  // Sin motivo no se envía nada.
  await dialogo.getByRole('button', { name: 'Sí, deshacer el atendido' }).click();
  await expect(dialogo.getByRole('alert')).toContainText('Elegí el motivo');
  expect((await leerTurnos()).find((t) => t.id === id)?.estado).toBe('atendido');

  await dialogo.getByLabel('Motivo').selectOption({ label: 'Marqué el turno equivocado' });
  await dialogo.getByRole('button', { name: 'Sí, deshacer el atendido' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await expect(page.getByText('Reservado', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Marcar atendido' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Marcar ausente' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Deshacer atendido' })).toHaveCount(0);
  expect((await leerTurnos()).find((t) => t.id === id)?.estado).toBe('reservado');
  expect(await leerEstadoPago(id)).toBe('acreditado'); // la seña no se toca
});

test('la odontóloga dueña del turno no ve «Deshacer atendido» y el servidor se lo rechaza', async ({ page, request }) => {
  const inicio = enMs(-15 * MINUTO);
  const id = await sembrarTurno(semilla, { inicio, estado: 'atendido', sena: 'acreditado' });
  await ingresar(page, EMAIL_ODONTOLOGA);
  await irAlDia(page, diaDe(inicio));

  await expect(page.getByText('Atendido', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Deshacer atendido' })).toHaveCount(0);

  const r = await request.post(`${API}/api/panel/turnos/${String(id)}/deshacer-atendido`, {
    headers: await accesoPorApi(request, EMAIL_ODONTOLOGA),
    data: { motivo: 'otro' },
  });
  expect(r.status()).toBe(403);
  expect((await leerTurnos()).find((t) => t.id === id)?.estado).toBe('atendido');
});
