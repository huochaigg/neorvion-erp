import assert from 'node:assert/strict';
import {
  canAccess,
  canAdjustOut,
  inventoryDetailQueryKey,
  inventoryQueryKey,
  inventoryStockStatus,
  inventoryTransactionTypeLabel,
  inventoryTransactionsQueryKey,
  PERMISSION_CODE,
  specValuesLabel,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('库存页 UI 规则', () => {
  it('按钮与后端权限编码一致：无对应 code 不显示操作', () => {
    const viewer = [PERMISSION_CODE.inventoryRead, PERMISSION_CODE.inventoryTransactionRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.inventoryInitialize]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.inventoryAdjust]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.inventoryRead]), true);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.inventoryTransactionRead]), true);
    const warehouse = [
      PERMISSION_CODE.inventoryRead,
      PERMISSION_CODE.inventoryInitialize,
      PERMISSION_CODE.inventoryAdjust,
      PERMISSION_CODE.inventoryTransactionRead,
    ];
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.inventoryInitialize]), true);
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.inventoryAdjust]), true);
    const operator = [PERMISSION_CODE.inventoryRead, PERMISSION_CODE.inventoryTransactionRead];
    assert.equal(canAccess(operator, [PERMISSION_CODE.inventoryAdjust]), false);
  });

  it('Query Key 含 tenantId 和筛选条件，切租户不会复用列表', () => {
    assert.notDeepEqual(inventoryQueryKey(1), inventoryQueryKey(2));
    assert.notDeepEqual(
      inventoryQueryKey(1, { q: '深圳', page: 1, pageSize: 20 }),
      inventoryQueryKey(1, { q: '广州', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(inventoryDetailQueryKey(1, 9), inventoryDetailQueryKey(2, 9));
    assert.notDeepEqual(
      inventoryTransactionsQueryKey(1, { type: 'INITIALIZE' }),
      inventoryTransactionsQueryKey(2, { type: 'INITIALIZE' }),
    );
  });

  it('流水类型中文、规格拼接、减少不能超过可用库存', () => {
    assert.equal(inventoryTransactionTypeLabel('INITIALIZE'), '初始化');
    assert.equal(inventoryTransactionTypeLabel('ADJUST_IN'), '库存增加');
    assert.equal(inventoryTransactionTypeLabel('ADJUST_OUT'), '库存减少');
    assert.equal(specValuesLabel({ 颜色: '黑', 尺码: '42' }), '颜色:黑 / 尺码:42');
    assert.equal(canAdjustOut(70, 80), false);
    assert.equal(canAdjustOut(70, 70), true);
    assert.equal(inventoryStockStatus({ quantity: 0, available_quantity: 0 }), 'ZERO');
    assert.equal(inventoryStockStatus({ quantity: 12, available_quantity: 8, threshold: 10 }), 'LOW');
    assert.equal(inventoryStockStatus({ quantity: 100, available_quantity: 80, threshold: 10 }), 'IN_STOCK');
  });
});
