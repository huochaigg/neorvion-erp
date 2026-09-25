import { setupApp } from 'wujie';
import { MICRO_APPS } from '@/micro/apps';

export function setupMicroApps() {
  for (const app of MICRO_APPS) {
    setupApp({
      name: app.name,
      exec: false,
      sync: true,
      alive: app.alive ?? false,
      fiber: app.fiber ?? false,
      degrade: app.degrade ?? false,
      prefix: { [app.name]: app.basename },
      plugins: app.plugins,
    });
  }
}
