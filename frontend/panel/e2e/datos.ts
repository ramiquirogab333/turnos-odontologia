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

export const EMAIL_RECEPCION = 'recepcion.e2e@turnos.test';
export const EMAIL_ODONTOLOGA = 'dra.ficticia.e2e@turnos.test';
export const CLAVE = 'password-e2e-sintetica';
/** bcrypt de CLAVE (dato sintético; solo existe en la base local de pruebas). */
const HASH_CLAVE = '$2b$10$ZBiMWnRW1aHUdN52SR5N5ubI2xDReJneSI4OZemXmYq5jYjOBFb4G';

export interface Semilla {
  readonly profesionalId: number;
  readonly profesional2Id: number;
  readonly sillon1Id: number;
  readonly sillon2Id: number;
  readonly limpiezaId: number;
}

async function conectar(): Promise<pg.Client> {
  exigirBaseLocal();
  const cliente = new pg.Client(CONEXION);
  await cliente.connect();
  return cliente;
}

/**
 * TRUNCATE ... CASCADE toma bloqueos exclusivos de muchas tablas; si justo corre un ciclo del worker (recordatorios o
 * Google Calendar) Postgres puede abortar uno de los dos con `deadlock detected` (40P01). Es ruido del arnés de
 * pruebas, no de la app: se reintenta unas pocas veces.
 */
async function truncarConReintento(c: pg.Client, consulta: string): Promise<void> {
  for (let intento = 1; ; intento += 1) {
    try {
      await c.query(consulta);
      return;
    } catch (error) {
      const codigo = (error as { code?: string }).code;
      if (codigo !== '40P01' || intento >= 5) throw error;
      await new Promise((resolver) => setTimeout(resolver, 500 * intento));
    }
  }
}

async function ejecutar<T>(accion: (cliente: pg.Client) => Promise<T>): Promise<T> {
  const cliente = await conectar();
  try {
    return await accion(cliente);
  } finally {
    await cliente.end();
  }
}

async function insertar(c: pg.Client, consulta: string, params: unknown[]): Promise<number> {
  const r = await c.query<{ id: string }>(consulta, params);
  return Number(r.rows[0]?.id);
}

/**
 * Siembra datos 100 % sintéticos (R19) y deterministas: dos profesionales con franja 00:00-23:59 TODOS los días (así
 * el test no depende de la hora ni del día en que corre), dos sillones, un tratamiento de 30 minutos, una usuaria de
 * recepción y una odontóloga asociada a la "Dra. Ana Ficticia".
 */
export async function sembrar(): Promise<Semilla> {
  return ejecutar(async (c) => {
    const migrada = await c.query(
      "SELECT 1 FROM information_schema.columns WHERE table_name = 'turno' AND column_name = 'origen'",
    );
    if (migrada.rowCount === 0) {
      throw new Error('La base no tiene las migraciones al día (falta turno.origen): corré `alembic upgrade head`.');
    }
    await truncarConReintento(
      c,
      'TRUNCATE token_blacklist, cierre_caja_linea, cierre_caja, pago_presupuesto, presupuesto_linea, presupuesto, ficha, odontograma_registro, paciente, pago_sena_aprobacion, pago_sena, turno, disponibilidad, profesional, sillon, tratamiento, usuario_rol, usuario, rol, registro_auditoria RESTART IDENTITY CASCADE',
    );
    const ana = await insertar(
      c,
      "INSERT INTO profesional (nombre, matricula, especialidad) VALUES ('Dra. Ana Ficticia', 'E2E-001', 'Odontología general') RETURNING id",
      [],
    );
    const bruno = await insertar(
      c,
      "INSERT INTO profesional (nombre, matricula, especialidad) VALUES ('Dr. Bruno Ejemplo', 'E2E-002', 'Odontología general') RETURNING id",
      [],
    );
    const s1 = await insertar(c, "INSERT INTO sillon (nombre, estado) VALUES ('Sillón 1', 'activo') RETURNING id", []);
    const s2 = await insertar(c, "INSERT INTO sillon (nombre, estado) VALUES ('Sillón 2', 'activo') RETURNING id", []);
    const limpieza = await insertar(
      c,
      "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('Limpieza dental', 30, 15000.00) RETURNING id",
      [],
    );
    for (const profesional of [ana, bruno]) {
      for (let dia = 0; dia <= 6; dia += 1) {
        await c.query(
          "INSERT INTO disponibilidad (profesional_id, dia_semana, hora_inicio, hora_fin, sillon_defecto_id) VALUES ($1, $2, '00:00', '23:59', $3)",
          [profesional, dia, s1],
        );
      }
    }
    const rolRecepcion = await insertar(c, "INSERT INTO rol (nombre) VALUES ('recepcion') RETURNING id", []);
    const rolOdontologo = await insertar(c, "INSERT INTO rol (nombre) VALUES ('odontologo') RETURNING id", []);
    const recepcion = await insertar(
      c,
      'INSERT INTO usuario (email, nombre_completo, hashed_password) VALUES ($1, $2, $3) RETURNING id',
      [EMAIL_RECEPCION, 'Rita Recepción', HASH_CLAVE],
    );
    await c.query('INSERT INTO usuario_rol (usuario_id, rol_id) VALUES ($1, $2)', [recepcion, rolRecepcion]);
    const odontologa = await insertar(
      c,
      'INSERT INTO usuario (email, nombre_completo, hashed_password, profesional_id) VALUES ($1, $2, $3, $4) RETURNING id',
      [EMAIL_ODONTOLOGA, 'Ana Ficticia', HASH_CLAVE, ana],
    );
    await c.query('INSERT INTO usuario_rol (usuario_id, rol_id) VALUES ($1, $2)', [odontologa, rolOdontologo]);
    return { profesionalId: ana, profesional2Id: bruno, sillon1Id: s1, sillon2Id: s2, limpiezaId: limpieza };
  });
}

