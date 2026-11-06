import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { cargarCatalogo } from './lib/api';

const TRATAMIENTOS = [
  { id: 1, nombre: 'Limpieza', duracion_minutos: 30, precio_base: '1000.00' },
  { id: 2, nombre: 'Consulta', duracion_minutos: 20, precio_base: '800.00' },
];
const PROFESIONALES = [{ id: 7, nombre: 'Dra. Sintética', especialidad: 'General' }];

// 13:00Z = 10:00 en Buenos Aires. El runner corre en Asia/Tokyo (22:00): si la UI
// usara la zona del navegador mostraría 22:00.
const SLOTS = [
  { inicio: '2026-11-16T10:00:00-03:00', fin: '2026-11-16T10:30:00-03:00', profesional_id: 7, sillon_id: 1 },
  { inicio: '2026-11-16T10:30:00-03:00', fin: '2026-11-16T11:00:00-03:00', profesional_id: 7, sillon_id: 1 },
  { inicio: '2026-11-17T09:00:00-03:00', fin: '2026-11-17T09:30:00-03:00', profesional_id: 7, sillon_id: 1 },
];
const CREADA = {
  turno_id: 5,
  codigo_gestion: 'ABCD2345',
  estado: 'reservado',
  inicio: SLOTS[0]?.inicio ?? '',
  fin: SLOTS[0]?.fin ?? '',
};

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function cuerpoDe(init: RequestInit | undefined): unknown {
  return typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : null;
}

type Manejador = (url: URL, init?: RequestInit) => Response | Promise<Response>;

function servidor(sobre: { turnos?: Manejador; disponibilidad?: Manejador } = {}) {
  const llamadas: { url: URL; init: RequestInit | undefined }[] = [];
  const mock = vi.fn((entrada: string, init?: RequestInit) => {
    const url = new URL(entrada, 'http://clinica.test');
    llamadas.push({ url, init });
    if (url.pathname === '/api/public/tratamientos') return Promise.resolve(json(TRATAMIENTOS));
    if (url.pathname === '/api/public/profesionales') return Promise.resolve(json(PROFESIONALES));
    if (url.pathname === '/api/public/disponibilidad')
      return Promise.resolve(sobre.disponibilidad ? sobre.disponibilidad(url, init) : json({ slots: SLOTS }));
    if (url.pathname === '/api/public/turnos')
      return Promise.resolve(sobre.turnos ? sobre.turnos(url, init) : json(CREADA, 201));
    return Promise.resolve(json({}, 404));
  });
  vi.stubGlobal('fetch', mock);
  return {
    llamadas,
    posts: () => llamadas.filter((l) => l.init?.method === 'POST'),
    pedidos: (ruta: string) => llamadas.filter((l) => l.url.pathname === ruta),
  };
}

/** Cada gesto va dentro de un act asíncrono: los componentes que usan `use()` suspenden al reaccionar. */
function nuevoUsuario() {
  const base = userEvent.setup();
  return {
    click: (el: Element) => act(() => base.click(el)),
    type: (el: Element, texto: string) => act(() => base.type(el, texto)),
    clear: (el: Element) => act(() => base.clear(el)),
  };
}
type Usuario = ReturnType<typeof nuevoUsuario>;

async function montar(): Promise<void> {
  // `use()` suspende: React 19 pide montar dentro de un act asíncrono.
  await act(() => {
    render(<App inicial={cargarCatalogo()} recargar={cargarCatalogo} />);
    return Promise.resolve();
  });
}

async function hastaElPaso3(usuario: Usuario) {
  await usuario.click(await screen.findByRole('radio', { name: /limpieza/i }));
  await usuario.click(screen.getByRole('button', { name: 'Ver horarios' }));
  await usuario.click(await screen.findByRole('button', { name: '10:00' }));
  await usuario.click(screen.getByRole('button', { name: 'Continuar' }));
}

