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

export const ALIAS_TRANSFERENCIA = 'clinica.demo.sintetica';
export const CBU_TRANSFERENCIA = '0000003100000000000043';
export const TITULAR_TRANSFERENCIA = 'Clínica Demo Sintética';
export const EMAIL_RECEPCION = 'recepcion.e2e@turnos.test';
export const CLAVE_RECEPCION = 'password-e2e-sintetica';
/** bcrypt de CLAVE_RECEPCION (dato sintético; solo existe en la base local de pruebas). */
const HASH_CLAVE_RECEPCION = '$2b$10$ZBiMWnRW1aHUdN52SR5N5ubI2xDReJneSI4OZemXmYq5jYjOBFb4G';

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
      "SELECT 1 FROM information_schema.columns WHERE table_name = 'turno' AND column_name = 'en_espera_vence_en'",
    );
    if (migrada.rowCount === 0) {
      throw new Error('La base no tiene las migraciones al día: corré `alembic upgrade head` desde backend/.');
    }
    await c.query(
      'TRUNCATE pago_sena, turno, disponibilidad, profesional, sillon, tratamiento, usuario_rol, usuario, rol RESTART IDENTITY CASCADE',
    );
    // Seña (C-06): datos bancarios SINTÉTICOS para la transferencia y un usuario de recepción de prueba.
    await c.query(
      `UPDATE configuracion_sena SET sena_porcentaje = 30.00, medios_habilitados = '{mercadopago,transferencia}',
         expiracion_mp_minutos = 30, expiracion_transferencia_minutos = 1440,
         transferencia_alias = $1, transferencia_cbu = $2, transferencia_titular = $3`,
      [ALIAS_TRANSFERENCIA, CBU_TRANSFERENCIA, TITULAR_TRANSFERENCIA],
    );
    const rol = await c.query<{ id: string }>("INSERT INTO rol (nombre) VALUES ('recepcion') RETURNING id");
    const usuario = await c.query<{ id: string }>(
      'INSERT INTO usuario (email, nombre_completo, hashed_password) VALUES ($1, $2, $3) RETURNING id',
      [EMAIL_RECEPCION, 'Recepción Sintética', HASH_CLAVE_RECEPCION],
    );
    await c.query('INSERT INTO usuario_rol (usuario_id, rol_id) VALUES ($1, $2)', [usuario.rows[0]?.id, rol.rows[0]?.id]);
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
  await ejecutar((c) => c.query('TRUNCATE pago_sena, turno RESTART IDENTITY CASCADE'));
}

export interface TurnoGuardado {
  readonly id: number;
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
      'SELECT id::int AS id, estado, contacto_nombre, contacto_telefono, inicio, fin, codigo_gestion FROM turno ORDER BY inicio, id',
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

export interface PagoGuardado {
  readonly id: number;
  readonly turno_id: number;
  readonly medio: string;
  readonly estado: string;
  readonly monto: string;
  readonly referencia_externa: string;
  readonly mp_payment_id: string | null;
}

export async function leerPagos(): Promise<PagoGuardado[]> {
  return ejecutar(async (c) => {
    const r = await c.query<PagoGuardado>(
      'SELECT id::int AS id, turno_id::int AS turno_id, medio, estado, monto::text AS monto, referencia_externa, mp_payment_id FROM pago_sena ORDER BY id',
    );
    return r.rows;
  });
}

/** Simula que pasó el tiempo: el vencimiento de la pre-reserva queda `minutos` minutos en el pasado. */
export async function vencerPreReserva(turnoId: number, minutos = 1): Promise<void> {
  await ejecutar((c) =>
    c.query("UPDATE turno SET en_espera_vence_en = now() - make_interval(mins => $1) WHERE id = $2 AND estado = 'en_espera'", [
      minutos,
      turnoId,
    ]),
  );
}

/** Siembra un turno YA `reservado` (bloquea agenda) en el horario dado, como si su seña estuviera acreditada. */
export async function sembrarTurnoReservado(semilla: Semilla, inicioIso: string, minutos = 30): Promise<void> {
  await ejecutar((c) =>
    c.query(
      `INSERT INTO turno (profesional_id, sillon_id, tratamiento_id, inicio, fin, estado)
       VALUES ($1, $2, $3, $4::timestamptz, $4::timestamptz + make_interval(mins => $5), 'reservado')`,
      [semilla.profesionalId, semilla.sillonId, semilla.limpiezaId, inicioIso, minutos],
    ),
  );
}