export interface OpcionesTurno {
  readonly inicio: Date;
  readonly estado?: 'reservado' | 'confirmado' | 'en_espera' | 'atendido' | 'ausente';
  readonly profesional?: 'ana' | 'bruno';
  readonly sillon?: 1 | 2;
  readonly nombre?: string | null;
  readonly origen?: 'web' | 'manual';
  /** Si se indica, crea también la seña con ese estado (monto 4500.00). */
  readonly sena?: 'acreditado' | 'pendiente' | 'a_reembolsar' | 'no_reembolsado';
  /** Cuándo se recibió el dinero (por defecto, ahora). Sirve para sembrar movimientos de un día pasado. */
  readonly acreditadoEn?: Date;
  /** Paciente al que se vincula el turno. */
  readonly pacienteId?: number;
  readonly minutos?: number;
}

/** Siembra un turno con el `inicio` EXACTO pedido. El reloj del servidor no se puede inyectar desde el navegador. */
export async function sembrarTurno(semilla: Semilla, o: OpcionesTurno): Promise<number> {
  const estado = o.estado ?? 'reservado';
  const nombre = o.nombre === undefined ? 'Carlos Sintético' : o.nombre;
  return ejecutar(async (c) => {
    const id = await insertar(
      c,
      `INSERT INTO turno (profesional_id, sillon_id, tratamiento_id, inicio, fin, estado, origen, codigo_gestion,
                          contacto_nombre, contacto_telefono, en_espera_vence_en, paciente_id)
       VALUES ($1, $2, $3, $4::timestamptz, $4::timestamptz + make_interval(mins => $5), $6, $7, $8, $9, $10,
               CASE WHEN $6 = 'en_espera' THEN now() + interval '2 hours' END, $11)
       RETURNING id`,
      [
        o.profesional === 'bruno' ? semilla.profesional2Id : semilla.profesionalId,
        o.sillon === 2 ? semilla.sillon2Id : semilla.sillon1Id,
        semilla.limpiezaId,
        o.inicio.toISOString(),
        o.minutos ?? 30,
        estado,
        o.origen ?? 'web',
        `E2E-CODIGO-${String(Date.now())}-${String(Math.random()).slice(2, 8)}`,
        nombre,
        nombre === null ? null : '+5491144445555',
        o.pacienteId ?? null,
      ],
    );
    if (o.sena !== undefined) {
      await c.query(
        `INSERT INTO pago_sena (turno_id, medio, monto, porcentaje_aplicado, estado, referencia_externa, vence_en, acreditado_en)
         VALUES ($1, 'mercadopago', 4500.00, 30.00, $2, $3, now() + interval '1 day',
                 CASE WHEN $2 <> 'pendiente' THEN COALESCE($4::timestamptz, now()) END)`,
        [id, o.sena, `SENA-E2E-${String(id)}`, o.acreditadoEn?.toISOString() ?? null],
      );
    }
    return id;
  });
}

