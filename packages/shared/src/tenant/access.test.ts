import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { lastTenantStorageKey, pickTenantSelection } from './access';
import type { Tenant } from '../types/tenant';

function tenant(partial: Partial<Tenant> & Pick<Tenant, 'id'>): Tenant {
  return {
    name: `Tenant ${partial.id}`,
    code: `t${partial.id}`,
    status: 'ACTIVE',
    created_by: 1,
    created_at: '',
    updated_at: '',
    my_role: 'OWNER',
    my_status: 'ACTIVE',
    is_owner: true,
    ...partial,
  };
}

describe('pickTenantSelection', () => {
  it('没有有效租户时进入创建流程', () => {
    assert.deepEqual(pickTenantSelection([], 1), { kind: 'none' });
    assert.deepEqual(
      pickTenantSelection([tenant({ id: 1, status: 'DISABLED' })], 1),
      { kind: 'none' },
    );
    assert.deepEqual(
      pickTenantSelection([tenant({ id: 1, my_status: 'DISABLED' })], 1),
      { kind: 'none' },
    );
  });

  it('只有一个有效租户时自动选择', () => {
    assert.deepEqual(pickTenantSelection([tenant({ id: 9 })], null), {
      kind: 'select',
      tenantId: 9,
    });
  });

  it('多个有效租户时恢复仍属于当前用户的上次选择', () => {
    const list = [tenant({ id: 2 }), tenant({ id: 5 })];
    assert.deepEqual(pickTenantSelection(list, 5), { kind: 'select', tenantId: 5 });
  });

  it('上次租户失效或无权访问时进入选择页，不会改选另一家', () => {
    const list = [tenant({ id: 2 }), tenant({ id: 5 })];
    assert.deepEqual(pickTenantSelection(list, 8), { kind: 'choose' });
    assert.deepEqual(
      pickTenantSelection([tenant({ id: 2 }), tenant({ id: 5, my_status: 'DISABLED' })], 5),
      { kind: 'select', tenantId: 2 },
    );
  });
});

describe('lastTenantStorageKey', () => {
  it('按用户隔离上次租户偏好', () => {
    assert.equal(lastTenantStorageKey(3), 'neorvion:last-tenant-id:3');
    assert.notEqual(lastTenantStorageKey(3), lastTenantStorageKey(4));
  });
});
