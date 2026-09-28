import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  flattenProductCategories,
  specEntriesFromRecord,
  specRecordFromEntries,
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
});
