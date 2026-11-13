import { defineConfig } from '@playwright/test';

/**
 * E2E del panel contra el backend REAL (Docker Compose, PostgreSQL real). Sin mocks.
 * Requisitos: `docker compose up -d postgres backend` con las migraciones aplicadas (ver README raíz), el backend con
 * APP_ENV=e2e y `JWT_SECRET_KEY` exportada para el contenedor.
 *
 * El navegador corre en una zona horaria distinta de la clínica (Tokyo vs -03:00) para probar que la UI muestra siempre
 * hora de la clínica. El panel se abre en `http://localhost:5174` y Vite reenvía `/api` al backend: es mismo origen,
 * así que no hace falta CORS y la cookie de refresh (HttpOnly, Secure, SameSite=Strict) viaja sin `credentials`.
 */
const comun = {
  browserName: 'chromium' as const,
  locale: 'es-AR',
  timezoneId: 'Asia/Tokyo',
};

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:5174',
    trace: 'retain-on-failure',
  },
  projects: [
    // R3: 360px es criterio de aceptación.
    { name: 'chromium-360', use: { ...comun, viewport: { width: 360, height: 800 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } },
    { name: 'chromium-1280', use: { ...comun, viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5174',
    reuseExistingServer: !process.env['CI'],
    timeout: 60_000,
  },
});
