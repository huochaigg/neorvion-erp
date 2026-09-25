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
};
