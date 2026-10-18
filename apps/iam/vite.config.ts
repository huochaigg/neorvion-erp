import path from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const rootDir = fileURLToPath(new URL('.', import.meta.url));
const iamOrigin = 'http://localhost:8018';

const publicBase = process.env.VITE_PUBLIC_BASE || '/';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 开发保持 /。生产同域部署到 /iam/ 时设 VITE_PUBLIC_BASE=/iam/
  base: publicBase,
  resolve: {
    alias: {
      '@': path.resolve(rootDir, 'src'),
    },
  },
  optimizeDeps: {
    include: ['dayjs', 'dayjs/locale/zh-cn', 'dayjs/plugin/customParseFormat'],
  },
  css: {
    modules: {
      localsConvention: 'camelCaseOnly',
    },
  },
  server: {
    host: '0.0.0.0',
    port: 8018,
    strictPort: true,
    origin: iamOrigin,
    cors: true,
    headers: {
      'Access-Control-Allow-Origin': '*',
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4176,
    cors: true,
    headers: {
      'Access-Control-Allow-Origin': '*',
    },
  },
});
