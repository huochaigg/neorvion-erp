import type { AppRoute, MatchedRoute } from './types';

export function walkRoutes(routes: AppRoute[], visit: (route: AppRoute, parents: AppRoute[]) => void) {
  const walk = (items: AppRoute[], parents: AppRoute[]) => {
    for (const item of [...items].sort((left, right) => (left.sort ?? 0) - (right.sort ?? 0))) {
      visit(item, parents);
      if (item.children?.length) {
        walk(item.children, [...parents, item]);
      }
    }
  };
  walk(routes, []);
}

export function flattenRoutes(routes: AppRoute[]): AppRoute[] {
  const result: AppRoute[] = [];
  walkRoutes(routes, (route) => {
    result.push(route);
  });
  return result;
}

export function matchPattern(pattern: string, pathname: string): boolean {
  const patternParts = pattern.split('/').filter(Boolean);
  const pathParts = pathname.split('/').filter(Boolean);
  if (patternParts.length !== pathParts.length) {
    return false;
  }
  return patternParts.every((part, index) => part.startsWith(':') || part === pathParts[index]);
}

function staticScore(pattern: string): number {
  return pattern.split('/').filter((part) => part && !part.startsWith(':')).length;
}

export function matchRoute(routes: AppRoute[], pathname: string): MatchedRoute | undefined {
  const hits: MatchedRoute[] = [];
  walkRoutes(routes, (route, parents) => {
    if (matchPattern(route.path, pathname)) {
      hits.push({ route, parents });
    }
  });
  hits.sort((left, right) => staticScore(right.route.path) - staticScore(left.route.path));
  return hits[0];
}

export function getSelectedMenuKey(match: MatchedRoute | undefined): string | undefined {
  if (!match) {
    return undefined;
  }
  if (match.route.activeMenu) {
    return match.route.activeMenu;
  }
  if (match.route.showInMenu === false) {
    const parent = [...match.parents].reverse().find((item) => item.showInMenu !== false);
    return parent?.path;
  }
  return match.route.path;
}

export function getOpenKeysForPath(routes: AppRoute[], pathname: string): string[] {
  const match = matchRoute(routes, pathname);
  if (!match) {
    return [];
  }
  const keys = match.parents.filter((item) => item.showInMenu !== false).map((item) => item.path);
  const selected = getSelectedMenuKey(match);
  if (selected && selected !== match.route.path) {
    const activeMatch = matchRoute(routes, selected);
    if (activeMatch) {
      for (const parent of activeMatch.parents) {
        if (parent.showInMenu !== false && !keys.includes(parent.path)) {
          keys.push(parent.path);
        }
      }
    }
  }
  return keys;
}

export function getBreadcrumb(routes: AppRoute[], pathname: string): AppRoute[] {
  const match = matchRoute(routes, pathname);
  if (!match) {
    return [];
  }
  return [...match.parents, match.route];
}

export function resolveNavigatePath(routes: AppRoute[], key: string): string {
  const match = flattenRoutes(routes).find((item) => item.path === key);
  return match?.redirect ?? key;
}
