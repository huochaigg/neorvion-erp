import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  categoryRowExpandable,
  flattenProductCategories,
  specEntriesFromRecord,
  specRecordFromEntries,
  toCategoryTableRows,
  type ProductCategory,
} from './product';

const tree: ProductCategory[] = [
  {
    id: 1,
    tenant_id: 8,
    name: '服装',
    parent_id: null,
    level: 1,
    sort: 0,
    status: 'ACTIVE',
    created_at: '',
    updated_at: '',
    children: [
      {
        id: 2,
        tenant_id: 8,
        name: '男装',
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

describe('product helpers', () => {
  it('规格空键空值不进入 JSON', () => {
    assert.deepEqual(specRecordFromEntries([{ key: 'size', value: '42' }, { key: '', value: 'x' }]), {
      size: '42',
    });
    assert.deepEqual(specEntriesFromRecord({}), [{ key: '', value: '' }]);
  });

  it('类目树拍平保持先序', () => {
    assert.deepEqual(
      flattenProductCategories(tree).map((item) => item.id),
      [1, 2],
    );
  });

  it('第三级和没有子节点的类目不展开', () => {
    assert.equal(categoryRowExpandable({ level: 1, children: [{ id: 2 }] }), true);
    assert.equal(categoryRowExpandable({ level: 1, children: [] }), false);
    assert.equal(categoryRowExpandable({ level: 2, children: [{ id: 3 }] }), true);
    assert.equal(categoryRowExpandable({ level: 3, children: [{ id: 4 }] }), false);
    const rows = toCategoryTableRows([
      {
        ...tree[0],
        children: [
          {
            id: 2,
            tenant_id: 8,
            name: '男装',
            parent_id: 1,
            level: 2,
            sort: 0,
            status: 'ACTIVE',
            created_at: '',
            updated_at: '',
            children: [
              {
                id: 3,
                tenant_id: 8,
                name: '衬衫',
                parent_id: 2,
                level: 3,
                sort: 0,
                status: 'ACTIVE',
                created_at: '',
                updated_at: '',
                children: [],
              },
            ],
          },
        ],
      },
    ]);
    const level2 = rows[0]?.children?.[0];
    const level3 = level2?.children?.[0];
    assert.equal(categoryRowExpandable(level2 ?? { level: 2 }), true);
    assert.equal(level3?.children, undefined);
    assert.equal(categoryRowExpandable(level3 ?? { level: 3, children: [] }), false);
  });
});
