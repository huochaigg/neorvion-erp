import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import type { RoleInfo } from '../types/tenant';
import { PERMISSION_CODE } from '../types/tenant';
import {
  canAccess,
  canManageMembers,
  canManageRoles,
  grantableRoles,
  groupPermissionsByModule,
  hasAllPermissions,
  hasAnyPermission,
  hasPermission,
  memberRoleNames,
  permissionModuleLabel,
  toggleModulePermissionIds,
} from './permissions';

const admin: RoleInfo = {
  id: 2,
  tenant_id: 1,
  name: '管理员',
  code: 'ADMIN',
  description: '',
  is_system: true,
  created_at: '',
  updated_at: '',
  permissions: [],
  member_count: 0,
};

const owner: RoleInfo = { ...admin, id: 1, name: '所有者', code: 'OWNER' };

describe('permission UI helpers', () => {
  it('按权限编码而不是角色名判断管理按钮', () => {
    assert.equal(hasPermission(['tenant:member:manage'], PERMISSION_CODE.tenantMemberManage), true);
    assert.equal(canManageMembers(['tenant:member:read']), false);
    assert.equal(canManageMembers(['tenant:member:create']), true);
    assert.equal(canManageMembers(['tenant:member:manage']), true);
    assert.equal(canManageRoles(['tenant:role:read']), false);
    assert.equal(canManageRoles(['tenant:role:permission:update']), true);
    assert.equal(canManageRoles(['tenant:role:manage']), true);
    assert.equal(hasAnyPermission(['product:read'], ['tenant:member:manage', 'product:read']), true);
    assert.equal(hasAllPermissions(['product:read'], ['product:read', 'order:read']), false);
    assert.equal(canAccess(['product:read', 'order:read'], ['product:read', 'order:read'], 'all'), true);
  });

  it('授权选项隐藏 OWNER', () => {
    assert.deepEqual(
      grantableRoles([owner, admin]).map((item) => item.code),
      ['ADMIN'],
    );
    assert.equal(memberRoleNames([{ name: '运营' }, { name: '仓库' }]), '运营、仓库');
  });

  it('权限按模块分组，模块全选与取消只影响该组', () => {
    const items = [
      { id: 1, module: 'tenant', code: 'tenant:read' },
      { id: 2, module: 'tenant', code: 'tenant:update' },
      { id: 3, module: 'product', code: 'product:read' },
    ];
    const grouped = groupPermissionsByModule(items);
    assert.equal(grouped[0]?.[0], 'tenant');
    assert.equal(grouped[0]?.[1].length, 2);
    assert.deepEqual(toggleModulePermissionIds([], [1, 2], true), [1, 2]);
    assert.deepEqual(toggleModulePermissionIds([1, 2, 3], [1, 2], false), [3]);
    assert.equal(permissionModuleLabel('tenant'), '企业管理');
  });
});
