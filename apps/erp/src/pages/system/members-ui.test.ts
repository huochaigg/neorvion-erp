import assert from 'node:assert/strict';
import {
  canManageMembers,
  canManageRoles,
  grantableRoles,
  tenantMemberQueryKey,
  tenantMembersQueryKey,
  tenantMyPermissionsQueryKey,
  type RoleInfo,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

const ownerRole: RoleInfo = {
  id: 1,
  tenant_id: 1,
  name: '所有者',
  code: 'OWNER',
  description: '',
  is_system: true,
  created_at: '',
  updated_at: '',
  permissions: [],
  member_count: 0,
};

const adminRole: RoleInfo = { ...ownerRole, id: 2, name: '管理员', code: 'ADMIN' };

describe('成员与角色页 UI 规则', () => {
  it('无细粒度成员写权限时隐藏管理操作，有 create 则视为可管理', () => {
    assert.equal(canManageMembers(['tenant:member:read']), false);
    assert.equal(canManageMembers(['tenant:member:create']), true);
    assert.equal(canManageMembers(['tenant:member:manage']), true);
  });

  it('无细粒度角色写权限时隐藏角色管理操作', () => {
    assert.equal(canManageRoles(['tenant:role:read']), false);
    assert.equal(canManageRoles(['tenant:role:delete']), true);
    assert.equal(canManageRoles(['tenant:role:manage']), true);
  });

  it('授权下拉不展示 OWNER', () => {
    assert.deepEqual(
      grantableRoles([ownerRole, adminRole]).map((item) => item.code),
      ['ADMIN'],
    );
  });

  it('成员 Query Key 按租户和筛选隔离，避免切租户后看到旧名单', () => {
    assert.notDeepEqual(tenantMembersQueryKey(1), tenantMembersQueryKey(2));
    assert.notDeepEqual(tenantMemberQueryKey(1, 9), tenantMemberQueryKey(2, 9));
    assert.notDeepEqual(tenantMyPermissionsQueryKey(1), tenantMyPermissionsQueryKey(2));
    assert.notDeepEqual(
      tenantMembersQueryKey(1, { q: 'a', page: 1, pageSize: 20 }),
      tenantMembersQueryKey(1, { q: 'b', page: 1, pageSize: 20 }),
    );
  });
});