async function completar(usuario: Usuario, telefono = '+5491144445555') {
  await usuario.type(screen.getByLabelText(/nombre completo/i), 'Carlos Sintético');
  await usuario.type(screen.getByLabelText(/teléfono/i), telefono);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('carga inicial (R2)', () => {
  it('muestra el estado de carga (Suspense) y lanza tratamientos y profesionales a la vez', async () => {
    let liberar: () => void = () => undefined;
    const bloqueo = new Promise<void>((res) => {
      liberar = res;
    });
    const s = servidor();
    const base = globalThis.fetch;
    const espiado = vi.fn((entrada: string, init?: RequestInit) => bloqueo.then(() => base(entrada, init)));
    vi.stubGlobal('fetch', espiado);

    await montar();

    expect(screen.getByRole('status')).toHaveTextContent(/cargando/i);
    expect(espiado).toHaveBeenCalledTimes(2); // ambas salieron sin esperar a la otra
    liberar();
    expect(await screen.findByRole('radio', { name: /limpieza/i })).toBeInTheDocument();
    expect(s.pedidos('/api/public/disponibilidad')).toHaveLength(0); // los horarios no se piden hasta elegir
  });

  it('si la carga falla ofrece reintentar y recupera el catálogo', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({}, 500))));
    const usuario = nuevoUsuario();
    await montar();
    expect(await screen.findByRole('alert')).toHaveTextContent(/no pudimos cargar/i);

    servidor();
    await usuario.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByRole('radio', { name: /limpieza/i })).toBeInTheDocument();
  });
});

describe('paso 1: tratamiento', () => {
  it('"Ver horarios" queda deshabilitado hasta elegir tratamiento; con un solo profesional se asigna solo', async () => {
    servidor();
    const usuario = nuevoUsuario();
    await montar();
    const boton = await screen.findByRole('button', { name: 'Ver horarios' });
    expect(boton).toBeDisabled();
    expect(screen.getByText(/te atiende dra\. sintética/i)).toBeInTheDocument();
    await usuario.click(screen.getByRole('radio', { name: /consulta/i }));
    expect(boton).toBeEnabled();
  });

  it('muestra duración y precio orientativo de cada tratamiento', async () => {
    servidor();
    await montar();
    const limpieza = await screen.findByRole('radio', { name: /limpieza/i });
    expect(limpieza).toHaveAccessibleName(/30 min/);
    expect(limpieza).toHaveAccessibleName(/1\.000/);
  });

  it('sin tratamientos invita a volver más tarde', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((u: string) => Promise.resolve(json(u.includes('profesionales') ? PROFESIONALES : []))),
    );
    await montar();
    expect(await screen.findByText(/todavía no tiene horarios/i)).toBeInTheDocument();
  });
});

describe('paso 2: horarios', () => {
  it('pide los horarios en UNA sola petición de 14 días y los muestra en hora de la clínica', async () => {
    const s = servidor();
    const usuario = nuevoUsuario();
    await montar();
    await usuario.click(await screen.findByRole('radio', { name: /limpieza/i }));
    await usuario.click(screen.getByRole('button', { name: 'Ver horarios' }));

    expect(await screen.findByRole('button', { name: '10:00' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '10:30' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '22:00' })).not.toBeInTheDocument(); // zona del navegador

    const [consulta] = s.pedidos('/api/public/disponibilidad');
    expect(consulta?.url.searchParams.get('profesional_id')).toBe('7');
    expect(consulta?.url.searchParams.get('tratamiento_id')).toBe('1');
    const desde = Date.parse(`${consulta?.url.searchParams.get('desde') ?? ''}T12:00:00Z`);
    const hasta = Date.parse(`${consulta?.url.searchParams.get('hasta') ?? ''}T12:00:00Z`);
    expect((hasta - desde) / 86_400_000).toBe(14);

    // cambiar de día no dispara más peticiones (sin fetch por día)
    await usuario.click(screen.getByRole('button', { name: 'martes 17 de noviembre' }));
    expect(screen.getByRole('button', { name: '09:00' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '10:00' })).not.toBeInTheDocument();
    expect(s.pedidos('/api/public/disponibilidad')).toHaveLength(1);
  });

  it('"Continuar" se habilita recién al elegir un horario', async () => {
    servidor();
    const usuario = nuevoUsuario();
    await montar();
    await usuario.click(await screen.findByRole('radio', { name: /limpieza/i }));
    await usuario.click(screen.getByRole('button', { name: 'Ver horarios' }));
    const continuar = await screen.findByRole('button', { name: 'Continuar' });
    expect(continuar).toBeDisabled();
    await usuario.click(screen.getByRole('button', { name: '10:30' }));
    expect(continuar).toBeEnabled();
  });

  it('sin horarios libres da una salida clara', async () => {
    servidor({ disponibilidad: () => json({ slots: [] }) });
    const usuario = nuevoUsuario();
    await montar();
    await usuario.click(await screen.findByRole('radio', { name: /limpieza/i }));
    await usuario.click(screen.getByRole('button', { name: 'Ver horarios' }));
    expect(await screen.findByText(/no hay horarios libres/i)).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: /cambiar tratamiento/i }));
    expect(screen.getByRole('radio', { name: /limpieza/i })).toBeChecked();
  });

  it('si falla la consulta de horarios permite reintentar', async () => {
    let intentos = 0;
    servidor({
      disponibilidad: () => {
        intentos += 1;
        return intentos === 1 ? json({}, 503) : json({ slots: SLOTS });
      },
    });
    const usuario = nuevoUsuario();
    await montar();
    await usuario.click(await screen.findByRole('radio', { name: /limpieza/i }));
    await usuario.click(screen.getByRole('button', { name: 'Ver horarios' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/horarios/i);
    await usuario.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByRole('button', { name: '10:00' })).toBeInTheDocument();
  });
});

