import { ERP_APP_NAME, KNOWLEDGE_APP_NAME } from '../constants/app';
import { childPathFromHost, hostPathFromChild } from '../micro/location';
import { safePathAfterTenantChange } from './erp-route';
import { safeKnowledgePathAfterTenantChange } from './knowledge-route';

export function safeChildPathAfterTenantChange(appName: string, childPathname: string): string | null {
  if (appName === ERP_APP_NAME) {
    return safePathAfterTenantChange(childPathname);
  }
  if (appName === KNOWLEDGE_APP_NAME) {
    return safeKnowledgePathAfterTenantChange(childPathname);
  }
  return null;
}

/** 把已保存的子应用 href 中的旧租户详情页换成模块安全首页。 */
export function sanitizeMicroHrefAfterTenantChange(
  appName: string,
  basename: string,
  defaultPath: string,
  href: string | null,
): string {
  const fallback = `${basename}${defaultPath}`;
  if (!href) {
    return fallback;
  }
  const pathname = href.split(/[?#]/, 1)[0] ?? href;
  if (pathname !== basename && !pathname.startsWith(`${basename}/`)) {
    return fallback;
  }
  const child = childPathFromHost(pathname, basename, defaultPath);
  const safeChild = safeChildPathAfterTenantChange(appName, child);
  if (!safeChild) {
    return href;
  }
  return hostPathFromChild(basename, safeChild);
}

export function safeHostPathAfterTenantChange(
  hostPathname: string,
  apps: ReadonlyArray<{ name: string; basename: string; defaultPath: string }>,
): string | null {
  for (const app of apps) {
    if (hostPathname !== app.basename && !hostPathname.startsWith(`${app.basename}/`)) {
      continue;
    }
    const child = childPathFromHost(hostPathname, app.basename, app.defaultPath);
    const safeChild = safeChildPathAfterTenantChange(app.name, child);
    return safeChild ? hostPathFromChild(app.basename, safeChild) : null;
  }
  return null;
}
