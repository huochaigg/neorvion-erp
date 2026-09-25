/** 主应用路由。ERP 业务页也使用 /erp 前缀，便于深链接与刷新。 */
export const SHELL_ROUTES = {
  home: '/',
  erp: '/erp',
} as const;

export const ERP_BASENAME = '/erp';

/** 子应用内部路由（相对于 basename）。 */
export const ERP_PATHS = {
  dashboard: '/dashboard',
  products: '/products',
  orders: '/orders',
  inventory: '/inventory',
  warehouses: '/warehouses',
} as const;

export const ERP_ROUTES = {
  dashboard: `${ERP_BASENAME}/dashboard`,
  products: `${ERP_BASENAME}/products`,
  orders: `${ERP_BASENAME}/orders`,
  inventory: `${ERP_BASENAME}/inventory`,
  warehouses: `${ERP_BASENAME}/warehouses`,
} as const;
