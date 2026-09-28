import { PERMISSION_CODE, type RoleInfo } from '../types/tenant';

export function hasPermission(codes: readonly string[] | undefined, code: string): boolean {
  return Boolean(codes?.includes(code));
}

export function canManageMembers(codes: readonly string[] | undefined): boolean {
  return hasPermission(codes, PERMISSION_CODE.tenantMemberManage);
}

export function canManageRoles(codes: readonly string[] | undefined): boolean {
  return hasPermission(codes, PERMISSION_CODE.tenantRoleManage);
}

/** 前端不展示 OWNER；后端仍会拒绝非法授予。 */
export function grantableRoles(roles: readonly RoleInfo[]): RoleInfo[] {
  return roles.filter((role) => role.code !== 'OWNER');
}

export function memberRoleNames(roles: { name: string }[] | undefined): string {
  if (!roles?.length) {
    return '-';
  }
  return roles.map((item) => item.name).join('、');
}
