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
  ProductList: lazy(async () => {
    const module = await import('@/pages/products/ProductListPage');
    return { default: module.ProductListPage };
  }),
  ProductForm: lazy(async () => {
    const module = await import('@/pages/products/ProductFormPage');
    return { default: module.ProductFormPage };
  }),
  ProductDetail: lazy(async () => {
    const module = await import('@/pages/products/ProductDetailPage');
    return { default: module.ProductDetailPage };
  }),
  ProductCategories: lazy(async () => {
    const module = await import('@/pages/products/CategoriesPage');
    return { default: module.CategoriesPage };
  }),
  Brands: lazy(async () => {
    const module = await import('@/pages/products/BrandsPage');
    return { default: module.BrandsPage };
  }),
  Placeholder: lazy(async () => {
    const module = await import('@/pages/PlaceholderPage');
    return { default: module.PlaceholderPage };
  }),
};
