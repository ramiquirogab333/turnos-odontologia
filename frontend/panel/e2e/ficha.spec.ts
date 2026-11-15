import { expect, test } from '@playwright/test';
import { accesoPorApi, API, diaDe, enMs, HORA, ingresar, irAlDia, verificarPantalla } from './ayudas';
import { EMAIL_ODONTOLOGA, EMAIL_RECEPCION, leerFicha, sembrar, sembrarAtendido, sembrarFicha, sembrarPaciente, sembrarTurno, type Semilla } from './datos';

/** Ficha clínica del panel (C-16, R7) contra el backend real. Datos 100 % sintéticos (R19). */
let semilla: Semilla;
let lucia: number;

test.beforeEach(async () => {
  semilla = await sembrar();
  lucia = await sembrarPaciente('Lucía', 'Ejemplo', '99000001');
  await sembrarFicha(lucia, { alergias: 'Penicilina (sintético)', medicacion: 'Ninguna (sintético)' }, 2);
});

test('la odontóloga abre «Ver ficha» desde su agenda, edita la medicación y la base queda en la versión siguiente', async ({ page }) => {
  const inicio = enMs(-3 * HORA);
  await sembrarTurno(semilla, { inicio, estado: 'atendido', nombre: 'Lucía Ejemplo', pacienteId: lucia });

  await ingresar(page, EMAIL_ODONTOLOGA);
  await irAlDia(page, diaDe(inicio)); // 3 h atrás puede ser el día anterior si corre justo después de la medianoche de la clínica
  await page.getByRole('link', { name: 'Ver ficha' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Lucía Ejemplo' })).toBeVisible();
  await expect(page.getByText('Penicilina (sintético)')).toBeVisible();
  // La vista clínica nunca trae el contacto (RN-CL-02).
  await expect(page.getByText('+5491144446666')).toHaveCount(0);
  await verificarPantalla(page, 'ficha en lectura');

  await page.getByRole('button', { name: 'Editar ficha' }).click();
  await page.getByLabel('Medicación').fill('Ibuprofeno 400 mg (sintético)');
  await expect(page.getByText('29/2000')).toBeVisible();
  await verificarPantalla(page, 'ficha en edición');
  await page.getByRole('button', { name: 'Guardar ficha' }).click();
  await expect(page.getByText('Ficha guardada')).toBeVisible();
  await expect(page.getByText('Ibuprofeno 400 mg (sintético)')).toBeVisible();

  const guardada = await leerFicha(lucia);
  expect(guardada?.version).toBe(3);
  expect(guardada?.medicacion).toBe('Ibuprofeno 400 mg (sintético)');
  await verificarPantalla(page, 'ficha guardada');
});

test('si recepción guarda antes (en otra pestaña), la odontóloga ve el 409 con «Lo que escribiste»', async ({ page, request }) => {
  const inicio = enMs(-3 * HORA);
  await sembrarTurno(semilla, { inicio, estado: 'atendido', nombre: 'Lucía Ejemplo', pacienteId: lucia });

  await ingresar(page, EMAIL_ODONTOLOGA);
  await irAlDia(page, diaDe(inicio)); // 3 h atrás puede ser el día anterior si corre justo después de la medianoche de la clínica
  await page.getByRole('link', { name: 'Ver ficha' }).click();
  await page.getByRole('button', { name: 'Editar ficha' }).click();
  await page.getByLabel('Observaciones').fill('Nota de la odontóloga (sintético)');

  // Recepción guarda con la misma versión que leyó la odontóloga (2) desde otra sesión.
  const cabecera = await accesoPorApi(request, EMAIL_RECEPCION);
  const r = await request.put(`${API}/api/panel/pacientes/${String(lucia)}/ficha`, {
    headers: cabecera,
    data: { alergias: 'Penicilina (sintético)', medicacion: 'Paracetamol (sintético)', antecedentes_medicos: '', observaciones: '', version: 2 },
  });
  expect(r.status()).toBe(200);

  await page.getByRole('button', { name: 'Guardar ficha' }).click();
  await expect(page.getByText('Alguien guardó la ficha mientras la editabas')).toBeVisible();
  await expect(page.getByText('Paracetamol (sintético)')).toBeVisible();
  const propio = page.getByRole('region', { name: 'Lo que escribiste' });
  await expect(propio.getByText('Nota de la odontóloga (sintético)')).toBeVisible();
  await verificarPantalla(page, 'ficha con conflicto de versión');

  const guardada = await leerFicha(lucia);
  expect(guardada?.version).toBe(3);
  expect(guardada?.medicacion).toBe('Paracetamol (sintético)');
  expect(guardada?.observaciones).toBe('');
});

test('con una atención de hace 400 días y sin turno pendiente la ficha y el odontograma son de solo lectura', async ({ page }) => {
  await sembrarAtendido(semilla, lucia, 400);

  await ingresar(page, EMAIL_ODONTOLOGA);
  await page.goto(`/#/pacientes/${String(lucia)}`);
  await expect(page.getByRole('heading', { level: 2, name: 'Lucía Ejemplo' })).toBeVisible();
  await expect(page.getByText('Solo lectura: tu última atención con esta paciente fue hace más de 12 meses. Para editar, pedí un turno a recepción')).toBeVisible();
  await expect(page.getByText('Penicilina (sintético)')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Editar ficha' })).toHaveCount(0);
  await verificarPantalla(page, 'ficha de solo lectura');

  await page.getByRole('tab', { name: 'Odontograma' }).click();
  await expect(page.getByRole('button', { name: 'Ver historial' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Agregar al lote' })).toHaveCount(0);
  await verificarPantalla(page, 'odontograma de solo lectura');
});

test('una paciente ajena muestra el mensaje de falta de acceso y ningún dato clínico', async ({ page }) => {
  await ingresar(page, EMAIL_ODONTOLOGA);
  await page.goto(`/#/pacientes/${String(lucia)}`);
  await expect(page.getByText('No tenés acceso a esta paciente: el acceso empieza cuando un turno con vos se marca atendido')).toBeVisible();
  await expect(page.getByText('Penicilina (sintético)')).toHaveCount(0);
  await verificarPantalla(page, 'paciente ajena');
});
