import { expect, test, type Page, type Response } from '@playwright/test';
import {
  API,
  NOMBRE,
  TELEFONO,
  abrirPaciente,
  completarContacto,
  diaObjetivo,
  elegirHorario,
  elegirTratamiento,
  inicioClinica,
  llegarAlPaso3,
  verificarPantalla,
} from './ayudas';
import { contarPacientes, leerTurnos, sembrar, sembrarTurnoReservado, vaciarTurnos, type Semilla } from './datos';
import { etiquetaDiaLarga } from '../src/lib/tiempo';

let semilla: Semilla;

test.beforeAll(async () => {
  const salud = await fetch(`${API}/api/health`);
  expect(salud.ok, 'el backend debe estar arriba (docker compose up -d postgres backend)').toBe(true);
  semilla = await sembrar();
});

test.beforeEach(async ({ page }) => {
  await vaciarTurnos();
  await page.goto('/');
});

const esPostTurnos = (r: Response): boolean =>
  r.url().endsWith('/api/public/turnos') && r.request().method() === 'POST';

test.describe('R2: la carga inicial no hace cascadas', () => {
  test('tratamientos y profesionales salen juntos y los horarios recién al elegir', async ({ page }) => {
    // El beforeEach ya cargó la app: se sale de esa página para que sus pedidos en vuelo
    // no se mezclen con los de la carga que se observa acá.
    await page.goto('about:blank');

    const consultasDisponibilidad: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/api/public/disponibilidad')) consultasDisponibilidad.push(r.url());
    });

    // Ningún pedido del catálogo recibe respuesta hasta que salieron los dos: si uno
    // esperara al otro (cascada), el catálogo nunca se mostraría y el test fallaría.
    const vistos = new Set<string>();
    let liberar: () => void = () => undefined;
    const ambosSalieron = new Promise<void>((resolve) => {
      liberar = resolve;
    });
    await page.route(/\/api\/public\/(tratamientos|profesionales)$/, async (route) => {
      vistos.add(new URL(route.request().url()).pathname);
      if (vistos.size === 2) liberar();
      await ambosSalieron;
      await route.continue();
    });

    await page.goto('/');
    await expect(page.getByRole('radio', { name: /limpieza dental/i })).toBeVisible();
    expect(consultasDisponibilidad).toHaveLength(0);

    await elegirTratamiento(page);
    // Se elige el día objetivo (siempre futuro): "hoy" puede no tener ya el horario de las 10:00.
    await page.getByRole('button', { name: etiquetaDiaLarga(diaObjetivo()), exact: true }).click();
    await expect(page.getByRole('button', { name: '10:00', exact: true }).first()).toBeVisible();
    expect(consultasDisponibilidad).toHaveLength(1); // una sola consulta para todo el rango
  });
});

