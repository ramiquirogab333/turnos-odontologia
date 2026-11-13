import { expect, type APIRequestContext, type Browser, type Page } from '@playwright/test';
import { diaClinica, etiquetaDiaLarga, hoyClinica, sumarDias } from '../src/lib/tiempo';
import { CLAVE, EMAIL_RECEPCION } from './datos';

export const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000';
export const MINUTO = 60_000;
export const HORA = 3_600_000;

/** Instante `delta` ms en el futuro (o en el pasado si es negativo), sin segundos ni milisegundos. */
export function enMs(delta: number): Date {
  const d = new Date(Date.now() + delta);
  d.setUTCSeconds(0, 0);
  return d;
}

/** Redondea hacia arriba a la próxima media hora (la grilla de turnos de 30 minutos de la semilla). */
export function proximaMediaHora(desde: Date): Date {
  const d = new Date(desde);
  d.setUTCSeconds(0, 0);
  const resto = d.getUTCMinutes() % 30;
  if (resto !== 0) d.setUTCMinutes(d.getUTCMinutes() + (30 - resto));
  return d;
}

/** Día objetivo del alta manual: 3 días adelante en la clínica (la semilla tiene franja todos los días). */
export function diaObjetivo(): string {
  return sumarDias(hoyClinica(new Date()), 3);
}

export function inicioClinica(dia: string, hhmm: string): string {
  return `${dia}T${hhmm}:00-03:00`;
}

/** Abre el panel en una página nueva del contexto dado y espera a que decida entre el ingreso y la agenda. */
export async function ingresar(page: Page, email = EMAIL_RECEPCION, clave = CLAVE): Promise<void> {
  await page.goto('/');
  await page.getByLabel('Correo electrónico').fill(email);
  await page.getByLabel('Contraseña').fill(clave);
  await page.getByRole('button', { name: 'Ingresar al panel' }).click();
  await expect(page.getByRole('heading', { name: 'Agenda', level: 1 })).toBeVisible();
}

/** Access token por la API (para verificar contra el servidor sin pasar por la pantalla). */
export async function accesoPorApi(request: APIRequestContext, email = EMAIL_RECEPCION): Promise<Record<string, string>> {
  const r = await request.post(`${API}/api/auth/login`, { data: { email, password: CLAVE } });
  expect(r.status(), 'el login sintético debe funcionar').toBe(200);
  const { access_token: token } = (await r.json()) as { access_token: string };
  return { Authorization: `Bearer ${token}` };
}

/**
 * Navega con "Día anterior"/"Día siguiente" hasta el día de la clínica pedido (máx. unos pocos días).
 * `desde` es el día que muestra la pantalla ahora (por defecto, hoy: la agenda abre en el día de hoy).
 */
export async function irAlDia(page: Page, dia: string, desde: string = hoyClinica(new Date())): Promise<void> {
  const delta = Math.round((Date.parse(`${dia}T12:00:00Z`) - Date.parse(`${desde}T12:00:00Z`)) / 86_400_000);
  const boton = page.getByRole('button', { name: delta < 0 ? 'Día anterior' : 'Día siguiente' });
  for (let i = 0; i < Math.abs(delta); i += 1) await boton.click();
  await expect(page.getByRole('heading', { level: 2, name: new RegExp(etiquetaDiaLarga(dia), 'i') })).toBeVisible();
}

export function diaDe(inicio: Date): string {
  return diaClinica(inicio.toISOString());
}

/** R3: ni la página ni ningún elemento se salen del ancho de la pantalla. */
export async function verificarSinScrollHorizontal(page: Page, donde: string): Promise<void> {
  const medidas = await page.evaluate(() => {
    const doc = document.documentElement;
    let maxDerecha = 0;
    for (const el of Array.from(document.body.querySelectorAll('*'))) {
      if (el.closest('.grilla-contenedor')) continue; // la grilla semanal desliza por dentro, no la página
      const caja = el.getBoundingClientRect();
      if (caja.width > 0) maxDerecha = Math.max(maxDerecha, caja.right);
    }
    return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth, innerWidth: window.innerWidth, maxDerecha };
  });
  expect(medidas.scrollWidth, `scroll horizontal en ${donde}`).toBeLessThanOrEqual(medidas.clientWidth);
  expect(medidas.maxDerecha, `elemento fuera de pantalla en ${donde}`).toBeLessThanOrEqual(medidas.innerWidth + 0.5);
}

