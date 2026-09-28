import assert from 'node:assert/strict';
import {
  canAccess,
  flattenProductCategories,
  PERMISSION_CODE,
  productCategoriesQueryKey,
  productQueryKey,
  productsQueryKey,
  specEntriesFromRecord,
  specRecordFromEntries,
  type ProductCategory,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

const tree: ProductCategory[] = [
  {
    id: 1,
    tenant_id: 1,
    name: '电子产品',
    parent_id: null,
    level: 1,
    sort: 0,
    status: 'ACTIVE',
    created_at: '',
    updated_at: '',
    children: [
      {
        id: 2,
        tenant_id: 1,
        name: '手机',
        parent_id: 1,
        level: 2,
        sort: 0,
        status: 'ACTIVE',
        created_at: '',
        updated_at: '',
        children: [],
      },
    ],
  },
];

describe('商品页 UI 规则', () => {
  it('无 product:create 不显示新建，无 update 不显示编辑，无 delete 不显示删除', () => {
    const viewer = [PERMISSION_CODE.productRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.productCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.productUpdate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.productDelete]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.productRead]), true);
    const operator = [
      PERMISSION_CODE.productRead,
      PERMISSION_CODE.productCreate,
      PERMISSION_CODE.productUpdate,
    ];
    assert.equal(canAccess(operator, [PERMISSION_CODE.productCreate]), true);
    assert.equal(canAccess(operator, [PERMISSION_CODE.productDelete]), false);
  });

  it('Query Key 含 tenantId 和筛选条件，切租户不会复用列表', () => {
    assert.notDeepEqual(productsQueryKey(1), productsQueryKey(2));
    assert.notDeepEqual(
      productsQueryKey(1, { q: 'iphone', page: 1, pageSize: 20 }),
      productsQueryKey(1, { q: 'air', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(productQueryKey(1, 9), productQueryKey(2, 9));
    assert.notDeepEqual(productCategoriesQueryKey(1), productCategoriesQueryKey(2));
  });

  it('规格键值对与 JSON 互转，空行丢弃', () => {
    assert.deepEqual(specRecordFromEntries([{ key: '颜色', value: '黑色' }, { key: ' ', value: 'x' }]), {
      颜色: '黑色',
    });
    assert.deepEqual(specEntriesFromRecord({ color: 'black' }), [{ key: 'color', value: 'black' }]);
  });

  it('类目树可拍平供筛选使用', () => {
    assert.deepEqual(
      flattenProductCategories(tree).map((item) => item.name),
      ['电子产品', '手机'],
    );
  });
});