describe('paso 3: contacto y confirmación', () => {
  it('reserva feliz: envía nombre y teléfono, y muestra código y horario de la clínica', async () => {
    const s = servidor();
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));

    expect(await screen.findByRole('heading', { name: /turno reservado/i })).toBeInTheDocument();
    expect(screen.getByText('ABCD2345')).toBeInTheDocument();
    expect(screen.getByText(/10:00 a 10:30/)).toBeInTheDocument();
    const [post] = s.posts();
    expect(cuerpoDe(post?.init)).toEqual({
      nombre: 'Carlos Sintético',
      telefono: '+5491144445555',
      tratamiento_id: 1,
      profesional_id: 7,
      inicio: '2026-11-16T10:00:00-03:00',
    });
  });

  it('teléfono inválido: explica cómo corregirlo, no envía nada y conserva el nombre', async () => {
    const s = servidor();
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario, '1234');
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));

    const campo = screen.getByLabelText(/teléfono/i);
    expect(campo).toBeInvalid();
    expect(campo).toHaveAccessibleDescription(/código de país.*\+5491144445555/);
    expect(s.posts()).toHaveLength(0);
    expect(screen.getByLabelText(/nombre completo/i)).toHaveValue('Carlos Sintético');

    // corregir y reintentar funciona
    await usuario.clear(campo);
    await usuario.type(campo, '+54 9 11 4444 5555');
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));
    expect(await screen.findByRole('heading', { name: /turno reservado/i })).toBeInTheDocument();
    expect(s.posts()).toHaveLength(1);
  });

  it('nombre vacío también se corrige antes de enviar', async () => {
    const s = servidor();
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await usuario.type(screen.getByLabelText(/teléfono/i), '+5491144445555');
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));
    expect(screen.getByLabelText(/nombre completo/i)).toHaveAccessibleDescription(/ingresá tu nombre/i);
    expect(s.posts()).toHaveLength(0);
  });

  it('422 de lista del servidor se muestra en el campo del teléfono', async () => {
    servidor({
      turnos: () =>
        json({ detail: [{ type: 'value_error', loc: ['body', 'telefono'], msg: 'Value error, x', input: '+1' }] }, 422),
    });
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));
    expect(await screen.findByLabelText(/teléfono/i)).toHaveAccessibleDescription(/código de país/i);
    expect(screen.queryByRole('heading', { name: /turno reservado/i })).not.toBeInTheDocument();
  });

  it('422 de texto (fuera de horario) ofrece elegir otro horario', async () => {
    servidor({ turnos: () => json({ detail: 'El horario solicitado está fuera de la disponibilidad del profesional' }, 422) });
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/otro horario/i);
    await usuario.click(screen.getByRole('button', { name: 'Elegir otro horario' }));
    expect(await screen.findByRole('button', { name: '10:30' })).toBeInTheDocument();
  });

  it('409: muestra las alternativas en hora de la clínica y reserva la que elija el paciente', async () => {
    let intento = 0;
    const alternativas = [
      { inicio: '2026-11-16T10:30:00-03:00', fin: '2026-11-16T11:00:00-03:00', sillon_id: 1 },
      { inicio: '2026-11-17T09:00:00-03:00', fin: '2026-11-17T09:30:00-03:00', sillon_id: 1 },
    ];
    const s = servidor({
      turnos: () => {
        intento += 1;
        if (intento === 1) return json({ detail: 'Solape por profesional', motivo: 'profesional', alternativas }, 409);
        return json({ ...CREADA, inicio: alternativas[0]?.inicio, fin: alternativas[0]?.fin }, 201);
      },
    });
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));

    const aviso = await screen.findByRole('alert');
    expect(aviso).toHaveTextContent(/ya fue reservado/i);
    expect(within(aviso).getByRole('button', { name: /lunes 16 de noviembre, 10:30/i })).toBeInTheDocument();
    expect(within(aviso).getByRole('button', { name: /martes 17 de noviembre, 09:00/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/nombre completo/i)).toHaveValue('Carlos Sintético'); // datos conservados

    await usuario.click(within(aviso).getByRole('button', { name: /lunes 16 de noviembre, 10:30/i }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));

    expect(await screen.findByRole('heading', { name: /turno reservado/i })).toBeInTheDocument();
    expect(screen.getByText(/10:30 a 11:00/)).toBeInTheDocument();
    const [, segundo] = s.posts();
    expect(cuerpoDe(segundo?.init)).toMatchObject({ inicio: '2026-11-16T10:30:00-03:00' });
  });

  it('409 sin alternativas lleva de vuelta a elegir horario', async () => {
    servidor({ turnos: () => json({ detail: 'Solape por sillon', motivo: 'sillon', alternativas: [] }, 409) });
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/no quedan horarios cercanos/i);
    await usuario.click(screen.getByRole('button', { name: 'Elegir otro horario' }));
    expect(await screen.findByRole('button', { name: '10:30' })).toBeInTheDocument();
  });

  it('evita el doble envío mientras la reserva está en curso', async () => {
    let resolver: (r: Response) => void = () => undefined;
    const s = servidor({
      turnos: () =>
        new Promise<Response>((res) => {
          resolver = res;
        }),
    });
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    const boton = screen.getByRole('button', { name: 'Confirmar turno' });
    await usuario.click(boton);
    expect(screen.getByRole('button', { name: /reservando/i })).toBeDisabled();
    await usuario.click(screen.getByRole('button', { name: /reservando/i }));
    expect(s.posts()).toHaveLength(1);
    resolver(json(CREADA, 201));
    expect(await screen.findByRole('heading', { name: /turno reservado/i })).toBeInTheDocument();
  });
});


