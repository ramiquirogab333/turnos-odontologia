import { createHmac } from 'node:crypto';
import { expect, type APIRequestContext, type Browser, type Page } from '@playwright/test';
import { etiquetaDiaLarga, hoyClinica, sumarDias } from '../src/lib/tiempo';
import { CLAVE_RECEPCION, EMAIL_RECEPCION, type Semilla } from './datos';

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


/** Secreto SINTÉTICO del webhook del entorno E2E (mismo default que docker-compose.yml; nunca uno real). */
export const SECRETO_WEBHOOK = process.env['E2E_MP_WEBHOOK_SECRET'] ?? 'secreto-webhook-sintetico-e2e';

/** Firma igual que Mercado Pago: HMAC-SHA256 del manifest `id:{data.id};request-id:{x-request-id};ts:{ts};`. */
export function firmarWebhook(
  dataId: string,
  opciones: { secreto?: string; requestId?: string; tsMs?: number } = {},
): Record<string, string> {
  const requestId = opciones.requestId ?? `req-e2e-${String(Date.now())}`;
  const ts = String(opciones.tsMs ?? Date.now());
  const idFirmado = /^[a-zA-Z0-9]+$/.test(dataId) ? dataId.toLowerCase() : dataId; // como Mercado Pago: minúsculas solo si es alfanumérico
  const manifest = `id:${idFirmado};request-id:${requestId};ts:${ts};`;
  const firma = createHmac('sha256', opciones.secreto ?? SECRETO_WEBHOOK).update(manifest).digest('hex');
  return { 'x-signature': `ts=${ts},v1=${firma}`, 'x-request-id': requestId };
}

/** Envía el webhook de un pago aprobado (la pasarela falsa decodifica estado y referencia del propio id). */
export async function enviarWebhook(
  request: APIRequestContext,
  referencia: string,
  monto: string,
  opciones: { secreto?: string; estado?: string } = {},
) {
  // La pasarela falsa informa monto y moneda codificados en el id; sin ellos la acreditación va a revisión (RN-SN-09).
  const dataId = `fake-${opciones.estado ?? 'approved'}-${referencia}@${monto}@ARS`;
  return request.post(`${API}/api/webhooks/mercadopago`, {
    params: { 'data.id': dataId, type: 'payment' },
    headers: firmarWebhook(dataId, opciones.secreto === undefined ? {} : { secreto: opciones.secreto }),
    data: { type: 'payment', data: { id: dataId } },
  });
}

/** Login del usuario de recepción sintético; devuelve la cabecera Authorization. */
export async function loginRecepcion(request: APIRequestContext): Promise<Record<string, string>> {
  const r = await request.post(`${API}/api/auth/login`, { data: { email: EMAIL_RECEPCION, password: CLAVE_RECEPCION } });
  expect(r.status(), 'el login de recepción sintética debe funcionar').toBe(200);
  const { access_token: token } = (await r.json()) as { access_token: string };
  return { Authorization: `Bearer ${token}` };
}

/** Recepción acredita a mano una transferencia (RN-SN-08). */
export async function acreditarTransferencia(request: APIRequestContext, pagoId: number) {
  return request.post(`${API}/api/admin/pagos-sena/${String(pagoId)}/acreditar`, { headers: await loginRecepcion(request) });
}

/** Reserva el horario como un paciente (por la API real) y devuelve el JSON de la respuesta. */
export async function reservarPorApi(
  semilla: Semilla,
  inicio: string,
  nombre: string,
  telefono = '+5491155556666',
): Promise<{ status: number; cuerpo: { turno_id: number; codigo_gestion: string; estado: string } }> {
  const r = await fetch(`${API}/api/public/turnos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nombre, telefono, tratamiento_id: semilla.limpiezaId, profesional_id: semilla.profesionalId, inicio }),
  });
  return { status: r.status, cuerpo: (await r.json()) as { turno_id: number; codigo_gestion: string; estado: string } };
}

/** Lleva al paciente desde "Confirmar turno" hasta la pantalla de pago de la seña. */
export async function reservarHastaLaSena(page: Page, dia: string, hhmm: string, nombre = NOMBRE): Promise<void> {
  await llegarAlPaso3(page, dia, hhmm);
  await completarContacto(page, TELEFONO, nombre);
  await page.getByRole('button', { name: 'Confirmar turno' }).click();
  await expect(page.getByRole('heading', { name: 'Pagá la seña para confirmar tu turno' })).toBeVisible();
}