/** R3: todo lo tocable mide al menos 48px de alto. */
export async function verificarObjetivosTactiles(page: Page, donde: string): Promise<void> {
  const chicos = await page.evaluate(() => {
    const tocables = Array.from(
      document.querySelectorAll<HTMLElement>(
        'button, select, input[type="text"], input[type="search"], input[type="tel"], input[type="email"], input[type="password"], input[type="date"]',
      ),
    );
    return tocables
      .filter((el) => el.offsetParent !== null)
      .map((el) => ({
        texto: (el.textContent ?? el.getAttribute('aria-label') ?? el.getAttribute('name') ?? '').trim().slice(0, 30),
        alto: el.getBoundingClientRect().height,
      }))
      .filter((m) => m.alto < 47.5);
  });
  expect(chicos, `objetivos táctiles < 48px en ${donde}`).toEqual([]);
}

export async function verificarPantalla(page: Page, donde: string): Promise<void> {
  await verificarSinScrollHorizontal(page, donde);
  await verificarObjetivosTactiles(page, donde);
}

/** Abre una página nueva en un contexto propio con las mismas condiciones del proyecto (misma zona horaria). */
export async function contextoNuevo(browser: Browser, ancho: number, alto: number) {
  return browser.newContext({ viewport: { width: ancho, height: alto }, locale: 'es-AR', timezoneId: 'Asia/Tokyo' });
}

/** Pasa a otra sección del panel con la navegación y espera su título. */
export async function irASeccion(
  page: Page,
  seccion: 'Agenda' | 'Pacientes' | 'Indicadores' | 'Caja' | 'Recordatorios' | 'Google Calendar' | 'Datos',
): Promise<void> {
  await page.getByRole('navigation', { name: 'Secciones del panel' }).getByRole('link', { name: seccion }).click();
  await expect(page.getByRole('heading', { level: 1, name: seccion })).toBeVisible();
}

/** Día de la clínica de un instante, a medianoche -03:00 + `hhmm` (para sembrar movimientos de un día pasado). */
export function instanteClinica(dia: string, hhmm: string): Date {
  return new Date(inicioClinica(dia, hhmm));
}

// --- Google Calendar (C-10): el servidor falso de Google del perfil e2e de Compose -------------------------------------

export const GCAL = process.env['E2E_GCAL_URL'] ?? 'http://localhost:8090';

export interface EventoGoogleFalso {
  readonly id: string;
  readonly summary: string;
  readonly description: string;
  readonly start: { readonly dateTime: string };
  readonly end: { readonly dateTime: string };
}

/** Lo que "hace la profesional en Google" y las fallas de Google (endpoints /_control del falso). */
export async function controlGoogle(request: APIRequestContext, ruta: string, cuerpo: Record<string, unknown> = {}): Promise<void> {
  const r = await request.post(`${GCAL}/_control/${ruta}`, { data: cuerpo });
  expect(r.ok(), `el Google falso debe estar arriba en ${GCAL} (docker compose --profile e2e up -d gcal-falso)`).toBe(true);
}

export async function eventosGoogle(request: APIRequestContext): Promise<EventoGoogleFalso[]> {
  const r = await request.get(`${GCAL}/_control/eventos`);
  expect(r.ok()).toBe(true);
  return (await r.json()) as EventoGoogleFalso[];
}

/** Conecta a la odontóloga con el Google falso por la API (consentimiento + callback), sin pasar por la pantalla. */
export async function conectarGooglePorApi(request: APIRequestContext, email: string): Promise<void> {
  const cabecera = await accesoPorApi(request, email);
  const iniciar = await request.post(`${API}/api/panel/google-calendar/conexion/iniciar`, { headers: cabecera });
  expect(iniciar.status(), 'iniciar la conexión (¿GCAL_* configuradas en el backend?)').toBe(200);
  const { url_autorizacion: url } = (await iniciar.json()) as { url_autorizacion: string };
  const consentimiento = await request.get(url, { maxRedirects: 0 });
  expect(consentimiento.status()).toBe(302);
  const callback = await request.get(consentimiento.headers()['location'] ?? '', { maxRedirects: 0 });
  expect(callback.status()).toBe(303);
  expect(callback.headers()['location']).toContain('resultado=conectado');
}