test.describe('3.1 reserva exitosa (happy path) a 360px', () => {
  test('Carlos Sintético reserva Limpieza de 30 min y obtiene 201, fin exacto y código de gestión', async ({ page }) => {
    const dia = diaObjetivo();
    await verificarPantalla(page, 'carga inicial');
    await elegirTratamiento(page);
    await expect(page.getByRole('heading', { name: 'Elegí día y horario' })).toBeVisible();
    await elegirHorario(page, dia, '10:00');
    await expect(page.getByText(/hora de Buenos Aires/).first()).toBeVisible();
    await completarContacto(page);
    await verificarPantalla(page, 'paso 3');

    const [respuesta] = await Promise.all([
      page.waitForResponse(esPostTurnos),
      page.getByRole('button', { name: 'Confirmar turno' }).click(),
    ]);
    expect(respuesta.status()).toBe(201);
    const cuerpo = (await respuesta.json()) as {
      codigo_gestion: string;
      inicio: string;
      fin: string;
      estado: string;
      sena: { monto: string; medios_habilitados: string[] };
    };
    expect(cuerpo.estado).toBe('en_espera'); // P7: ya no nace reservado
    expect(cuerpo.sena.monto).toBe('4500.00'); // 30 % de 15000.00
    expect(new Date(cuerpo.fin).getTime() - new Date(cuerpo.inicio).getTime()).toBe(30 * 60_000);

    await expect(page.getByRole('heading', { name: 'Pagá la seña para confirmar tu turno' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Turno reservado' })).toHaveCount(0);
    await expect(page.getByText(/10:00 a 10:30/)).toBeVisible(); // hora de la clínica aunque el navegador esté en Tokyo
    await expect(page.getByText(/4\.500,00/)).toBeVisible();
    await expect(page.getByText(/^Tu reserva vence a las \d{2}:\d{2}$/)).toBeVisible();
    await expect(page.getByText('Tu turno no está confirmado hasta acreditar la seña.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pagar con Mercado Pago' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pagar por transferencia' })).toBeVisible();
    await verificarPantalla(page, 'pantalla de seña');

    const turnos = await leerTurnos();
    expect(turnos).toHaveLength(1);
    expect(turnos[0]).toMatchObject({ estado: 'en_espera', contacto_nombre: NOMBRE, contacto_telefono: TELEFONO });
    expect(turnos[0]?.codigo_gestion).toBe(cuerpo.codigo_gestion);
    expect(turnos[0]?.inicio.toISOString()).toBe(new Date(inicioClinica(dia, '10:00')).toISOString());
    expect((turnos[0]?.fin.getTime() ?? 0) - (turnos[0]?.inicio.getTime() ?? 0)).toBe(30 * 60_000);
    expect(await contarPacientes()).toBe(0); // RN-TU-06: sin registro de paciente
  });

  test('la tira de días desliza por dentro: la página no', async ({ page }) => {
    await elegirTratamiento(page);
    await expect(page.getByRole('button', { name: etiquetaDiaLarga(diaObjetivo()), exact: true })).toBeAttached();
    const { tira, pagina } = await page.evaluate(() => {
      const t = document.querySelector('.dias');
      return {
        tira: t ? t.scrollWidth > t.clientWidth : false,
        pagina: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    });
    expect(tira).toBe(true);
    expect(pagina).toBe(false);
  });
});

test.describe('3.2 horario ocupado: alternativas y carrera', () => {
  test('el slot se ocupa entre que el paciente lo ve y confirma: 409, alternativas y reserva de una de ellas', async ({ page }) => {
    const dia = diaObjetivo();
    await llegarAlPaso3(page, dia, '10:00');
    await completarContacto(page);

    // Mientras tanto, otra persona acredita su seña en ese horario: queda `reservado` y bloquea la agenda.
    await sembrarTurnoReservado(semilla, inicioClinica(dia, '10:00'));

    const [respuesta] = await Promise.all([
      page.waitForResponse(esPostTurnos),
      page.getByRole('button', { name: 'Confirmar turno' }).click(),
    ]);
    expect(respuesta.status()).toBe(409);

    const aviso = page.getByRole('alert');
    await expect(aviso).toContainText('ya fue reservado');
    const alternativas = aviso.getByRole('button', { name: /,\s\d{2}:\d{2}$/ });
    await expect(alternativas.first()).toBeVisible();
    expect(await alternativas.count()).toBeGreaterThan(1);
    await verificarPantalla(page, 'conflicto con alternativas');
    await expect(page.getByLabel('Nombre completo')).toHaveValue(NOMBRE); // no se pierden los datos

    // La primera alternativa es el horario libre contiguo.
    await aviso.getByRole('button', { name: new RegExp(`${etiquetaDiaLarga(dia)}, 10:30`) }).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByText(/Cambiamos tu horario/)).toBeVisible();

    const [segunda] = await Promise.all([
      page.waitForResponse(esPostTurnos),
      page.getByRole('button', { name: 'Confirmar turno' }).click(),
    ]);
    expect(segunda.status()).toBe(201);
    await expect(page.getByRole('heading', { name: 'Pagá la seña para confirmar tu turno' })).toBeVisible();
    await expect(page.getByText(/10:30 a 11:00/)).toBeVisible();

    const turnos = await leerTurnos();
    expect(turnos.map((t) => [t.contacto_nombre, t.estado])).toEqual([
      [null, 'reservado'],
      [NOMBRE, 'en_espera'],
    ]);
    expect(turnos[1]?.inicio.toISOString()).toBe(new Date(inicioClinica(dia, '10:30')).toISOString());
  });

  test('dos pacientes confirman el mismo horario al mismo tiempo: ambos obtienen 201 en_espera (la competencia es al acreditar)', async ({ browser }) => {
    const dia = diaObjetivo();
    const paginas: Page[] = [await abrirPaciente(browser), await abrirPaciente(browser)];
    try {
      for (const p of paginas) {
        await llegarAlPaso3(p, dia, '11:00');
        await completarContacto(p);
      }
      const estados = await Promise.all(
        paginas.map(async (p) => {
          const [r] = await Promise.all([
            p.waitForResponse(esPostTurnos),
            p.getByRole('button', { name: 'Confirmar turno' }).click(),
          ]);
          return r.status();
        }),
      );
      expect(estados).toEqual([201, 201]); // P7 / R8: un en_espera no bloquea agenda
      for (const p of paginas) {
        await expect(p.getByRole('heading', { name: 'Pagá la seña para confirmar tu turno' })).toBeVisible();
      }
      const turnos = await leerTurnos();
      expect(turnos.map((t) => t.estado)).toEqual(['en_espera', 'en_espera']);
    } finally {
      await Promise.all(paginas.map((p) => p.context().close()));
    }
  });
});

test.describe('3.3 teléfono inválido en el último horario de atención', () => {
  test('el formulario explica cómo corregirlo, no envía nada y el horario sigue libre', async ({ page }) => {
    const dia = diaObjetivo();
    const posts: string[] = [];
    page.on('request', (r) => {
      if (r.method() === 'POST') posts.push(r.url());
    });

    await llegarAlPaso3(page, dia, '16:30'); // 16:30 + 30 min = 17:00, cierre de la franja
    await completarContacto(page, '1234');
    await page.getByRole('button', { name: 'Confirmar turno' }).click();

    const campo = page.getByLabel('Teléfono (WhatsApp)');
    await expect(campo).toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByText(/código de país, por ejemplo \+5491144445555/)).toBeVisible();
    await verificarPantalla(page, 'paso 3 con error');
    expect(posts).toEqual([]);
    expect(await leerTurnos()).toHaveLength(0);
    expect(await contarPacientes()).toBe(0);

    // Corregido, el mismo horario sigue disponible y se reserva.
    await campo.fill('+54 9 11 4444-5555');
    const [r] = await Promise.all([page.waitForResponse(esPostTurnos), page.getByRole('button', { name: 'Confirmar turno' }).click()]);
    expect(r.status()).toBe(201);
    await expect(page.getByRole('heading', { name: 'Pagá la seña para confirmar tu turno' })).toBeVisible();
    await expect(page.getByText(/16:30 a 17:00/)).toBeVisible();
  });

  test('si un cliente desactualizado enviara un teléfono inválido, el 422 real del servidor se muestra en el campo', async ({ page }) => {
    const dia = diaObjetivo();
    // Se altera SOLO el teléfono de la petición real (no se simula la respuesta): el backend responde de verdad.
    await page.route('**/api/public/turnos', async (route) => {
      const original = route.request().postDataJSON() as Record<string, unknown>;
      await route.continue({ postData: JSON.stringify({ ...original, telefono: '1234' }) });
    });

    await llegarAlPaso3(page, dia, '16:30');
    await completarContacto(page);
    const [r] = await Promise.all([page.waitForResponse(esPostTurnos), page.getByRole('button', { name: 'Confirmar turno' }).click()]);

    expect(r.status()).toBe(422);
    expect(Array.isArray(((await r.json()) as { detail: unknown }).detail)).toBe(true); // forma de lista de Pydantic
    await expect(page.getByLabel('Teléfono (WhatsApp)')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByText(/código de país, por ejemplo \+5491144445555/)).toBeVisible();
    expect(await leerTurnos()).toHaveLength(0); // sin bloqueo de agenda ni registros huérfanos
    expect(await contarPacientes()).toBe(0);
  });
});
