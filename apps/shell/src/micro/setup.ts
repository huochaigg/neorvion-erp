import { ERP_APP_NAME } from '@neorvion/shared';
import { setupApp } from '@/micro/wujie-host';

export function setupMicroApps() {
  const erpEntry = (import.meta.env.VITE_ERP_ENTRY || 'http://localhost:8016').replace(/\/$/, '');
  setupApp({
    name: ERP_APP_NAME,
    url: `${erpEntry}/erp/dashboard`,
    exec: true,
    sync: true,
    fiber: false,
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
