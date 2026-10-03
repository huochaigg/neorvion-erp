import assert from 'node:assert/strict';
import {
  canAccess,
  canSetWarehouseDefault,
  PERMISSION_CODE,
  warehouseLocation,
  warehouseQueryKey,
  warehousesQueryKey,
  warehouseTypeLabel,
  WAREHOUSE_STATUS,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('仓库页 UI 规则', () => {
  it('按钮与后端权限编码一致：无对应 code 不显示操作', () => {
    const viewer = [PERMISSION_CODE.warehouseRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.warehouseCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.warehouseUpdate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.warehouseDisable]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.warehouseDelete]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.warehouseRead]), true);
    const warehouseRole = [
      PERMISSION_CODE.warehouseRead,
      PERMISSION_CODE.warehouseCreate,
      PERMISSION_CODE.warehouseUpdate,
    ];
    assert.equal(canAccess(warehouseRole, [PERMISSION_CODE.warehouseCreate]), true);
    assert.equal(canAccess(warehouseRole, [PERMISSION_CODE.warehouseUpdate]), true);
    assert.equal(canAccess(warehouseRole, [PERMISSION_CODE.warehouseDisable]), false);
    assert.equal(canAccess(warehouseRole, [PERMISSION_CODE.warehouseDelete]), false);
  });

  it('Query Key 含 tenantId 和筛选条件，切租户不会复用列表', () => {
    assert.notDeepEqual(warehousesQueryKey(1), warehousesQueryKey(2));
    assert.notDeepEqual(
      warehousesQueryKey(1, { q: '深圳', type: 'DOMESTIC', page: 1, pageSize: 20 }),
      warehousesQueryKey(1, { q: '广州', type: 'DOMESTIC', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(warehouseQueryKey(1, 9), warehouseQueryKey(2, 9));
  });

  it('已是默认或停用仓不显示设为默认', () => {
    assert.equal(canSetWarehouseDefault({ is_default: true, status: WAREHOUSE_STATUS.active }), false);
    assert.equal(canSetWarehouseDefault({ is_default: false, status: WAREHOUSE_STATUS.disabled }), false);
    assert.equal(canSetWarehouseDefault({ is_default: false, status: WAREHOUSE_STATUS.active }), true);
  });

  it('仓库类型用中文展示，国家城市可拼接', () => {
    assert.equal(warehouseTypeLabel('DOMESTIC'), '国内仓');
    assert.equal(warehouseTypeLabel('FBA'), 'FBA');
    assert.equal(warehouseLocation({ country_code: 'CN', city: '深圳' }), 'CN / 深圳');
    assert.equal(warehouseLocation({ country_code: null, city: null }), '-');
  });
});
