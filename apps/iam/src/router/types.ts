export type IconName =
  | 'DashboardOutlined'
  | 'AppstoreOutlined'
  | 'SettingOutlined';

export type PageKey =
  | 'Dashboard'
  | 'Placeholder'
  | 'Users'
  | 'Members'
  | 'Roles'
  | 'Permissions'
  | 'Applications'
  | 'Menus'
  | 'Audit';

export interface PageProps {
  title?: string;
  description?: string;
}

export type PermissionMode = 'any' | 'all';

export interface MatchedRoute {
  route: AppRoute;
  parents: AppRoute[];
}

export interface AppRoute {
  path: string;
  name: string;
  title: string;
  description?: string;
  icon?: IconName;
  showInMenu?: boolean;
  sort?: number;
  permission?: string;
  permissions?: string[];
  permissionMode?: PermissionMode;
  activeMenu?: string;
  redirect?: string;
  component?: PageKey;
  children?: AppRoute[];
}
