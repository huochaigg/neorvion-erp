import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import type { RoleInfo } from '../types/tenant';
import { PERMISSION_CODE } from '../types/tenant';
import {
  canManageMembers,
  canManageRoles,
  grantableRoles,
  hasPermission,
  memberRoleNames,
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
};

const owner: RoleInfo = { ...admin, id: 1, name: '所有者', code: 'OWNER' };

describe('permission UI helpers', () => {
  it('按权限编码而不是角色名判断管理按钮', () => {
    assert.equal(hasPermission(['tenant:member:manage'], PERMISSION_CODE.tenantMemberManage), true);
    assert.equal(canManageMembers(['tenant:member:read']), false);
    assert.equal(canManageMembers(['tenant:member:manage']), true);
    assert.equal(canManageRoles(['tenant:role:read']), false);
    assert.equal(canManageRoles(['tenant:role:manage']), true);
  });

  it('授权选项隐藏 OWNER', () => {
    assert.deepEqual(
      grantableRoles([owner, admin]).map((item) => item.code),
      ['ADMIN'],
    );
    assert.equal(memberRoleNames([{ name: '运营' }, { name: '仓库' }]), '运营、仓库');
  });
});
