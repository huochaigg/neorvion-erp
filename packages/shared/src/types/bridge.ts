/** 主应用通过 Wujie props 传给 ERP 子应用的受控状态。 */
export interface ShellToErpProps {
  token: string | null;
  tenantId: number | null;
  user: ShellUserSnapshot | null;
}

export interface ShellUserSnapshot {
  id: number;
  displayName: string;
}

export const SHELL_EVENTS = {
  tenantChanged: 'shell:tenant-changed',
  navigate: 'shell:navigate',
} as const;

/** 主子应用路由同步。payload.name 区分 ERP / 未来的 SCM、CRM。 */
export const MICRO_EVENTS = {
  childLocation: 'micro:child-location',
  hostNavigate: 'micro:host-navigate',
} as const;

export type MicroHistoryAction = 'push' | 'replace';

export interface MicroLocationPayload {
  name: string;
  pathname: string;
  search: string;
  hash: string;
  action?: MicroHistoryAction;
}
