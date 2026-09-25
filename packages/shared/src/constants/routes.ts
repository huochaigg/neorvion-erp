/** 主应用路由。/erp 只存在于 Shell，用来挂载子应用。 */
export const SHELL_ROUTES = {
  home: '/',
  login: '/login',
  register: '/register',
  erp: '/erp',
} as const;

/** 主应用里的子应用挂载前缀。独立运行的 ERP 不使用该前缀。 */
export const ERP_BASENAME = '/erp';

/** 子应用自己的路径。独立访问 8016 时就是浏览器地址。 */
export const ERP_PATHS = {
  dashboard: '/dashboard',
  products: '/products',
  orders: '/orders',
  inventory: '/inventory',
  warehouses: '/warehouses',
} as const;

/** 主应用浏览器地址 = /erp + 子应用路径。 */
export const ERP_ROUTES = {
  dashboard: `${ERP_BASENAME}${ERP_PATHS.dashboard}`,
  products: `${ERP_BASENAME}${ERP_PATHS.products}`,
  orders: `${ERP_BASENAME}${ERP_PATHS.orders}`,
  inventory: `${ERP_BASENAME}${ERP_PATHS.inventory}`,
  warehouses: `${ERP_BASENAME}${ERP_PATHS.warehouses}`,
} as const;
