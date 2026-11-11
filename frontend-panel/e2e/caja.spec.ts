import { expect, test } from '@playwright/test';
import { hoyClinica, sumarDias } from '../src/lib/tiempo';
import { accesoPorApi, API, diaDe, enMs, HORA, ingresar, instanteClinica, irAlDia, irASeccion, MINUTO, verificarPantalla } from './ayudas';
import {
  leerCierres,
  leerEstadoPago,
  sembrar,
  sembrarPaciente,
  sembrarPresupuestoAceptado,
  sembrarTurno,
  type Semilla,
} from './datos';

/** Caja, pendientes y cierre (C-12) contra el backend real, a 360 px y a 1280 px. Datos 100 % sintéticos (R19). */
let semilla: Semilla;

test.beforeEach(async () => {
  semilla = await sembrar();
});

test('un turno ausente con seña acreditada: la seña sigue en el total del día en que se cobró y figura como retenida', async ({ page }) => {
  const inicio = enMs(-15 * MINUTO);
  await sembrarTurno(semilla, { inicio, estado: 'confirmado', sena: 'acreditado' });
  await ingresar(page);
  await irAlDia(page, diaDe(inicio));

  await page.getByRole('button', { name: 'Marcar ausente' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Sí, marcar ausente' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('Seña retenida')).toBeVisible();

  await irASeccion(page, 'Caja');
  const resumen = page.getByRole('region', { name: 'Resumen de la caja' });
  await expect(resumen.getByText('Total del día: $ 4.500,00')).toBeVisible();
  await expect(resumen.getByText('Señas por Mercado Pago: $ 4.500,00 (1)')).toBeVisible();
  await expect(resumen.getByText('Señas retenidas por ausencia: $ 4.500,00 (1 seña)')).toBeVisible();
  await verificarPantalla(page, 'caja con una seña retenida');
});

test('cancelar un turno con 48 horas y registrar la devolución: el egreso se ve en la caja y la seña queda devuelta', async ({ page }) => {
  const inicio = enMs(48 * HORA);
  const id = await sembrarTurno(semilla, { inicio, sena: 'acreditado' });
  await ingresar(page);
  await irAlDia(page, diaDe(inicio));

  await page.getByRole('button', { name: 'Cancelar turno' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Sí, cancelar el turno' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await leerEstadoPago(id)).toBe('a_reembolsar');

  await irASeccion(page, 'Caja');
  const pendientes = page.getByRole('region', { name: 'Pagos por resolver' });
  await expect(pendientes.getByText(/Seña a devolver: \$ 4\.500,00/)).toBeVisible();
  await verificarPantalla(page, 'caja con un pago por resolver');

  await pendientes.getByRole('button', { name: 'Registrar devolución' }).click();
  const dialogo = page.getByRole('dialog', { name: '¿Registrar la devolución de $ 4.500,00?' });
  await expect(dialogo).toContainText('egreso de la caja de hoy');
  await verificarPantalla(page, 'diálogo de devolución');

  // Sin referencia no se envía nada.
  await dialogo.getByRole('button', { name: 'Sí, registrar la devolución' }).click();
  await expect(dialogo.getByRole('alert')).toContainText('Escribí la referencia de la devolución (el número de operación)');
  expect(await leerEstadoPago(id)).toBe('a_reembolsar');

  await dialogo.getByLabel('Referencia de la devolución').fill('DEV-SINT-0001');
  await dialogo.getByRole('button', { name: 'Sí, registrar la devolución' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await expect(page.getByText('No hay pagos por resolver')).toBeVisible();
  const resumen = page.getByRole('region', { name: 'Resumen de la caja' });
  await expect(resumen.getByText('Devoluciones de señas por Mercado Pago: $ 4.500,00 (1)')).toBeVisible();
  await expect(resumen.getByText(/Egresos \$ 4\.500,00/)).toBeVisible();
  await expect(resumen.getByText('Total del día: $ 0,00')).toBeVisible();
  expect(await leerEstadoPago(id)).toBe('reembolsado');
});

test('cerrar la caja de un día terminado muestra quién la cerró y que el cierre cuadra', async ({ page }) => {
  // Movimientos de anteayer: el día ya terminó sin importar a qué hora corre la suite.
  const anteayer = sumarDias(hoyClinica(new Date()), -2);
  await sembrarTurno(semilla, { inicio: enMs(5 * HORA), sena: 'acreditado', acreditadoEn: instanteClinica(anteayer, '15:00') });

  await ingresar(page);
  await irASeccion(page, 'Caja');
  await page.getByRole('button', { name: 'Día anterior' }).click();
  await page.getByRole('button', { name: 'Día anterior' }).click();
  await expect(page.getByText('Total del día: $ 4.500,00')).toBeVisible();
  await expect(page.getByText('Caja abierta')).toBeVisible();
  await verificarPantalla(page, 'caja de un día terminado');

  await page.getByRole('button', { name: 'Cerrar caja' }).click();
  const dialogo = page.getByRole('dialog', { name: /¿Cerrar la caja del .*\?/ });
  await expect(dialogo).toContainText('Total del día $ 4.500,00');
  await verificarPantalla(page, 'confirmación de cierre');
  await dialogo.getByRole('button', { name: 'Sí, cerrar la caja' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await expect(page.getByText('Caja cerrada')).toBeVisible();
  await expect(page.getByText(/Cerrada por Rita Recepción el /)).toBeVisible();
  await expect(page.getByText('El cierre cuadra')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cerrar caja' })).toHaveCount(0);
  // La recepcionista no puede anular el cierre: solo el administrador.
  await expect(page.getByRole('button', { name: 'Anular cierre' })).toHaveCount(0);
  await verificarPantalla(page, 'caja cerrada');
  expect(await leerCierres()).toEqual([{ dia: anteayer, estado: 'vigente' }]);
});

test('con el día cerrado, un cobro con fecha de ese día responde 409 caja_cerrada y no se registra', async ({ request }) => {
  const anteayer = sumarDias(hoyClinica(new Date()), -2);
  const paciente = await sembrarPaciente('Mateo', 'Prueba', '27888777');
  const presupuesto = await sembrarPresupuestoAceptado(paciente);
  const headers = await accesoPorApi(request);

  const cierre = await request.post(`${API}/api/panel/caja/cierres`, { headers, data: { dia: anteayer } });
  expect(cierre.status()).toBe(201);

  const cobro = await request.post(`${API}/api/panel/pacientes/${String(paciente)}/presupuestos/${String(presupuesto)}/pagos`, {
    headers,
    data: { medio: 'transferencia', monto: '1500.00', fecha_cobro: `${anteayer}T16:00:00-03:00` },
  });
  expect(cobro.status()).toBe(409);
  const cuerpo = (await cobro.json()) as { motivo: string; dia: string };
  expect(cuerpo.motivo).toBe('caja_cerrada');
  expect(cuerpo.dia).toBe(anteayer);

  // Un cobro de hoy (día abierto) sí se acepta: el bloqueo es por la fecha del movimiento.
  const hoy = await request.post(`${API}/api/panel/pacientes/${String(paciente)}/presupuestos/${String(presupuesto)}/pagos`, {
    headers,
    data: { medio: 'transferencia', monto: '1500.00', fecha_cobro: new Date().toISOString() },
  });
  expect(hoy.status()).toBe(201);
});
