import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { PageKey, PageProps } from './types';

export const PAGE_COMPONENTS: Record<PageKey, LazyExoticComponent<ComponentType<PageProps>>> = {
  Dashboard: lazy(async () => {
    const module = await import('@/pages/DashboardPage');
    return { default: module.DashboardPage };
  }),
  Placeholder: lazy(async () => {
    const module = await import('@/pages/PlaceholderPage');
    return { default: module.PlaceholderPage };
  }),
  Users: lazy(async () => {
    const module = await import('@/pages/system/UsersPage');
    return { default: module.UsersPage };
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
  Applications: lazy(async () => {
    const module = await import('@/pages/system/ApplicationsPage');
    return { default: module.ApplicationsPage };
  }),
  Menus: lazy(async () => {
    const module = await import('@/pages/system/MenusPage');
    return { default: module.MenusPage };
  }),
  Audit: lazy(async () => {
    const module = await import('@/pages/system/AuditPage');
    return { default: module.AuditPage };
  }),
  Sessions: lazy(async () => {
    const module = await import('@/pages/system/SessionsPage');
    return { default: module.SessionsPage };
  }),
};
