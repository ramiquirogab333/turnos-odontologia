import { expect, test } from '@playwright/test';
import { accesoPorApi, API, diaDe, enMs, HORA, ingresar, irAlDia, irASeccion, MINUTO, verificarPantalla } from './ayudas';
import { contarPacientes, EMAIL_ODONTOLOGA, leerPacienteDeTurno, sembrar, sembrarPaciente, sembrarTurno, type Semilla } from './datos';

/** Listado de pacientes (C-12) contra el backend real. Datos 100 % sintéticos (R19). */
let semilla: Semilla;

test.beforeEach(async () => {
  semilla = await sembrar();
});

test('la búsqueda de pacientes funciona a 360 px sin desplazamiento horizontal y filtra por nombre y por ausencias', async ({ page }) => {
  const lucia = await sembrarPaciente('Lucía', 'Ejemplo', '30111222');
  await sembrarPaciente('Martín', 'Prueba', '28999888');
  await sembrarTurno(semilla, { inicio: enMs(-3 * HORA), estado: 'ausente', nombre: 'Lucía Ejemplo', pacienteId: lucia });

  await ingresar(page);
  await irASeccion(page, 'Pacientes');

  const lista = page.getByRole('list', { name: 'Pacientes' });
  await expect(lista.getByText('Lucía Ejemplo')).toBeVisible();
  await expect(lista.getByText('Martín Prueba')).toBeVisible();
  await verificarPantalla(page, 'listado de pacientes');

  await page.getByRole('searchbox', { name: 'Buscar por nombre, apellido o DNI' }).fill('lucia');
  await expect(lista.getByText('Martín Prueba')).toHaveCount(0);
  await expect(lista.getByText('Lucía Ejemplo')).toBeVisible();
  await expect(lista.getByText(/DNI 30111222/)).toBeVisible();
  await expect(lista.getByText(/1 ausencia\b/)).toBeVisible();
  await verificarPantalla(page, 'resultado de la búsqueda');

  await page.getByRole('searchbox').fill('zzz');
  await expect(page.getByText('No encontramos pacientes con «zzz»')).toBeVisible();
  await expect(page.getByText(/buscá por DNI/)).toBeVisible();
  await verificarPantalla(page, 'búsqueda sin resultados');

  await page.getByRole('searchbox').fill('');
  await page.getByRole('button', { name: 'Con ausencias' }).click();
  await expect(page.getByRole('button', { name: 'Con ausencias' })).toHaveAttribute('aria-pressed', 'true');
  await expect(lista.getByText('Martín Prueba')).toHaveCount(0);
  await expect(lista.getByText('Lucía Ejemplo')).toBeVisible();

  // También se encuentra por el comienzo del DNI.
  await page.getByRole('button', { name: 'Con ausencias' }).click();
  await page.getByRole('searchbox').fill('2899');
  await expect(lista.getByText('Martín Prueba')).toBeVisible();
  await expect(lista.getByText('Lucía Ejemplo')).toHaveCount(0);
});

