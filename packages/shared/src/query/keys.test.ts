import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  currentUserQueryKey,
  healthQueryKey,
  isTenantScopedQueryKey,
  myTenantsQueryKey,
  ordersQueryKey,
  productsQueryKey,
  tenantIdFromQueryKey,
} from './keys';

describe('query keys', () => {
  it('租户业务 key 以 tenantId 隔离，用户资料不带租户', () => {
    assert.notDeepEqual(healthQueryKey(1), healthQueryKey(2));
    assert.notDeepEqual(productsQueryKey(1), productsQueryKey(2));
    assert.notDeepEqual(ordersQueryKey(1), ordersQueryKey(2));
    assert.equal(isTenantScopedQueryKey(healthQueryKey(1)), true);
    assert.equal(tenantIdFromQueryKey(healthQueryKey(9)), 9);
    assert.equal(isTenantScopedQueryKey(currentUserQueryKey()), false);
    assert.equal(isTenantScopedQueryKey(myTenantsQueryKey()), false);
    assert.equal(tenantIdFromQueryKey(currentUserQueryKey()), undefined);
  });
});
