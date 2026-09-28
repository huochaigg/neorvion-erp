import { PERMISSION_CODE, PERMISSION_MODULE_LABELS, type RoleInfo } from '../types/tenant';
import type { PermissionMode } from '../types/tenant';

export function hasPermission(codes: readonly string[] | undefined, code: string): boolean {
  return Boolean(codes?.includes(code));
}

export function hasAnyPermission(
  codes: readonly string[] | undefined,
  required: readonly string[],
): boolean {
  return required.some((code) => hasPermission(codes, code));
}

export function hasAllPermissions(
  codes: readonly string[] | undefined,
  required: readonly string[],
): boolean {
  if (!required.length) {
    return true;
  }
  return required.every((code) => hasPermission(codes, code));
}

export function canAccess(
  codes: readonly string[] | undefined,
  required: readonly string[],
  mode: PermissionMode = 'all',
): boolean {
  if (!required.length) {
    return true;
  }
  return mode === 'any' ? hasAnyPermission(codes, required) : hasAllPermissions(codes, required);
}

export function canManageMembers(codes: readonly string[] | undefined): boolean {
  return hasAnyPermission(codes, [
    PERMISSION_CODE.tenantMemberCreate,
    PERMISSION_CODE.tenantMemberUpdate,
    PERMISSION_CODE.tenantMemberRoleUpdate,
    PERMISSION_CODE.tenantMemberDisable,
    PERMISSION_CODE.tenantMemberRemove,
    PERMISSION_CODE.tenantMemberManage,
  ]);
}

export function canManageRoles(codes: readonly string[] | undefined): boolean {
  return hasAnyPermission(codes, [
    PERMISSION_CODE.tenantRoleCreate,
    PERMISSION_CODE.tenantRoleUpdate,
    PERMISSION_CODE.tenantRoleDelete,
    PERMISSION_CODE.tenantRolePermissionUpdate,
    PERMISSION_CODE.tenantRoleManage,
  ]);
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

export function permissionModuleLabel(module: string): string {
  return PERMISSION_MODULE_LABELS[module] ?? module;
}

export function groupPermissionsByModule<T extends { module: string }>(items: readonly T[]): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const current = groups.get(item.module) ?? [];
    current.push(item);
    groups.set(item.module, current);
  }
  return [...groups.entries()];
}

export function toggleModulePermissionIds(
  selected: readonly number[],
  moduleIds: readonly number[],
  checked: boolean,
): number[] {
  const next = new Set(selected);
  for (const id of moduleIds) {
    if (checked) {
      next.add(id);
    } else {
      next.delete(id);
    }
  }
  return [...next];
}
