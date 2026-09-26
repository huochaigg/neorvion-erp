/** 主应用路由。/erp 只存在于 Shell，用来挂载子应用。 */
export const SHELL_ROUTES = {
  home: '/',
  login: '/login',
  register: '/register',
  workspaces: '/workspaces',
  workspaceCreate: '/workspaces/create',
  erp: '/erp',
} as const;

/** 主应用里的子应用挂载前缀。ERP 内部业务路径不放在本文件。 */
export const ERP_BASENAME = '/erp';

/** 主应用打开 ERP 时的默认落地页。具体菜单由 ERP 自己的 routes.ts 维护。 */
export const ERP_DEFAULT_PATH = '/dashboard';
