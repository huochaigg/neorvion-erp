import { ERP_APP_NAME, ERP_BASENAME } from '@neorvion/shared';
import { setupApp } from '@/micro/wujie-host';

let initialized = false;

export function setupMicroApps() {
  if (initialized) return;

  setupApp({
    name: ERP_APP_NAME,
    exec: true,
    sync: true,
    alive: false,
    fiber: false,
    attrs: {
      src: '/wujie-empty.html',
    },
    prefix: { [ERP_APP_NAME]: ERP_BASENAME },
    plugins: [
      {
        cssLoader(code: string) {
          return code.replaceAll(':root', ':host');
        },
      },
    ],
  });

  initialized = true;
}