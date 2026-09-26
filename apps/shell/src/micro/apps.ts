import { ERP_APP_NAME, ERP_BASENAME, ERP_DEFAULT_PATH, childPathFromHost } from '@neorvion/shared';
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
    alive: true,
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

export function stripMicroSyncParam(search: string, name: string): string {
  if (!search || search === '?') {
    return '';
  }
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  if (!params.has(name)) {
    return search.startsWith('?') ? search : `?${search}`;
  }
  params.delete(name);
  const next = params.toString();
  return next ? `?${next}` : '';
}

/** 主应用 /erp/dashboard → 子应用 http://localhost:8016/dashboard，禁止拼出 /erp/erp。 */
export function buildMicroAppUrl(
  app: MicroAppDefinition,
  pathname: string,
  search = '',
  hash = '',
): string {
  const entry = app.getEntry();
  const childPath = childPathFromHost(pathname, app.basename, app.defaultPath);
  return `${entry}${childPath}${stripMicroSyncParam(search, app.name)}${hash}`;
}

export function getMicroAppEntryHref(app: MicroAppDefinition, lastHref?: string | null): string {
  if (lastHref && (lastHref === app.basename || lastHref.startsWith(`${app.basename}/`))) {
    return lastHref;
  }
  return `${app.basename}${app.defaultPath}`;
}
