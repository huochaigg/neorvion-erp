/** 主应用通过 Wujie props 传给 ERP 子应用的受控状态。 */
export interface ShellToErpProps {
  token: string | null;
  tenantId: number | null;
  user: ShellUserSnapshot | null;
  /** Shell 单飞 Refresh。ERP 遇到 401 时调用，禁止自己打 /auth/refresh。 */
  refreshSession?: () => Promise<string>;
}

export interface ShellUserSnapshot {
  id: number;
  displayName: string;
}

export const SHELL_EVENTS = {
  tenantChanged: 'shell:tenant-changed',
  navigate: 'shell:navigate',
} as const;

export interface TenantChangedPayload {
  previousTenantId: number | null;
  currentTenantId: number | null;
}

/** 主子应用路由同步。payload.name 区分 ERP / 未来的 SCM、CRM。 */
export const MICRO_EVENTS = {
  childLocation: 'micro:child-location',
  hostNavigate: 'micro:host-navigate',
  tenantInaccessible: 'micro:tenant-inaccessible',
  unauthorized: 'micro:unauthorized',
} as const;

export type MicroHistoryAction = 'push' | 'replace';

export interface MicroLocationPayload {
  name: string;
  pathname: string;
  search: string;
  hash: string;
  action?: MicroHistoryAction;
}
