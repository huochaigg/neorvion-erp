import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { safePathAfterTenantChange } from './erp-route';

describe('safePathAfterTenantChange', () => {
  it('列表和模块首页可以保留', () => {
    assert.equal(safePathAfterTenantChange('/dashboard'), null);
    assert.equal(safePathAfterTenantChange('/products/list'), null);
    assert.equal(safePathAfterTenantChange('/orders'), null);
    assert.equal(safePathAfterTenantChange('/inventory/list'), null);
  });

  it('带旧租户资源 ID 的路径回到列表', () => {
    assert.equal(safePathAfterTenantChange('/products/123'), '/products/list');
    assert.equal(safePathAfterTenantChange('/products/123/edit'), '/products/list');
    assert.equal(safePathAfterTenantChange('/orders/456'), '/orders');
  });
});
