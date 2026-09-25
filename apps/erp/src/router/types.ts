export type IconName =
  | 'DashboardOutlined'
  | 'AppstoreOutlined'
  | 'DatabaseOutlined'
  | 'ShopOutlined'
  | 'ShoppingCartOutlined';

export type PageKey = 'Dashboard' | 'Placeholder';

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
  permission?: string;
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
