import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import type { PermissionTreeNode } from '../types/tenant';
import {
  checkedKeysFromPermissionIds,
  collectTreePermissionIds,
  permissionIdsFromCheckedKeys,
} from './permission-tree';

const tree: PermissionTreeNode[] = [
  {
    key: 'dir:system',
    title: '系统管理',
    type: 'DIRECTORY',
    permission_id: null,
    permission_code: null,
    children: [
      {
        key: 'menu:members',
        title: '成员管理',
        type: 'MENU',
        permission_id: null,
        permission_code: null,
        children: [
          {
            key: 'action:member-read',
            title: '查看成员',
            type: 'ACTION',
            permission_id: 1,
            permission_code: 'tenant:member:read',
            children: [],
          },
          {
            key: 'action:member-create',
            title: '添加成员',
            type: 'ACTION',
            permission_id: 2,
            permission_code: 'tenant:member:create',
            children: [],
          },
        ],
      },
    ],
  },
];

describe('permission tree helpers', () => {
  it('勾选父目录只保存子 ACTION 的 permission_id，不把 DIRECTORY 当成权限', () => {
    const ids = permissionIdsFromCheckedKeys(tree, [
      'dir:system',
      'menu:members',
      'action:member-read',
      'action:member-create',
    ]);
    assert.deepEqual(ids, [1, 2]);
    assert.equal(collectTreePermissionIds(tree).includes(0), false);
  });

  it('已有权限还原为叶子 key，MENU 本身没有 permission_id', () => {
    assert.deepEqual(checkedKeysFromPermissionIds(tree, [1]), ['action:member-read']);
    assert.equal(tree[0]?.permission_id, null);
    assert.equal(tree[0]?.children[0]?.permission_id, null);
  });
});
