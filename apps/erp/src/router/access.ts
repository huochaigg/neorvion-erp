import { canAccess, type PermissionMode } from '@neorvion/shared';
import type { AppRoute, MatchedRoute } from './types';

export interface RoutePermissionRequirement {
  codes: string[];
  mode: PermissionMode;
}

export function resolveRouteRequirement(route: AppRoute): RoutePermissionRequirement {
  if (route.permissions?.length) {
    return { codes: route.permissions, mode: route.permissionMode ?? 'all' };
  }
  if (route.permission) {
    return { codes: [route.permission], mode: route.permissionMode ?? 'all' };
  }
  return { codes: [], mode: 'all' };
}

/** 叶子未声明权限时，沿最近的已声明祖先继承；整条链都未声明则放行。 */
export function resolvePageRequirement(match: MatchedRoute | undefined): RoutePermissionRequirement {
  if (!match) {
    return { codes: [], mode: 'all' };
  }
  const chain = [match.route, ...[...match.parents].reverse()];
  for (const item of chain) {
    const current = resolveRouteRequirement(item);
    if (current.codes.length) {
      return current;
    }
  }
  return { codes: [], mode: 'all' };
}

export function routeMatchesPermissions(route: AppRoute, codes: readonly string[]): boolean {
  const required = resolveRouteRequirement(route);
  return canAccess(codes, required.codes, required.mode);
}

export function pageAllowsAccess(match: MatchedRoute | undefined, codes: readonly string[]): boolean {
  const required = resolvePageRequirement(match);
  return canAccess(codes, required.codes, required.mode);
}

export type PageAccessState = 'loading' | 'allow' | 'forbidden';

export function resolvePageAccessState(options: {
  tenantId: number | null;
  isLoading: boolean;
  match: MatchedRoute | undefined;
  permissions: readonly string[];
}): PageAccessState {
  if (options.tenantId != null && options.isLoading) {
    return 'loading';
  }
  if (!pageAllowsAccess(options.match, options.permissions)) {
    return 'forbidden';
  }
  return 'allow';
}

/**
 * 菜单可见性：有可见子项的分组保留；空分组隐藏。
 * 不删除 React Router 路由，页面访问另走 PermissionGuard。
 */
export function filterMenuRoutes(routes: AppRoute[], codes: readonly string[]): AppRoute[] {
  const visible: AppRoute[] = [];
  for (const route of routes) {
    if (route.showInMenu === false) {
      continue;
    }
    const children = filterMenuRoutes(route.children ?? [], codes);
    if (children.length > 0) {
      visible.push({ ...route, children });
      continue;
    }
    const groupingOnly = Boolean(route.redirect && !route.component);
    if (groupingOnly) {
      continue;
    }
    if (route.component && routeMatchesPermissions(route, codes)) {
      visible.push({ ...route, children: undefined });
    }
  }
  return visible;
}