test('la odontóloga no ve la sección de pacientes y el servidor tampoco se la da', async ({ page, request }) => {
  await sembrarPaciente('Lucía', 'Ejemplo', '30111222');
  await sembrarTurno(semilla, { inicio: enMs(2 * HORA + 5 * MINUTO) });

  await ingresar(page, EMAIL_ODONTOLOGA);
  // C-10: la odontóloga ve una navegación acotada a su agenda y a Google Calendar (nada de pacientes ni caja).
  await expect(page.getByRole('navigation', { name: 'Secciones del panel' }).getByRole('link')).toHaveText(['Agenda', 'Google Calendar']);

  await page.goto('/#/pacientes');
  await expect(page.getByRole('heading', { level: 1, name: 'Agenda' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Pacientes' })).toHaveCount(0);

  const r = await request.get(`${API}/api/panel/pacientes/listado`, { headers: await accesoPorApi(request, EMAIL_ODONTOLOGA) });
  expect(r.status()).toBe(403);
});

test('recepción vincula un turno manual con un DNI nuevo (alta precargada), corrige el vínculo con confirmación y la tarjeta muestra «Ver ficha»', async ({ page }) => {
  const inicio = enMs(2 * HORA + 5 * MINUTO);
  const turno = await sembrarTurno(semilla, { inicio, origen: 'manual', nombre: 'Carlos Sintético' });
  const mateo = await sembrarPaciente('Mateo', 'Prueba', '99000002');

  await ingresar(page);
  await irAlDia(page, diaDe(inicio));
  await expect(page.getByText('Carlos Sintético')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ver ficha' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Vincular paciente' }).click();
  await page.getByLabel('DNI del paciente').fill('99000003');
  await page.getByRole('button', { name: 'Buscar' }).click();
  await expect(page.getByText('No hay ningún paciente con ese DNI')).toBeVisible();
  await verificarPantalla(page, 'vincular: DNI no registrado');
  await page.getByRole('button', { name: 'Dar de alta y vincular' }).click();
  await expect(page.getByLabel('DNI', { exact: true })).toHaveValue('99000003');
  await expect(page.getByLabel('Teléfono')).toHaveValue('+5491144445555');
  await expect(page.getByLabel('Nombre', { exact: true })).toHaveValue('Carlos');
  await expect(page.getByLabel('Apellido')).toHaveValue('Sintético');
  await verificarPantalla(page, 'vincular: alta precargada');
  await page.getByRole('button', { name: 'Guardar paciente' }).click();
  await expect(page.getByRole('link', { name: 'Ver ficha' })).toBeVisible();
  expect(await contarPacientes()).toBe(2);
  const nuevo = await leerPacienteDeTurno(turno);
  expect(nuevo).not.toBeNull();
  expect(nuevo).not.toBe(mateo);

  // Corregir el vínculo: aviso de acceso clínico antes de enviar.
  await page.getByRole('button', { name: 'Cambiar paciente' }).click();
  await page.getByLabel('DNI del paciente').fill('99000002');
  await page.getByRole('button', { name: 'Buscar' }).click();
  await page.getByRole('button', { name: 'Vincular a Mateo Prueba' }).click();
  await expect(page.getByText(/puede ganar o perder acceso clínico/)).toBeVisible();
  await verificarPantalla(page, 'vincular: confirmar el cambio');
  expect(await leerPacienteDeTurno(turno)).toBe(nuevo);
  await page.getByRole('button', { name: 'Confirmar el cambio' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await leerPacienteDeTurno(turno)).toBe(mateo);

  await page.getByRole('link', { name: 'Ver ficha' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Mateo Prueba' })).toBeVisible();
  await expect(page.getByText('+5491144446666')).toBeVisible();
  await verificarPantalla(page, 'detalle del paciente de recepción');
});

test('la odontóloga ve el mensaje de primera visita antes de marcar atendido y, después, abre la ficha editable', async ({ page }) => {
  const lucia = await sembrarPaciente('Lucía', 'Ejemplo', '99000001');
  const inicio = enMs(-5 * MINUTO);
  const turno = await sembrarTurno(semilla, { inicio, estado: 'confirmado', nombre: 'Lucía Ejemplo', pacienteId: lucia });

  await ingresar(page, EMAIL_ODONTOLOGA);
  await irAlDia(page, diaDe(inicio));
  await expect(page.getByRole('button', { name: 'Vincular paciente' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Cambiar paciente' })).toHaveCount(0);
  await page.getByRole('link', { name: 'Ver ficha' }).click();
  await expect(page.getByText('Vas a poder ver la ficha cuando marques el turno como atendido.')).toBeVisible();
  await expect(page.getByText('Lucía Ejemplo', { exact: true })).toHaveCount(0);
  await verificarPantalla(page, 'primera visita sin atender');

  await page.getByRole('link', { name: 'Volver a la agenda' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Agenda' })).toBeVisible();
  await irAlDia(page, diaDe(inicio));
  await page.getByRole('button', { name: 'Marcar atendido' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Sí, marcar atendido' }).click();
  await expect(page.getByText('Atendido', { exact: true })).toBeVisible();
  expect(await leerPacienteDeTurno(turno)).toBe(lucia);

  await page.getByRole('link', { name: 'Ver ficha' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Lucía Ejemplo' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Editar ficha|Completar ficha/ })).toBeVisible();
  await verificarPantalla(page, 'ficha editable tras la primera visita');
});

test('recepción da de alta un paciente desde Pacientes y llega a su detalle; un DNI repetido enlaza al existente', async ({ page }) => {
  const lucia = await sembrarPaciente('Lucía', 'Ejemplo', '99000001');
  await ingresar(page);
  await irASeccion(page, 'Pacientes');
  await page.getByRole('button', { name: 'Nuevo paciente' }).click();
  await page.getByLabel('Nombre', { exact: true }).fill('Mateo');
  await page.getByLabel('Apellido').fill('Prueba');
  await page.getByLabel('DNI', { exact: true }).fill('99000001');
  await page.getByLabel('Teléfono').fill('+5491100000002');
  await page.getByRole('button', { name: 'Guardar paciente' }).click();
  await expect(page.getByText('Ya hay un paciente con ese DNI')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ver a Lucía Ejemplo' })).toHaveAttribute('href', `#/pacientes/${String(lucia)}`);
  await verificarPantalla(page, 'DNI repetido');

  await page.getByLabel('DNI', { exact: true }).fill('99000002');
  await page.getByRole('button', { name: 'Guardar paciente' }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Mateo Prueba' })).toBeVisible();
  await page.getByRole('tab', { name: 'Datos' }).click();
  await expect(page.getByLabel('DNI', { exact: true })).toHaveValue('99000002');
  await verificarPantalla(page, 'datos del paciente');
});
