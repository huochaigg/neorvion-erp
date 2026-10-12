import { ERP_DEFAULT_PATH, safePathAfterTenantChange } from '@neorvion/shared';
import { pageAllowsAccess } from './access';
import { matchRoute } from './match';
import type { AppRoute } from './types';

export interface RouteTab {
  key: string;
  path: string;
  title: string;
  closable: boolean;
  tenantScoped: boolean;
}

export interface TabsSnapshot {
  tenantId: number | null;
  tabs: RouteTab[];
  activeKey: string;
}

/** 预留上限：超出后关掉最早的非固定、非当前 Tab。 */
export const MAX_TABS = 20;

export const DASHBOARD_TAB_PATH = ERP_DEFAULT_PATH;

export function createPinnedDashboardTab(): RouteTab {
  return {
    key: DASHBOARD_TAB_PATH,
    path: DASHBOARD_TAB_PATH,
    title: '工作台',
    closable: false,
    tenantScoped: false,
  };
}

export function createInitialTabsState(tenantId: number | null = null): TabsSnapshot {
  const pinned = createPinnedDashboardTab();
  return {
    tenantId,
    tabs: [pinned],
    activeKey: pinned.key,
  };
}

/** 列表分页等 query 不参与 Tab 身份；详情 ID 在 pathname 里，会形成不同 Tab。 */
export function normalizeTabPath(pathname: string, search = ''): string {
  void search;
  const withoutQuery = pathname.split('?')[0] ?? pathname;
  if (withoutQuery.length > 1 && withoutQuery.endsWith('/')) {
    return withoutQuery.slice(0, -1);
  }
  return withoutQuery || '/';
}

export function isTabEligiblePath(pathname: string, routes: AppRoute[]): boolean {
  const path = normalizeTabPath(pathname);
  const match = matchRoute(routes, path);
  if (!match) {
    return false;
  }
  if (match.route.redirect && !match.route.component) {
    return false;
  }
  return Boolean(match.route.component);
}

export function tabFromPath(pathname: string, routes: AppRoute[]): RouteTab | null {
  const path = normalizeTabPath(pathname);
  if (!isTabEligiblePath(path, routes)) {
    return null;
  }
  const match = matchRoute(routes, path);
  if (!match) {
    return null;
  }
  const pinned = path === DASHBOARD_TAB_PATH;
  return {
    key: path,
    path,
    title: match.route.title,
    closable: !pinned,
    tenantScoped: !pinned,
  };
}

function ensurePinned(tabs: RouteTab[]): RouteTab[] {
  if (tabs.some((item) => item.key === DASHBOARD_TAB_PATH)) {
    return tabs;
  }
  return [createPinnedDashboardTab(), ...tabs];
}

export function enforceMaxTabs(tabs: RouteTab[], activeKey: string, maxTabs = MAX_TABS): RouteTab[] {
  const next = ensurePinned([...tabs]);
  while (next.length > maxTabs) {
    const index = next.findIndex((item) => item.closable && item.key !== activeKey);
    if (index < 0) {
      break;
    }
    next.splice(index, 1);
  }
  return next;
}

export function ensureTab(state: TabsSnapshot, pathname: string, routes: AppRoute[]): TabsSnapshot {
  const incoming = tabFromPath(pathname, routes);
  if (!incoming) {
    return state;
  }
  const existing = state.tabs.find((item) => item.key === incoming.key);
  const tabs = existing
    ? state.tabs.map((item) =>
        item.key === incoming.key ? { ...item, path: incoming.path, closable: incoming.closable } : item,
      )
    : [...state.tabs, incoming];
  return {
    ...state,
    tabs: enforceMaxTabs(ensurePinned(tabs), incoming.key),
    activeKey: incoming.key,
  };
}

export function closeTab(state: TabsSnapshot, key: string): TabsSnapshot {
  const index = state.tabs.findIndex((item) => item.key === key);
  const target = state.tabs[index];
  if (!target?.closable) {
    return state;
  }
  const tabs = ensurePinned(state.tabs.filter((item) => item.key !== key));
  if (state.activeKey !== key) {
    return { ...state, tabs };
  }
  const left = tabs[index - 1];
  const right = tabs[index];
  return {
    ...state,
    tabs,
    activeKey: left?.key ?? right?.key ?? DASHBOARD_TAB_PATH,
  };
}

