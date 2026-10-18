import type { MenuProps } from 'antd';
import { createElement } from 'react';
import { filterMenuRoutes } from './access';
import { ICON_MAP } from './icons';
import type { AppRoute } from './types';

function toMenuItems(routes: AppRoute[]): NonNullable<MenuProps['items']> {
  return routes
    .sort((left, right) => (left.sort ?? 0) - (right.sort ?? 0))
    .map((item) => {
      const Icon = item.icon ? ICON_MAP[item.icon] : undefined;
      const children = (item.children ?? [])
        .filter((child) => child.showInMenu !== false)
        .sort((left, right) => (left.sort ?? 0) - (right.sort ?? 0));
      if (children.length > 0) {
        return {
          key: item.path,
          icon: Icon ? createElement(Icon) : undefined,
          label: item.title,
          children: toMenuItems(children),
        };
      }
      return {
        key: item.path,
        icon: Icon ? createElement(Icon) : undefined,
        label: item.title,
      };
    });
}

export function buildMenuItems(
  routes: AppRoute[],
  permissionCodes: readonly string[] = [],
): NonNullable<MenuProps['items']> {
  return toMenuItems(filterMenuRoutes(routes, permissionCodes));
}
