import pg from 'pg';

/** Conexión a la base LOCAL de pruebas (Docker Compose, host 5433). */
const CONEXION = {
  host: process.env['E2E_PGHOST'] ?? 'localhost',
  port: Number(process.env['E2E_PGPORT'] ?? 5433),
  user: process.env['E2E_PGUSER'] ?? 'turnos',
  password: process.env['E2E_PGPASSWORD'] ?? 'turnos',
  database: process.env['E2E_PGDATABASE'] ?? 'turnos',
};

const HOSTS_LOCALES = new Set(['localhost', '127.0.0.1', '::1']);

/** Barrera: este módulo trunca tablas, así que SOLO opera sobre una base local. */
function exigirBaseLocal(): void {
  if (!HOSTS_LOCALES.has(CONEXION.host)) {
    throw new Error(
      `E2E se niega a truncar tablas en "${CONEXION.host}": solo se permite la base local de Docker Compose.`,
    );
  }
}

export interface Semilla {
  readonly profesionalId: number;
  readonly sillonId: number;
  readonly limpiezaId: number;
  readonly consultaId: number;
}

async function conectar(): Promise<pg.Client> {
  exigirBaseLocal();
  const cliente = new pg.Client(CONEXION);
  await cliente.connect();
  return cliente;
}

async function ejecutar<T>(accion: (cliente: pg.Client) => Promise<T>): Promise<T> {
  const cliente = await conectar();
  try {
    return await accion(cliente);
  } finally {
    await cliente.end();
  }
}

/**
 * Siembra datos 100 % sintéticos (R19) y deterministas: un profesional con franja
 * 09:00-17:00 TODOS los días de la semana (así el test no depende de que hoy sea hábil),
 * un sillón y dos tratamientos.
 */
export async function sembrar(): Promise<Semilla> {
  return ejecutar(async (c) => {
    const migrada = await c.query(
      "SELECT 1 FROM information_schema.columns WHERE table_name = 'turno' AND column_name = 'codigo_gestion'",
    );
    if (migrada.rowCount === 0) {
      throw new Error('La base no tiene las migraciones al día: corré `alembic upgrade head` desde backend/.');
    }
    await c.query('TRUNCATE turno, disponibilidad, profesional, sillon, tratamiento RESTART IDENTITY CASCADE');
    const p = await c.query<{ id: string }>(
      "INSERT INTO profesional (nombre, matricula, especialidad) VALUES ('Dra. Sintética', 'E2E-001', 'Odontología general') RETURNING id",
    );
    const s = await c.query<{ id: string }>("INSERT INTO sillon (nombre, estado) VALUES ('Sillón E2E', 'activo') RETURNING id");
    const t1 = await c.query<{ id: string }>(
      "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('Limpieza dental', 30, 15000.00) RETURNING id",
    );
    const t2 = await c.query<{ id: string }>(
      "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('Consulta de control', 20, 8000.00) RETURNING id",
    );
    const profesionalId = Number(p.rows[0]?.id);
    const sillonId = Number(s.rows[0]?.id);
    for (let dia = 0; dia <= 6; dia += 1) {
      await c.query(
        "INSERT INTO disponibilidad (profesional_id, dia_semana, hora_inicio, hora_fin, sillon_defecto_id) VALUES ($1, $2, '09:00', '17:00', $3)",
        [profesionalId, dia, sillonId],
      );
    }
    return {
      profesionalId,
      sillonId,
      limpiezaId: Number(t1.rows[0]?.id),
      consultaId: Number(t2.rows[0]?.id),
    };
  });
}

export async function vaciarTurnos(): Promise<void> {
  await ejecutar((c) => c.query('TRUNCATE turno RESTART IDENTITY CASCADE'));
}

export interface TurnoGuardado {
  readonly estado: string;
  readonly contacto_nombre: string;
  readonly contacto_telefono: string;
  readonly inicio: Date;
  readonly fin: Date;
  readonly codigo_gestion: string;
}

export async function leerTurnos(): Promise<TurnoGuardado[]> {
  return ejecutar(async (c) => {
    const r = await c.query<TurnoGuardado>(
      'SELECT estado, contacto_nombre, contacto_telefono, inicio, fin, codigo_gestion FROM turno ORDER BY inicio',
    );
    return r.rows;
  });
}

export async function contarPacientes(): Promise<number> {
  return ejecutar(async (c) => {
    const r = await c.query<{ n: string }>('SELECT count(*) AS n FROM paciente');
    return Number(r.rows[0]?.n);
  });
}
