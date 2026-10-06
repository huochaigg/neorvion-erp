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
  Warehouses: lazy(async () => {
    const module = await import('@/pages/warehouses/WarehousesPage');
    return { default: module.WarehousesPage };
  }),
  InventoryList: lazy(async () => {
    const module = await import('@/pages/inventory/InventoryListPage');
    return { default: module.InventoryListPage };
  }),
  InventoryDetail: lazy(async () => {
    const module = await import('@/pages/inventory/InventoryDetailPage');
    return { default: module.InventoryDetailPage };
  }),
  InventoryTransactions: lazy(async () => {
    const module = await import('@/pages/inventory/InventoryTransactionsPage');
    return { default: module.InventoryTransactionsPage };
  }),
  PurchaseList: lazy(async () => {
    const module = await import('@/pages/purchases/PurchaseListPage');
    return { default: module.PurchaseListPage };
  }),
  PurchaseForm: lazy(async () => {
    const module = await import('@/pages/purchases/PurchaseFormPage');
    return { default: module.PurchaseFormPage };
  }),
  PurchaseDetail: lazy(async () => {
    const module = await import('@/pages/purchases/PurchaseDetailPage');
    return { default: module.PurchaseDetailPage };
  }),
  Suppliers: lazy(async () => {
    const module = await import('@/pages/purchases/SuppliersPage');
    return { default: module.SuppliersPage };
  }),
  SalesOrderList: lazy(async () => {
    const module = await import('@/pages/orders/SalesOrderListPage');
    return { default: module.SalesOrderListPage };
  }),
  SalesOrderForm: lazy(async () => {
    const module = await import('@/pages/orders/SalesOrderFormPage');
    return { default: module.SalesOrderFormPage };
  }),
  SalesOrderDetail: lazy(async () => {
    const module = await import('@/pages/orders/SalesOrderDetailPage');
    return { default: module.SalesOrderDetailPage };
  }),
  Customers: lazy(async () => {
    const module = await import('@/pages/orders/CustomersPage');
    return { default: module.CustomersPage };
  }),
  Placeholder: lazy(async () => {
    const module = await import('@/pages/PlaceholderPage');
    return { default: module.PlaceholderPage };
  }),
};
