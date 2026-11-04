import { defineConfig } from '@playwright/test';

/**
 * E2E contra el backend REAL (Docker Compose, PostgreSQL real). Sin mocks.
 * Requisitos: `docker compose up -d postgres backend` con las migraciones aplicadas
 * (ver README raíz) y `JWT_SECRET_KEY` exportada para el contenedor del backend.
 *
 * El navegador corre en una zona horaria distinta de la clínica (Tokyo vs -03:00)
 * para probar que la UI muestra siempre hora de la clínica.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:5173',
    viewport: { width: 360, height: 800 }, // R3: 360px es criterio de aceptación
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2,
    locale: 'es-AR',
    timezoneId: 'Asia/Tokyo',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium-360', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env['CI'],
    timeout: 60_000,
  },
});
