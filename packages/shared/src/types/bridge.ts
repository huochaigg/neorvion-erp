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
