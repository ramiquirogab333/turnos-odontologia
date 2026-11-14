import { expect, test, type Page } from '@playwright/test';
import { hoyClinica, sumarDias } from '../src/lib/tiempo';
import { accesoPorApi, API, diaObjetivo, enMs, HORA, ingresar, inicioClinica, irAlDia, irASeccion, verificarPantalla } from './ayudas';
import { EMAIL_ODONTOLOGA, leerTurnos, sembrar, sembrarTurno, type Semilla } from './datos';

/**
 * Catálogo (C-14): duración, precio, horarios y bajas contra el backend real, a 360 y 1280 px (R3, R7).
 * Los datos son 100 % sintéticos (R19) y los crea la prueba: `sembrar()` deja la base limpia antes de cada test.
 */
let semilla: Semilla;

const NOMBRES_DIA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const DIA = 24 * HORA;

test.beforeEach(async () => {
  semilla = await sembrar();
});

/** Índice del día de la semana (0 = lunes) de una fecha "YYYY-MM-DD" de la clínica. */
function indiceDeDia(dia: string): number {
  return (new Date(`${dia}T12:00:00Z`).getUTCDay() + 6) % 7;
}

/** El próximo día de la clínica (al menos mañana) que cae en el día de la semana pedido. */
function proximo(indice: number): string {
  let dia = sumarDias(hoyClinica(new Date()), 1);
  while (indiceDeDia(dia) !== indice) dia = sumarDias(dia, 1);
  return dia;
}

interface HorarioPublico {
  readonly inicio: string;
  readonly fin: string;
}

async function horariosPublicos(page: Page, profesionalId: number, tratamientoId: number, dia: string): Promise<HorarioPublico[]> {
  const q = new URLSearchParams({
    profesional_id: String(profesionalId),
    tratamiento_id: String(tratamientoId),
    desde: dia,
    hasta: dia,
  });
  const r = await page.request.get(`${API}/api/public/disponibilidad?${q.toString()}`);
  expect(r.status()).toBe(200);
  return ((await r.json()) as { slots: HorarioPublico[] }).slots;
}

async function abrirCatalogo(page: Page, pestana: 'Tratamientos' | 'Profesionales' | 'Sillones' | 'Horarios' = 'Tratamientos'): Promise<void> {
  await ingresar(page);
  await irASeccion(page, 'Catálogo');
  await expect(page.getByRole('tab', { name: 'Tratamientos' })).toHaveAttribute('aria-selected', 'true');
  if (pestana !== 'Tratamientos') await page.getByRole('tab', { name: pestana }).click();
  await expect(page.getByRole('tab', { name: pestana })).toHaveAttribute('aria-selected', 'true');
}

const fila = (page: Page, texto: string) => page.getByRole('listitem').filter({ hasText: texto });

test('recepción cambia la duración y los horarios públicos pasan a durar lo nuevo (US-008 CA-2)', async ({ page }) => {
  const dia = proximo(2);
  const antes = await horariosPublicos(page, semilla.profesionalId, semilla.limpiezaId, dia);
  expect(antes.length).toBeGreaterThan(0);
  expect(new Set(antes.map((h) => Date.parse(h.fin) - Date.parse(h.inicio)))).toEqual(new Set([30 * 60_000]));

  await abrirCatalogo(page);
  await verificarPantalla(page, 'catálogo: tratamientos');
  await fila(page, 'Limpieza dental').getByRole('button', { name: 'Editar' }).click();
  await expect(page.getByText(/valen solo para los turnos que se tomen desde ahora/)).toBeVisible();
  await page.getByLabel('Duración (minutos)').fill('45');
  await page.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(page.getByText('Guardamos los cambios')).toBeVisible();
  await expect(fila(page, 'Limpieza dental').getByText('45 min')).toBeVisible();

  const despues = await horariosPublicos(page, semilla.profesionalId, semilla.limpiezaId, dia);
  expect(despues.length).toBeGreaterThan(0);
  expect(new Set(despues.map((h) => Date.parse(h.fin) - Date.parse(h.inicio)))).toEqual(new Set([45 * 60_000]));
});

