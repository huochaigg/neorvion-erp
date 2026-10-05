import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  currentUserQueryKey,
  healthQueryKey,
  isTenantScopedQueryKey,
  myTenantsQueryKey,
  ordersQueryKey,
  productsQueryKey,
  warehousesQueryKey,
  inventoryQueryKey,
  inventoryDetailQueryKey,
  inventoryTransactionsQueryKey,
  purchaseOrdersQueryKey,
  purchaseOrderQueryKey,
  suppliersQueryKey,
  tenantMembersQueryKey,
  tenantMyPermissionsQueryKey,
  tenantRolesQueryKey,
  tenantIdFromQueryKey,
} from './keys';

describe('query keys', () => {
  it('租户业务 key 以 tenantId 隔离，用户资料不带租户', () => {
    assert.notDeepEqual(healthQueryKey(1), healthQueryKey(2));
    assert.notDeepEqual(productsQueryKey(1), productsQueryKey(2));
    assert.notDeepEqual(warehousesQueryKey(1), warehousesQueryKey(2));
    assert.notDeepEqual(
      warehousesQueryKey(1, { q: 'sz', page: 1, pageSize: 20 }),
      warehousesQueryKey(1, { q: 'gz', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(productsQueryKey(1, { q: 'a' }), productsQueryKey(1, { q: 'b' }));
    assert.notDeepEqual(ordersQueryKey(1), ordersQueryKey(2));
    assert.notDeepEqual(inventoryQueryKey(1), inventoryQueryKey(2));
    assert.notDeepEqual(
      inventoryQueryKey(1, { q: 'sku', page: 1, pageSize: 20 }),
      inventoryQueryKey(1, { q: 'phone', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(inventoryDetailQueryKey(1, 9), inventoryDetailQueryKey(2, 9));
    assert.notDeepEqual(
      inventoryTransactionsQueryKey(1, { type: 'INITIALIZE' }),
      inventoryTransactionsQueryKey(1, { type: 'ADJUST_IN' }),
    );
    assert.notDeepEqual(suppliersQueryKey(1), suppliersQueryKey(2));
    assert.notDeepEqual(
      suppliersQueryKey(1, { q: '深圳', page: 1, pageSize: 20 }),
      suppliersQueryKey(1, { q: '广州', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(purchaseOrdersQueryKey(1), purchaseOrdersQueryKey(2));
    assert.notDeepEqual(
      purchaseOrdersQueryKey(1, { status: 'DRAFT', page: 1, pageSize: 20 }),
      purchaseOrdersQueryKey(1, { status: 'REJECTED', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(purchaseOrderQueryKey(1, 9), purchaseOrderQueryKey(2, 9));
    assert.notDeepEqual(tenantMembersQueryKey(1), tenantMembersQueryKey(2));
    assert.notDeepEqual(
      tenantMembersQueryKey(1, { page: 1, pageSize: 20 }),
      tenantMembersQueryKey(1, { page: 2, pageSize: 20 }),
    );
    assert.notDeepEqual(tenantRolesQueryKey(1), tenantRolesQueryKey(2));
    assert.notDeepEqual(tenantMyPermissionsQueryKey(1), tenantMyPermissionsQueryKey(2));
    assert.equal(isTenantScopedQueryKey(healthQueryKey(1)), true);
    assert.equal(tenantIdFromQueryKey(healthQueryKey(9)), 9);
    assert.equal(isTenantScopedQueryKey(currentUserQueryKey()), false);
    assert.equal(isTenantScopedQueryKey(myTenantsQueryKey()), false);
    assert.equal(tenantIdFromQueryKey(currentUserQueryKey()), undefined);
  });
});
