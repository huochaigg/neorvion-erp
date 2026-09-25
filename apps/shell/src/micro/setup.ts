import { ERP_APP_NAME, ERP_BASENAME } from '@neorvion/shared';
import { setupApp } from '@/micro/wujie-host';

/** 只注册子应用配置，不在主应用首页启动 ERP。 */
export function setupMicroApps() {
  setupApp({
    name: ERP_APP_NAME,
    exec: true,
    sync: false,
    fiber: false,
    prefix: { [ERP_APP_NAME]: ERP_BASENAME },
    plugins: [
      {
        // Tailwind v4 主题变量写在 :root 上，映射到 :host 以免污染主应用。
        cssLoader(code: string) {
          return code.replaceAll(':root', ':host');
        },
      },
    ],
  });
}