test('una duración inválida se explica junto al campo y no cambia nada', async ({ page }) => {
  await abrirCatalogo(page);
  await fila(page, 'Limpieza dental').getByRole('button', { name: 'Editar' }).click();
  await page.getByLabel('Duración (minutos)').fill('7');
  await page.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(page.getByText('La duración va de 5 a 480 minutos, en múltiplos de 5')).toBeVisible();
  await expect(page.getByLabel('Duración (minutos)')).toHaveValue('7');
  await verificarPantalla(page, 'catálogo: error de duración');
});

test('recepción agrega una franja el martes y los horarios públicos de ese martes la respetan; una superpuesta se rechaza', async ({ page }) => {
  const martes = proximo(1);
  await abrirCatalogo(page, 'Horarios');
  await page.getByLabel('Profesional').selectOption({ label: 'Dra. Ana Ficticia' });
  const bloque = page.getByRole('region', { name: 'Martes' });
  await expect(bloque.getByText('00:00 a 23:59')).toBeVisible(); // la semilla trae atención todos los días

  // Se quita la franja de todo el día y se reemplaza por una de 09:00 a 13:00 con "Sillón 1".
  await bloque.getByRole('button', { name: 'Quitar franja' }).click();
  await expect(page.getByRole('dialog').getByText('No hay turnos tomados en esta franja.')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Quitar franja' }).click();
  await expect(bloque.getByText('Sin atención este día')).toBeVisible();

  await bloque.getByRole('button', { name: 'Agregar franja' }).click();
  await page.getByLabel('Desde').fill('09:00');
  await page.getByLabel('Hasta').fill('13:00');
  await page.getByLabel('Sillón preferido').selectOption({ label: 'Sillón 1' });
  await page.getByRole('button', { name: 'Guardar franja' }).click();
  await expect(bloque.getByText('09:00 a 13:00')).toBeVisible();
  await expect(bloque.getByText('Activa')).toBeVisible();
  await verificarPantalla(page, 'catálogo: horarios');

  const horarios = await horariosPublicos(page, semilla.profesionalId, semilla.limpiezaId, martes);
  expect(horarios.length).toBeGreaterThan(0);
  for (const h of horarios) {
    const hora = h.inicio.slice(11, 16);
    expect(hora >= '09:00' && h.fin.slice(11, 16) <= '13:00', `horario fuera de la franja: ${h.inicio}`).toBe(true);
  }

  // Una franja que se pisa con la anterior se explica y conserva lo escrito.
  await bloque.getByRole('button', { name: 'Agregar franja' }).click();
  await page.getByLabel('Desde').fill('12:00');
  await page.getByLabel('Hasta').fill('15:00');
  await page.getByRole('button', { name: 'Guardar franja' }).click();
  await expect(page.getByText('Se superpone con la franja de 09:00 a 13:00 del martes')).toBeVisible();
  await expect(page.getByLabel('Desde')).toHaveValue('12:00');
  await expect(page.getByLabel('Hasta')).toHaveValue('15:00');
  await expect(bloque.getByText(/^\d\d:\d\d a \d\d:\d\d$/)).toHaveCount(1);
});

test('quitar una franja con un turno tomado lo informa y el turno sigue en la agenda', async ({ page }) => {
  const dia = diaObjetivo();
  await sembrarTurno(semilla, { inicio: new Date(inicioClinica(dia, '10:00')), nombre: 'Lucía Ejemplo' });

  await abrirCatalogo(page, 'Horarios');
  await page.getByLabel('Profesional').selectOption({ label: 'Dra. Ana Ficticia' });
  const bloque = page.getByRole('region', { name: NOMBRES_DIA[indiceDeDia(dia)] ?? '' });
  await bloque.getByRole('button', { name: 'Quitar franja' }).click();
  const dialogo = page.getByRole('dialog');
  await expect(dialogo.getByText('Hay 1 turno tomado en esta franja. No se cancela: sigue en la agenda.')).toBeVisible();
  await expect(dialogo.getByText('Los pacientes nuevos ya no podrán reservar en ese horario.')).toBeVisible();
  await verificarPantalla(page, 'catálogo: confirmar quitar franja');
  await dialogo.getByRole('button', { name: 'Quitar franja' }).click();
  await expect(bloque.getByText('Sin atención este día')).toBeVisible();

  const turnos = await leerTurnos();
  expect(turnos).toHaveLength(1);
  expect(turnos[0]?.estado).toBe('reservado');

  await irASeccion(page, 'Agenda');
  await irAlDia(page, dia);
  await expect(page.getByText('Lucía Ejemplo')).toBeVisible();
});

test('desactivar un tratamiento lo saca del listado público y borrar uno usado se explica y ofrece desactivar', async ({ page }) => {
  await sembrarTurno(semilla, { inicio: enMs(2 * DIA), nombre: 'Mateo Prueba' });
  const publico = async (): Promise<string[]> => {
    const r = await page.request.get(`${API}/api/public/tratamientos`);
    return ((await r.json()) as { nombre: string }[]).map((t) => t.nombre);
  };
  expect(await publico()).toEqual(['Limpieza dental']);

  await abrirCatalogo(page);
  await fila(page, 'Limpieza dental').getByRole('button', { name: 'Desactivar' }).click();
  const dialogo = page.getByRole('dialog');
  await expect(dialogo.getByText('Hay 1 turno tomado en este tratamiento. No se cancela: sigue en la agenda.')).toBeVisible();
  await dialogo.getByRole('button', { name: 'Desactivar' }).click();
  await expect(fila(page, 'Limpieza dental').getByText('Inactivo')).toBeVisible();
  await expect(fila(page, 'Limpieza dental').getByText('No se ofrece para reservar')).toBeVisible();
  expect(await publico()).toEqual([]);

  // Borrar uno con turnos: 409 con el motivo y la salida de desactivar; el tratamiento sigue en la lista.
  await fila(page, 'Limpieza dental').getByRole('button', { name: 'Borrar' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Borrar tratamiento' }).click();
  await expect(page.getByRole('alert')).toContainText('No se puede borrar porque tiene turnos registrados');
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Desactivar' })).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Volver' }).click();
  await expect(fila(page, 'Limpieza dental')).toBeVisible();
});

test('las cuatro pestañas del catálogo no superan el ancho de la pantalla y sus botones se tocan bien (R3)', async ({ page }) => {
  await abrirCatalogo(page);
  for (const pestana of ['Tratamientos', 'Profesionales', 'Sillones', 'Horarios'] as const) {
    await page.getByRole('tab', { name: pestana }).click();
    await expect(page.getByRole('tab', { name: pestana })).toHaveAttribute('aria-selected', 'true');
    await verificarPantalla(page, `catálogo: ${pestana}`);
  }
  // Horarios con una profesional de siete franjas: el editor sigue dentro de la pantalla.
  await page.getByLabel('Profesional').selectOption({ label: 'Dra. Ana Ficticia' });
  await expect(page.getByRole('heading', { level: 3 })).toHaveCount(7);
  await verificarPantalla(page, 'catálogo: horarios con siete franjas');
});

test('la odontóloga no ve «Catálogo» y un enlace directo la deja en su agenda', async ({ page }) => {
  await ingresar(page, EMAIL_ODONTOLOGA);
  await expect(page.getByRole('navigation', { name: 'Secciones del panel' }).getByRole('link', { name: 'Catálogo' })).toHaveCount(0);
  const llamadasAdmin: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/api/admin/')) llamadasAdmin.push(r.url());
  });
  await page.goto('/#/catalogo?pestana=horarios');
  await expect(page.getByRole('heading', { name: 'Agenda', level: 1 })).toBeVisible();
  expect(llamadasAdmin).toEqual([]);
  // Aunque la pida por la API, el servidor la rechaza (RBAC).
  const cabecera = await accesoPorApi(page.request, EMAIL_ODONTOLOGA);
  const r = await page.request.get(`${API}/api/admin/tratamientos`, { headers: cabecera });
  expect(r.status()).toBe(403);
});
