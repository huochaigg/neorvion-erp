import path from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const rootDir = fileURLToPath(new URL('.', import.meta.url));
const knowledgeOrigin = 'http://localhost:8017';

const publicBase = process.env.VITE_PUBLIC_BASE || '/';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'absolute-dev-origin',
      transformIndexHtml(html) {
        return html
          .replaceAll('src="/', `src="${knowledgeOrigin}/`)
          .replaceAll('href="/', `href="${knowledgeOrigin}/`)
          .replaceAll('from "/', `from "${knowledgeOrigin}/`);
      },
    },
  ],
  base: publicBase,
  resolve: {
    alias: {
      '@': path.resolve(rootDir, 'src'),
    },
  },
  css: {
    modules: {
      localsConvention: 'camelCaseOnly',
    },
  },
  server: {
    host: '0.0.0.0',
    port: 8017,
    strictPort: true,
    origin: knowledgeOrigin,
    cors: {
      origin: true,
      credentials: true,
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4175,
    cors: true,
    headers: {
      'Access-Control-Allow-Origin': '*',
    },
  },
});
