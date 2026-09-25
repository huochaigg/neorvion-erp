import { ERP_APP_NAME, ERP_BASENAME, ERP_DEFAULT_PATH } from '@neorvion/shared';
import type { plugin } from 'wujie';
import { tailwindV4ShadowCssPlugin } from '@/micro/css-plugins';

export interface MicroAppDefinition {
  name: string;
  basename: string;
  defaultPath: string;
  getEntry: () => string;
  fiber?: boolean;
  degrade?: boolean;
  alive?: boolean;
  plugins?: plugin[];
}

export const MICRO_APPS: MicroAppDefinition[] = [
  {
    name: ERP_APP_NAME,
    basename: ERP_BASENAME,
    defaultPath: ERP_DEFAULT_PATH,
    getEntry: () => (import.meta.env.VITE_ERP_ENTRY || 'http://localhost:8016').replace(/\/$/, ''),
    fiber: false,
    degrade: false,
    alive: false,
    plugins: [tailwindV4ShadowCssPlugin()],
  },
];

export function getMicroApp(name: string): MicroAppDefinition {
  const app = MICRO_APPS.find((item) => item.name === name);
  if (!app) {
    throw new Error(`未注册的微应用：${name}`);
  }
  return app;
}

/** 主应用 /erp/dashboard → 子应用 http://localhost:8016/dashboard，禁止拼出 /erp/erp。 */
export function buildMicroAppUrl(app: MicroAppDefinition, pathname: string): string {
  const entry = app.getEntry();
  if (pathname === app.basename || pathname === `${app.basename}/`) {
    return `${entry}${app.defaultPath}`;
  }
  if (pathname.startsWith(`${app.basename}/`)) {
    return `${entry}${pathname.slice(app.basename.length)}`;
  }
  return `${entry}${app.defaultPath}`;
}
