// Carrera concurrente: dos POST /api/turnos simultáneos sobre el mismo slot
// (fetch desde el runner, sin UI: backend-only, D10) => exactamente un 201 + un 409.
// Padres FK vía INSERTs SQL directos (sus CRUDs llegan en C-04).
// @ts-check
const { test, expect } = require('@playwright/test');
const { Client } = require('pg');

const DB = {
  host: process.env.E2E_PGHOST || 'localhost',
  port: Number(process.env.E2E_PGPORT || 5433),
  user: process.env.E2E_PGUSER || 'turnos',
  password: process.env.E2E_PGPASSWORD || 'turnos',
  database: process.env.E2E_PGDATABASE || 'turnos',
};

function futuroISO(minutos = 180) {
  return new Date(Date.now() + minutos * 60_000).toISOString();
}

test.describe('carrera por el mismo slot', () => {
  let ids;

  test.beforeAll(async () => {
    const pg = new Client(DB);
    await pg.connect();
    await pg.query('TRUNCATE turno, profesional, sillon, tratamiento RESTART IDENTITY CASCADE');
    const p = await pg.query(
      "INSERT INTO profesional (nombre, matricula, especialidad) VALUES ('E2E P', 'E2E-1', 'G') RETURNING id",
    );
    const s = await pg.query("INSERT INTO sillon (nombre, estado) VALUES ('E2E S', 'activo') RETURNING id");
    const t = await pg.query(
      "INSERT INTO tratamiento (nombre, duracion_minutos, precio_base) VALUES ('E2E T', 30, 100.00) RETURNING id",
    );
    await pg.end();
    ids = {
      profesional_id: p.rows[0].id,
      sillon_id: s.rows[0].id,
      tratamiento_id: t.rows[0].id,
    };
    // Backend levantado con la migración 001 aplicada.
    const health = await (await fetch(`${process.env.E2E_BASE_URL || 'http://localhost:8000'}/api/health`)).json();
    expect(health.status).toBe('ok');
  });

  test.afterEach(async () => {
    const pg = new Client(DB);
    await pg.connect();
    await pg.query('TRUNCATE turno RESTART IDENTITY CASCADE');
    await pg.end();
  });

  for (let i = 1; i <= 5; i++) {
    test(`intento ${i}: exactamente un 201 y un 409`, async ({ baseURL }) => {
      const payload = { ...ids, inicio: futuroISO(240 + i) };
      const post = () =>
        fetch(`${baseURL}/api/turnos`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(payload),
        });
      const [r1, r2] = await Promise.all([post(), post()]);
      expect([r1.status, r2.status].sort()).toEqual([201, 409]);
      const perdedor = r1.status === 409 ? r1 : r2;
      const cuerpo = await perdedor.json();
      expect(['profesional', 'sillon']).toContain(cuerpo.motivo);
      expect(r1.status).not.toBe(500);
      expect(r2.status).not.toBe(500);
    });
  }
});