const SENA = {
  monto: '300.00',
  vence_en: '2026-11-16T09:30:00-03:00',
  medios_habilitados: ['mercadopago', 'transferencia'],
  texto_politica_reembolso: 'Si cancelás con 24 h o más de anticipación, te devolvemos la seña. Si no asistís, la seña no se devuelve.',
};
const EN_ESPERA = { ...CREADA, estado: 'en_espera', sena: SENA };
const ESTADO_RESERVADO = {
  turno_id: 5,
  estado_turno: 'reservado',
  estado_pago: 'acreditado',
  vencida: false,
  medios_habilitados: ['mercadopago'],
  pago_id: 11,
  medio: 'mercadopago',
  monto: '300.00',
  vence_en: null,
  texto_politica_reembolso: SENA.texto_politica_reembolso,
  referencia_externa: 'abc123abc123abc123abc123abc123ab',
  checkout_url: null,
  alias: null,
  cbu: null,
  titular: null,
  referencia_concepto: null,
  inicio: '2026-11-16T10:00:00-03:00',
  fin: '2026-11-16T10:30:00-03:00',
  tratamiento_nombre: 'Limpieza',
  profesional_nombre: 'Dra. Sintética',
};

describe('seña (C-06): del paso 3 al pago', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
    localStorage.clear();
  });

  it('una reserva en_espera lleva a la pantalla de pago y NO a "Turno reservado"', async () => {
    servidor({ turnos: () => json(EN_ESPERA, 201) });
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));

    expect(await screen.findByRole('heading', { name: 'Pagá la seña para confirmar tu turno' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /turno reservado/i })).not.toBeInTheDocument();
    expect(screen.getByText(/300,00/)).toBeInTheDocument();
    expect(screen.getByText('Tu reserva vence a las 09:30')).toBeInTheDocument();
  });

  it('una reserva ya reservada (precio 0) va directo a "Turno reservado"', async () => {
    servidor({ turnos: () => json({ ...CREADA, sena: null }, 201) });
    const usuario = nuevoUsuario();
    await montar();
    await hastaElPaso3(usuario);
    await completar(usuario);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar turno' }));
    expect(await screen.findByRole('heading', { name: /turno reservado/i })).toBeInTheDocument();
  });

  it('al volver del checkout (?pago=retorno) retoma la espera con el código guardado y llega a "Turno reservado"', async () => {
    window.history.replaceState(null, '', '/?pago=retorno&turno=5');
    localStorage.setItem('sena-pendiente-v2', JSON.stringify({ v: 2, turnoId: 5, codigoGestion: 'ABCD2345', expira: Date.now() + 3_600_000 }));
    const mock = vi.fn((entrada: string, init?: RequestInit) => {
      const url = new URL(entrada, 'http://clinica.test');
      if (url.pathname === '/api/public/turnos/5/sena') {
        expect(new Headers(init?.headers).get('X-Codigo-Gestion')).toBe('ABCD2345');
        return Promise.resolve(json(ESTADO_RESERVADO));
      }
      return Promise.resolve(json([]));
    });
    vi.stubGlobal('fetch', mock);
    await montar();

    expect(await screen.findByRole('heading', { name: 'Turno reservado' })).toBeInTheDocument();
    expect(screen.getByText('ABCD2345')).toBeInTheDocument();
    expect(mock.mock.calls.filter(([u]) => u.includes('/sena'))).toHaveLength(1);
  });

  it('al volver del checkout sin datos guardados avisa y permite reservar de nuevo', async () => {
    window.history.replaceState(null, '', '/?pago=retorno&turno=5');
    servidor();
    const usuario = nuevoUsuario();
    await montar();
    expect(await screen.findByRole('heading', { name: /no encontramos tu reserva/i })).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Reservar un turno' }));
    expect(await screen.findByRole('radio', { name: /limpieza/i })).toBeInTheDocument();
    expect(window.location.search).toBe('');
  });

  it('el turno guardado de otro turno no se usa para el retorno', async () => {
    window.history.replaceState(null, '', '/?pago=retorno&turno=9');
    localStorage.setItem('sena-pendiente-v2', JSON.stringify({ v: 2, turnoId: 5, codigoGestion: 'ABCD2345', expira: Date.now() + 3_600_000 }));
    servidor();
    await montar();
    expect(await screen.findByRole('heading', { name: /no encontramos tu reserva/i })).toBeInTheDocument();
  });
});

describe('App: ruta /gestionar (C-07)', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('muestra la gestión del turno y no pide el catálogo de reserva', async () => {
    window.history.replaceState(null, '', '/gestionar#CODIGO-SINTETICO-1');
    const mock = vi.fn((entrada: string) =>
      Promise.resolve(entrada === '/api/public/gestion' ? json({ detail: 'No encontramos un turno con ese código' }, 404) : json({}, 500)),
    );
    vi.stubGlobal('fetch', mock);
    await montar();

    expect(await screen.findByText(/No encontramos un turno con ese código/)).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /limpieza/i })).not.toBeInTheDocument();
    expect(mock.mock.calls.filter(([u]) => u === '/api/public/gestion')).toHaveLength(1);
  });

  it('en la ruta raíz sigue mostrando la reserva', async () => {
    servidor();
    await montar();
    expect(await screen.findByRole('radio', { name: /limpieza/i })).toBeInTheDocument();
  });
});
