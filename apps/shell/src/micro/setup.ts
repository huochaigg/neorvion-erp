import { setupApp } from 'wujie';
import { MICRO_APPS } from '@/micro/apps';

export function setupMicroApps() {
  for (const app of MICRO_APPS) {
    setupApp({
      name: app.name,
      exec: false,
      // 关闭原生 ?{name}= 同步，改由 Shell pathname 双向同步，避免和 React Router 抢 history.state。
      sync: false,
      alive: app.alive ?? false,
      fiber: app.fiber ?? false,
      degrade: app.degrade ?? false,
      prefix: { [app.name]: app.basename },
      plugins: app.plugins,
    });
  }
}