export interface TurnoGuardado {
  readonly id: number;
  readonly estado: string;
  readonly origen: string;
  readonly contacto_nombre: string | null;
  readonly inicio: Date;
}

export async function leerTurnos(): Promise<TurnoGuardado[]> {
  return ejecutar(async (c) => {
    const r = await c.query<TurnoGuardado>(
      'SELECT id::int AS id, estado, origen, contacto_nombre, inicio FROM turno ORDER BY inicio, id',
    );
    return r.rows;
  });
}

export async function leerEstadoPago(turnoId: number): Promise<string | null> {
  return ejecutar(async (c) => {
    const r = await c.query<{ estado: string }>('SELECT estado FROM pago_sena WHERE turno_id = $1 ORDER BY id DESC LIMIT 1', [
      turnoId,
    ]);
    return r.rows[0]?.estado ?? null;
  });
}

export async function contarPagos(): Promise<number> {
  return ejecutar(async (c) => {
    const r = await c.query<{ n: string }>('SELECT count(*) AS n FROM pago_sena');
    return Number(r.rows[0]?.n);
  });
}

/** Paciente sintético (R19): el DNI es de fantasía y único. */
export async function sembrarPaciente(nombre: string, apellido: string, dni: string): Promise<number> {
  return ejecutar((c) =>
    insertar(
      c,
      "INSERT INTO paciente (nombre, apellido, dni, telefono) VALUES ($1, $2, $3, '+5491144446666') RETURNING id",
      [nombre, apellido, dni],
    ),
  );
}

/** Presupuesto aceptado de un paciente (hace falta uno para cobrarlo por la API). */
export async function sembrarPresupuestoAceptado(pacienteId: number): Promise<number> {
  return ejecutar((c) =>
    insertar(
      c,
      `INSERT INTO presupuesto (paciente_id, estado, subtotal, total_paciente, presentado_en, resuelto_en)
       VALUES ($1, 'aceptado', 20000.00, 20000.00, now(), now()) RETURNING id`,
      [pacienteId],
    ),
  );
}

/** Cambia el estado de un turno sin pasar por la pantalla (para comparar el mismo turno en dos estados). */
export async function cambiarEstadoTurno(turnoId: number, estado: 'reservado' | 'en_espera'): Promise<void> {
  await ejecutar(async (c) => {
    await c.query(
      `UPDATE turno SET estado = $2, en_espera_vence_en = CASE WHEN $2 = 'en_espera' THEN now() + interval '2 hours' END
       WHERE id = $1`,
      [turnoId, estado],
    );
  });
}

export interface CierreGuardado {
  readonly dia: string;
  readonly estado: string;
}

export async function leerCierres(): Promise<CierreGuardado[]> {
  return ejecutar(async (c) => {
    const r = await c.query<CierreGuardado>("SELECT to_char(dia, 'YYYY-MM-DD') AS dia, estado FROM cierre_caja ORDER BY id");
    return r.rows;
  });
}

export interface RecordatorioGuardado {
  readonly turno_id: number;
  readonly estado: string;
  readonly motivo: string | null;
}

/** Recordatorios de la base, en orden de creación (los genera el worker). */
export async function leerRecordatorios(): Promise<RecordatorioGuardado[]> {
  return ejecutar(async (c) => {
    const r = await c.query<RecordatorioGuardado>(
      'SELECT turno_id::int AS turno_id, estado, motivo FROM recordatorio ORDER BY id',
    );
    return r.rows;
  });
}

/** Código de gestión de un turno sembrado (para cancelarlo desde la gestión del paciente). */
export async function leerCodigoGestion(turnoId: number): Promise<string> {
  return ejecutar(async (c) => {
    const r = await c.query<{ codigo_gestion: string }>('SELECT codigo_gestion FROM turno WHERE id = $1', [turnoId]);
    return r.rows[0]?.codigo_gestion ?? '';
  });
}
