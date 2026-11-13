import { readFile } from 'node:fs/promises';
import { expect, test, type Page } from '@playwright/test';
import { hoyClinica, sumarDias } from '../src/lib/tiempo';
import { accesoPorApi, API, enMs, HORA, ingresar, irASeccion, verificarPantalla } from './ayudas';
import { EMAIL_ADMIN, EMAIL_ODONTOLOGA, sembrar, sembrarPaciente, sembrarTurno, type Semilla } from './datos';

/** Datos (C-13): exportar a CSV y consultar la auditoría contra el backend real. Datos 100 % sintéticos (R19). */
let semilla: Semilla;

const BOM = '﻿';
const DIA = 24 * HORA;

test.beforeEach(async () => {
  semilla = await sembrar();
});

/** Descarga lo que dispara el botón y devuelve su nombre y su contenido (con el BOM, tal cual llegó). */
async function descargar(page: Page): Promise<{ nombre: string; texto: string }> {
  const espera = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Descargar CSV' }).click();
  const descarga = await espera;
  const ruta = await descarga.path();
  return { nombre: descarga.suggestedFilename(), texto: await readFile(ruta, 'utf-8') };
}

test('recepción descarga los turnos de la semana a 360 px y no ve ni pacientes ni auditoría', async ({ page }) => {
  const hoy = hoyClinica(new Date());
  await sembrarTurno(semilla, { inicio: enMs(DIA), nombre: 'Lucía Ejemplo' });
  await sembrarTurno(semilla, { inicio: enMs(2 * DIA), nombre: 'Mateo Prueba', sillon: 2, profesional: 'bruno' });
  await sembrarTurno(semilla, { inicio: enMs(3 * DIA), nombre: '=HYPERLINK("http://example.invalid","ver")' });
  await sembrarTurno(semilla, { inicio: enMs(40 * DIA), nombre: 'Fuera Del Rango' });

  await ingresar(page);
  await irASeccion(page, 'Datos');
  await expect(page.getByRole('tab', { name: 'Exportar' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tab', { name: 'Auditoría' })).toHaveCount(0);
  await expect(page.getByLabel('¿Qué querés exportar?').locator('option')).toHaveText(['Turnos', 'Cierres de caja']);
  await verificarPantalla(page, 'exportación (recepción)');

  await page.getByLabel('Desde (opcional)').fill(hoy);
  await page.getByLabel('Hasta (opcional)').fill(sumarDias(hoy, 7));
  const { nombre, texto } = await descargar(page);

  expect(nombre).toBe(`turnos_${hoy}.csv`);
  expect(texto.startsWith(BOM + 'id,inicio,fin,estado,origen,profesional_id,profesional,')).toBe(true);
  const lineas = texto.trimEnd().split('\r\n');
  expect(lineas).toHaveLength(4); // encabezado + los 3 turnos de la semana
  expect(texto).toContain('Lucía Ejemplo');
  expect(texto).toContain("'=HYPERLINK("); // la fórmula llega neutralizada
  expect(texto).not.toContain('Fuera Del Rango');
  expect(texto).not.toContain('E2E-CODIGO'); // nunca el código de gestión
  await expect(page.getByText(`Descargamos turnos_${hoy}.csv.`)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Descargar CSV' })).toBeEnabled();
  await verificarPantalla(page, 'exportación terminada');

  // Si fuerza la pestaña de auditoría recibe el mensaje de permiso, sin consultar nada.
  await page.goto('/#/datos?pestana=auditoria');
  await expect(page.getByText('No tenés permiso para ver la auditoría.')).toBeVisible();
});

test('el admin exporta pacientes y encuentra su exportación en la auditoría, a 360 px', async ({ page }) => {
  await sembrarPaciente('Lucía', 'Ejemplo', '30111222');
  await sembrarPaciente('Martín', 'Prueba', '28999888');

  await ingresar(page, EMAIL_ADMIN);
  await irASeccion(page, 'Datos');
  await expect(page.getByLabel('¿Qué querés exportar?').locator('option')).toHaveText(['Turnos', 'Pacientes', 'Cierres de caja']);
  await page.getByLabel('¿Qué querés exportar?').selectOption('pacientes');
  const { nombre, texto } = await descargar(page);
  expect(nombre).toBe(`pacientes_${hoyClinica(new Date())}.csv`);
  expect(texto.trimEnd().split('\r\n')).toHaveLength(3); // encabezado + 2 pacientes activos
  expect(texto).toContain('30111222');

  await page.getByRole('tab', { name: 'Auditoría' }).click();
  await page.getByLabel('Tipo').selectOption('exportacion');
  await page.getByRole('button', { name: 'Buscar' }).click();
  const lista = page.getByRole('list', { name: 'Registros de auditoría' });
  await expect(lista.getByText('Exportación de datos')).toHaveCount(1);
  await expect(lista.getByText('Alma Administración')).toBeVisible();
  await expect(lista.getByText(/paciente · IP /)).toBeVisible();
  await expect(lista).not.toContainText('Lucía'); // el registro no lleva datos personales
  await expect(lista).not.toContainText('30111222');
  await verificarPantalla(page, 'auditoría filtrada por exportación');

  await page.getByLabel('Tipo').selectOption('cierre_caja');
  await page.getByRole('button', { name: 'Buscar' }).click();
  await expect(page.getByText('No hay registros para estos filtros')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ver más' })).toHaveCount(0);
});

test('un 429 con Retry-After de 600 segundos muestra el mensaje de 10 minutos y no descarga nada', async ({ page }) => {
  await ingresar(page);
  await irASeccion(page, 'Datos');
  await page.route('**/api/panel/export*', (ruta) =>
    ruta.fulfill({
      status: 429,
      headers: { 'Content-Type': 'application/json', 'Retry-After': '600' },
      body: JSON.stringify({ detail: 'Demasiados intentos. Probá de nuevo más tarde.', motivo: 'demasiados_intentos' }),
    }),
  );
  let descargas = 0;
  page.on('download', () => {
    descargas += 1;
  });
  await page.getByRole('button', { name: 'Descargar CSV' }).click();
  await expect(page.getByRole('alert')).toContainText('Hiciste muchas exportaciones seguidas. Probá de nuevo en 10 minutos');
  await expect(page.getByRole('button', { name: 'Descargar CSV' })).toBeEnabled();
  await verificarPantalla(page, 'límite de exportaciones');
  expect(descargas).toBe(0);
});

test('la odontóloga no ve «Datos» y el servidor tampoco le exporta nada', async ({ page, request }) => {
  await ingresar(page, EMAIL_ODONTOLOGA);
  await expect(page.getByRole('navigation', { name: 'Secciones del panel' }).getByRole('link')).toHaveText(['Agenda', 'Google Calendar']);
  await page.goto('/#/datos');
  await expect(page.getByRole('heading', { level: 1, name: 'Agenda' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Datos' })).toHaveCount(0);

  const cabeceras = await accesoPorApi(request, EMAIL_ODONTOLOGA);
  for (const entidad of ['turnos', 'pacientes', 'cierres_caja']) {
    const r = await request.get(`${API}/api/panel/export?entidad=${entidad}&formato=csv`, { headers: cabeceras });
    expect(r.status(), `exportar ${entidad} como odontóloga`).toBe(403);
  }
});