export function closeOtherTabs(state: TabsSnapshot, key?: string): TabsSnapshot {
  const keepKey = key ?? state.activeKey;
  const tabs = ensurePinned(
    state.tabs.filter((item) => item.key === DASHBOARD_TAB_PATH || item.key === keepKey),
  );
  const activeKey = tabs.some((item) => item.key === keepKey) ? keepKey : DASHBOARD_TAB_PATH;
  return { ...state, tabs, activeKey };
}

export function closeTabsToTheRight(state: TabsSnapshot, key: string): TabsSnapshot {
  const index = state.tabs.findIndex((item) => item.key === key);
  if (index < 0) {
    return state;
  }
  const tabs = ensurePinned(state.tabs.filter((item, itemIndex) => itemIndex <= index || !item.closable));
  const activeKey = tabs.some((item) => item.key === state.activeKey)
    ? state.activeKey
    : (tabs[tabs.length - 1]?.key ?? DASHBOARD_TAB_PATH);
  return { ...state, tabs, activeKey };
}

export function closeAllTabs(state: TabsSnapshot): TabsSnapshot {
  return {
    ...state,
    tabs: [createPinnedDashboardTab()],
    activeKey: DASHBOARD_TAB_PATH,
  };
}

export function setTabTitle(state: TabsSnapshot, pathname: string, title: string): TabsSnapshot {
  const path = normalizeTabPath(pathname);
  if (!title.trim()) {
    return state;
  }
  let changed = false;
  const tabs = state.tabs.map((item) => {
    if (item.key !== path && item.path !== path) {
      return item;
    }
    if (item.title === title) {
      return item;
    }
    changed = true;
    return { ...item, title };
  });
  return changed ? { ...state, tabs } : state;
}

export function resetTabsForTenant(tenantId: number | null): TabsSnapshot {
  return createInitialTabsState(tenantId);
}

export function pruneInvalidTabs(
  state: TabsSnapshot,
  routes: AppRoute[],
  permissions?: readonly string[],
): TabsSnapshot {
  const tabs = ensurePinned(
    state.tabs.filter((item) => {
      if (item.key === DASHBOARD_TAB_PATH) {
        return true;
      }
      if (!isTabEligiblePath(item.path, routes)) {
        return false;
      }
      if (permissions === undefined) {
        return true;
      }
      return pageAllowsAccess(matchRoute(routes, item.path), permissions);
    }),
  );
  const activeKey = tabs.some((item) => item.key === state.activeKey)
    ? state.activeKey
    : (tabs[tabs.length - 1]?.key ?? DASHBOARD_TAB_PATH);
  return { ...state, tabs, activeKey };
}

/** 拖拽结束后用新顺序重排；工作台永远回到第一位。 */
export function reorderTabs(state: TabsSnapshot, orderedKeys: string[]): TabsSnapshot {
  const byKey = new Map(state.tabs.map((item) => [item.key, item]));
  const next: RouteTab[] = [byKey.get(DASHBOARD_TAB_PATH) ?? createPinnedDashboardTab()];
  const seen = new Set<string>([DASHBOARD_TAB_PATH]);
  for (const key of orderedKeys) {
    if (seen.has(key)) {
      continue;
    }
    const tab = byKey.get(key);
    if (!tab) {
      continue;
    }
    next.push(tab);
    seen.add(key);
  }
  for (const tab of state.tabs) {
    if (!seen.has(tab.key)) {
      next.push(tab);
      seen.add(tab.key);
    }
  }
  return { ...state, tabs: next };
}

export function shouldSkipTabAfterTenantChange(pathname: string, routeList: AppRoute[]): boolean {
  const path = normalizeTabPath(pathname);
  if (safePathAfterTenantChange(path) != null) {
    return true;
  }
  const match = matchRoute(routeList, path);
  return Boolean(match?.route.path.split('/').some((part) => part.startsWith(':')));
}
