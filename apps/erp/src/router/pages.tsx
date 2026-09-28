import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { PageKey, PageProps } from './types';

export const PAGE_COMPONENTS: Record<PageKey, LazyExoticComponent<ComponentType<PageProps>>> = {
  Dashboard: lazy(async () => {
    const module = await import('@/pages/DashboardPage');
    return { default: module.DashboardPage };
  }),
  Members: lazy(async () => {
    const module = await import('@/pages/system/MembersPage');
    return { default: module.MembersPage };
  }),
  Roles: lazy(async () => {
    const module = await import('@/pages/system/RolesPage');
    return { default: module.RolesPage };
  }),
  Permissions: lazy(async () => {
    const module = await import('@/pages/system/PermissionsPage');
    return { default: module.PermissionsPage };
  }),
  Placeholder: lazy(async () => {
    const module = await import('@/pages/PlaceholderPage');
    return { default: module.PlaceholderPage };
  }),
};
