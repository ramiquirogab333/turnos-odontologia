import { expect, test } from '@playwright/test';
import { accesoPorApi, API, ingresar, verificarPantalla } from './ayudas';
import {
  asignarObraSocial,
  EMAIL_ODONTOLOGA,
  EMAIL_RECEPCION,
  leerPagosPresupuesto,
  leerPresupuestos,
  sembrar,
  sembrarAtendido,
  sembrarObraSocial,
  sembrarPaciente,
  type Semilla,
} from './datos';

/** Presupuestos y cobros del panel (C-16, R7) contra el backend real. Datos 100 % sintéticos (R19). */
let semilla: Semilla;
let lucia: number;

test.beforeEach(async () => {
  semilla = await sembrar();
  lucia = await sembrarPaciente('Lucía', 'Ejemplo', '99000001');
  // «Limpieza dental» de la semilla vale $ 15.000: con Swiss Medical sintético al 90 % quedan $ 1.500 a cargo del paciente.
  const swiss = await sembrarObraSocial(semilla, 'Swiss Medical', 'SWISS', '90.00');
  await asignarObraSocial(lucia, swiss);
});

test('recepción arma el borrador, lo presenta, lo acepta, cobra parcial y anula el cobro; el servidor es quien calcula', async ({ page, request }) => {
  await ingresar(page, EMAIL_RECEPCION);
  await page.goto(`/#/pacientes/${String(lucia)}?pestana=presupuestos`);
  await expect(page.getByText('Este paciente todavía no tiene presupuestos')).toBeVisible();
  await verificarPantalla(page, 'sin presupuestos');

  await page.getByRole('button', { name: 'Nuevo presupuesto' }).click();
  await page.getByRole('button', { name: 'Agregar línea' }).click();
  await page.getByLabel('Tratamiento').selectOption({ label: 'Limpieza dental' });
  await expect(page.getByText('Guardá el borrador para ver los importes')).toBeVisible();
  await verificarPantalla(page, 'formulario de presupuesto');
  await page.getByRole('button', { name: 'Guardar borrador' }).click();
  await expect(page.getByText('Borrador guardado')).toBeVisible();
  // Importes tal como los devolvió el servidor: bruto, cobertura del 90 % y a cargo del paciente.
  await expect(page.getByText('$ 15.000', { exact: true })).toBeVisible();
  await expect(page.getByText('$ 13.500', { exact: true })).toBeVisible();
  await expect(page.getByText('A cargo del paciente $ 1.500')).toBeVisible();
  await verificarPantalla(page, 'borrador guardado');
  await page.getByRole('button', { name: 'Cerrar' }).click();

  const [borrador] = await leerPresupuestos(lucia);
  expect(borrador?.estado).toBe('borrador');
  expect(borrador?.total_paciente).toBe('1500.00');

  await page.getByRole('button', { name: 'Presentar', exact: true }).click();
  await expect(page.getByText('Los importes quedan fijos desde ahora')).toBeVisible();
  await verificarPantalla(page, 'confirmar presentación');
  await page.getByRole('button', { name: 'Sí, presentar' }).click();
  await expect(page.getByText('Presentado', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Aceptar', exact: true }).click();
  await page.getByRole('button', { name: 'Sí, aceptar' }).click();
  await expect(page.getByText('Aceptado', { exact: true })).toBeVisible();
  await expect(page.getByText('Pagado $ 0 · Saldo $ 1.500')).toBeVisible();
  await verificarPantalla(page, 'presupuesto aceptado');

  await page.getByLabel('Monto').fill('1000');
  await page.getByLabel('Referencia (opcional)').fill('TRF-E2E-0001');
  await page.getByRole('button', { name: 'Registrar cobro', exact: true }).click();
  await expect(page.getByText('Pagado $ 1.000 · Saldo $ 500')).toBeVisible();
  expect((await leerPagosPresupuesto(borrador?.id ?? 0)).map((p) => [p.estado, p.monto, p.referencia])).toEqual([['registrado', '1000.00', 'TRF-E2E-0001']]);
  await verificarPantalla(page, 'cobro registrado');

  // Otra persona cobra $ 400 mientras esta pantalla sigue mostrando el saldo viejo: el servidor corrige con su saldo.
  const cabecera = await accesoPorApi(request, EMAIL_RECEPCION);
  const otro = await request.post(`${API}/api/panel/pacientes/${String(lucia)}/presupuestos/${String(borrador?.id)}/pagos`, {
    headers: cabecera,
    data: { medio: 'transferencia', monto: '400.00' },
  });
  expect(otro.status()).toBe(201);
  await page.getByLabel('Monto').fill('500');
  await page.getByRole('button', { name: 'Registrar cobro', exact: true }).click();
  await expect(page.getByText('El monto supera el saldo. El saldo actual es $ 100')).toBeVisible();
  await expect(page.getByLabel('Monto')).toHaveValue('100.00');
  await verificarPantalla(page, 'monto mayor que el saldo');
  expect(await leerPagosPresupuesto(borrador?.id ?? 0)).toHaveLength(2);

  await page.getByRole('button', { name: 'Anular cobro' }).first().click();
  await page.getByLabel('Motivo').fill('Monto equivocado (sintético)');
  await verificarPantalla(page, 'anular cobro');
  await page.getByRole('dialog').getByRole('button', { name: 'Anular cobro' }).click();
  await expect(page.getByText('Anulado · Monto equivocado (sintético)')).toBeVisible();
  await expect(page.getByText('Pagado $ 400 · Saldo $ 1.100')).toBeVisible();
  const pagos = await leerPagosPresupuesto(borrador?.id ?? 0);
  expect(pagos.map((p) => p.estado)).toEqual(['anulado', 'registrado']);
  expect(pagos[0]?.anulado_motivo).toBe('Monto equivocado (sintético)');
});

test('la odontóloga ve el presupuesto con sus líneas e importes pero sin pagos, saldo ni acciones', async ({ page, request }) => {
  await sembrarAtendido(semilla, lucia, 30);
  const cabecera = await accesoPorApi(request, EMAIL_RECEPCION);
  const base = `${API}/api/panel/pacientes/${String(lucia)}/presupuestos`;
  const creado = await request.post(base, { headers: cabecera, data: { lineas: [{ tratamiento_id: semilla.limpiezaId, cantidad: 1 }], notas: '' } });
  expect(creado.status()).toBe(201);
  const { id } = (await creado.json()) as { id: number };
  for (const accion of ['presentar', 'aceptar']) {
    expect((await request.post(`${base}/${String(id)}/${accion}`, { headers: cabecera })).status()).toBe(200);
  }
  expect((await request.post(`${base}/${String(id)}/pagos`, { headers: cabecera, data: { medio: 'transferencia', monto: '500.00' } })).status()).toBe(201);

  await ingresar(page, EMAIL_ODONTOLOGA);
  await page.goto(`/#/pacientes/${String(lucia)}?pestana=presupuestos`);
  await expect(page.getByText('A cargo del paciente $ 1.500')).toBeVisible();
  await expect(page.getByText('Limpieza dental').first()).toBeVisible();
  await expect(page.getByText(/Pagado|Saldo/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Registrar cobro|Anular|Presentar|Aceptar|Editar|Nuevo presupuesto/ })).toHaveCount(0);
  await verificarPantalla(page, 'presupuesto de la odontóloga');
});
