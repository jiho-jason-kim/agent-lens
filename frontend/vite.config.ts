import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  // Keep browser requests on one origin during local development.
  server: { port: 5173, strictPort: true, proxy: { '/evaluations': 'http://127.0.0.1:8000', '/workflows': 'http://127.0.0.1:8000', '/runs': 'http://127.0.0.1:8000', '/scenarios': 'http://127.0.0.1:8000' } },
  preview: { proxy: { '/evaluations': 'http://127.0.0.1:8000', '/workflows': 'http://127.0.0.1:8000', '/runs': 'http://127.0.0.1:8000', '/scenarios': 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts' },
});
