import { defineConfig } from 'vitest/config';
import viteConfig from './vite.config.ts';

export default defineConfig({
  ...viteConfig,
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', '../../packages/shared/src/**/*.test.ts'],
  },
});
