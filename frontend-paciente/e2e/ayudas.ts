import { expect, type Browser, type Page } from '@playwright/test';
import { etiquetaDiaLarga, hoyClinica, sumarDias } from '../src/lib/tiempo';
import type { Semilla } from './datos';

export const NOMBRE = 'Carlos Sintético';
export const TELEFONO = '+5491144445555';
export const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000';

/** Día objetivo: 3 días adelante en la clínica, con franja todos los días (la semilla), nunca "hoy". */
export function diaObjetivo(): string {
  return sumarDias(hoyClinica(new Date()), 3);
}

/** Instante ISO con offset de la clínica (-03:00), igual que lo devuelve la API. */
export function inicioClinica(dia: string, hhmm: string): string {
  return `${dia}T${hhmm}:00-03:00`;
}

/** R3: ni la página ni ningún elemento (salvo la tira de días, que desliza por diseño) se salen de 360px. */
export async function verificarSinScrollHorizontal(page: Page, donde: string): Promise<void> {
  const medidas = await page.evaluate(() => {
    const doc = document.documentElement;
    let maxDerecha = 0;
    for (const el of Array.from(document.body.querySelectorAll('*'))) {
      if (el.closest('.dias') || el.classList.contains('solo-lectores') || el.closest('.solo-lectores')) continue;
      const caja = el.getBoundingClientRect();
      if (caja.width > 0) maxDerecha = Math.max(maxDerecha, caja.right);
    }
    return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth, innerWidth: window.innerWidth, maxDerecha };
  });
  expect(medidas.clientWidth, `viewport en ${donde}`).toBe(360);
  expect(medidas.scrollWidth, `scroll horizontal en ${donde}`).toBeLessThanOrEqual(medidas.clientWidth);
  expect(medidas.maxDerecha, `elemento fuera de pantalla en ${donde}`).toBeLessThanOrEqual(medidas.innerWidth + 0.5);
}

/** R3: todo lo tocable mide al menos 48px de alto. */
export async function verificarObjetivosTactiles(page: Page, donde: string): Promise<void> {
  const chicos = await page.evaluate(() => {
    const tocables = Array.from(
      document.querySelectorAll<HTMLElement>('button, input[type="text"], input[type="tel"], label.opcion'),
    );
    return tocables
      .filter((el) => el.offsetParent !== null)
      .map((el) => ({ texto: (el.textContent ?? el.getAttribute('name') ?? '').trim().slice(0, 30), alto: el.getBoundingClientRect().height }))
      .filter((m) => m.alto < 47.5);
  });
  expect(chicos, `objetivos táctiles < 48px en ${donde}`).toEqual([]);
}

export async function verificarPantalla(page: Page, donde: string): Promise<void> {
  await verificarSinScrollHorizontal(page, donde);
  await verificarObjetivosTactiles(page, donde);
}

export async function elegirTratamiento(page: Page, nombre = /limpieza dental/i): Promise<void> {
  await page.getByRole('radio', { name: nombre }).check();
  await verificarPantalla(page, 'paso 1');
  await page.getByRole('button', { name: 'Ver horarios' }).click();
}

export async function elegirHorario(page: Page, dia: string, hhmm: string): Promise<void> {
  await page.getByRole('button', { name: etiquetaDiaLarga(dia), exact: true }).click();
  await page.getByRole('button', { name: hhmm, exact: true }).click();
  await verificarPantalla(page, 'paso 2');
  await page.getByRole('button', { name: 'Continuar' }).click();
}

export async function completarContacto(page: Page, telefono = TELEFONO, nombre = NOMBRE): Promise<void> {
  await page.getByLabel('Nombre completo').fill(nombre);
  await page.getByLabel('Teléfono (WhatsApp)').fill(telefono);
}

/** Abre una página nueva (contexto propio) con las mismas condiciones móviles que el proyecto. */
export async function abrirPaciente(browser: Browser): Promise<Page> {
  const contexto = await browser.newContext({
    viewport: { width: 360, height: 800 },
    isMobile: true,
    hasTouch: true,
    locale: 'es-AR',
    timezoneId: 'Asia/Tokyo',
  });
  const page = await contexto.newPage();
  await page.goto('/');
  return page;
}

/** Lleva un paciente nuevo hasta el paso 3 con el horario dado. */
export async function llegarAlPaso3(page: Page, dia: string, hhmm: string): Promise<void> {
  await elegirTratamiento(page);
  await elegirHorario(page, dia, hhmm);
  await expect(page.getByRole('heading', { name: 'Confirmá tus datos' })).toBeVisible();
}

export type { Semilla };
