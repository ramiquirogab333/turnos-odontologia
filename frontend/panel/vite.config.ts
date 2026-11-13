import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Panel (C-08, D10): puerto 5174 y proxy /api = mismo origen, sin CORS ni credentials. El backend corre en Docker Compose (localhost:8000). El proxy evita CORS:
// el navegador siempre habla con el mismo origen (R17: sin configuración extra en el backend).
const backend = process.env['VITE_BACKEND_URL'] ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: { port: 5174, strictPort: true, proxy: { '/api': { target: backend, changeOrigin: true } } },
  preview: { port: 5174, strictPort: true, proxy: { '/api': { target: backend, changeOrigin: true } } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globalSetup: ['./src/test/global-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
});
