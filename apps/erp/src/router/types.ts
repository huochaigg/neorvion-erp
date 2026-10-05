export type IconName =
  | 'DashboardOutlined'
  | 'AppstoreOutlined'
  | 'DatabaseOutlined'
  | 'ShopOutlined'
  | 'ShoppingCartOutlined'
  | 'AccountBookOutlined'
  | 'SettingOutlined';

export type PageKey =
  | 'Dashboard'
  | 'Placeholder'
  | 'Members'
  | 'Roles'
  | 'Permissions'
  | 'ProductList'
  | 'ProductForm'
  | 'ProductDetail'
  | 'ProductCategories'
  | 'Brands'
  | 'Warehouses'
  | 'InventoryList'
  | 'InventoryDetail'
  | 'InventoryTransactions'
  | 'PurchaseList'
  | 'PurchaseForm'
  | 'PurchaseDetail'
  | 'Suppliers';

export type PermissionMode = 'any' | 'all';

export interface AppRoute {
  path: string;
  name: string;
  title: string;
  description?: string;
  icon?: IconName;
  showInMenu?: boolean;
  redirect?: string;
  /** 隐藏页高亮的菜单 path，例如详情页指向列表 */
  activeMenu?: string;
  /** 单个权限；与 permissions 同时出现时以 permissions 为准 */
  permission?: string;
  permissions?: string[];
  permissionMode?: PermissionMode;
  sort?: number;
  component?: PageKey;
  children?: AppRoute[];
}

export interface PageProps {
  title?: string;
  description?: string;
}

export interface MatchedRoute {
  route: AppRoute;
  parents: AppRoute[];
}
