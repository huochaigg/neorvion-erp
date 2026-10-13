import { sanitizeMicroHrefAfterTenantChange, safeHostPathAfterTenantChange } from '@neorvion/shared';
import { MICRO_APPS } from '@/micro/apps';
import { getLastMicroHref, setLastMicroHref } from '@/micro/last-location';

/** 切租户后把已保存的子应用详情/编辑路由换成模块安全首页，未激活的子应用下次进入也不会恢复旧页。 */
export function resetUnsafeMicroLastLocations() {
  for (const app of MICRO_APPS) {
    const current = getLastMicroHref(app.name);
    if (!current) {
      continue;
    }
    const next = sanitizeMicroHrefAfterTenantChange(app.name, app.basename, app.defaultPath, current);
    if (next !== current) {
      setLastMicroHref(app.name, next);
    }
  }
}

export function hostPathToResetAfterTenantChange(hostPathname: string): string | null {
  return safeHostPathAfterTenantChange(
    hostPathname,
    MICRO_APPS.map((app) => ({
      name: app.name,
      basename: app.basename,
      defaultPath: app.defaultPath,
    })),
  );
}
