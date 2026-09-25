import type { MenuProps } from 'antd';
import { createElement } from 'react';
import { ICON_MAP } from './icons';
import type { AppRoute } from './types';

function visibleChildren(route: AppRoute): AppRoute[] {
  return (route.children ?? [])
    .filter((item) => item.showInMenu !== false)
    .sort((left, right) => (left.sort ?? 0) - (right.sort ?? 0));
}

export function buildMenuItems(routes: AppRoute[]): NonNullable<MenuProps['items']> {
  return routes
    .filter((item) => item.showInMenu !== false)
    .sort((left, right) => (left.sort ?? 0) - (right.sort ?? 0))
    .map((item) => {
      const Icon = item.icon ? ICON_MAP[item.icon] : undefined;
      const children = visibleChildren(item);
      if (children.length > 0) {
        return {
          key: item.path,
          icon: Icon ? createElement(Icon) : undefined,
          label: item.title,
          children: buildMenuItems(children),
        };
      }
      return {
        key: item.path,
        icon: Icon ? createElement(Icon) : undefined,
        label: item.title,
      };
    });
}
