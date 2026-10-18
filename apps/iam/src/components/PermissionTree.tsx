import {
  checkedKeysFromPermissionIds,
  permissionIdsFromCheckedKeys,
  type PermissionTreeNode,
} from '@neorvion/shared';
import { Input, Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useMemo, useState } from 'react';

interface PermissionTreeProps {
  tree: PermissionTreeNode[];
  value?: number[];
  onChange?: (ids: number[]) => void;
  disabled?: boolean;
}

function toDataNodes(nodes: PermissionTreeNode[]): DataNode[] {
  return nodes.map((node) => ({
    key: node.key,
    title: node.title,
    children: node.children.length ? toDataNodes(node.children) : undefined,
  }));
}

function filterTree(nodes: PermissionTreeNode[], keyword: string): PermissionTreeNode[] {
  if (!keyword) {
    return nodes;
  }
  const needle = keyword.trim().toLowerCase();
  const walk = (items: PermissionTreeNode[]): PermissionTreeNode[] => {
    const result: PermissionTreeNode[] = [];
    for (const node of items) {
      const children = walk(node.children);
      const hit =
        node.title.toLowerCase().includes(needle) ||
        (node.permission_code ?? '').toLowerCase().includes(needle) ||
        node.key.toLowerCase().includes(needle);
      if (hit || children.length) {
        result.push({ ...node, children });
      }
    }
    return result;
  };
  return walk(nodes);
}

export function PermissionTree({ tree, value = [], onChange, disabled }: PermissionTreeProps) {
  const [keyword, setKeyword] = useState('');
  const filtered = useMemo(() => filterTree(tree, keyword), [tree, keyword]);
  const data = useMemo(() => toDataNodes(filtered), [filtered]);
  const checkedKeys = useMemo(() => checkedKeysFromPermissionIds(tree, value), [tree, value]);

  return (
    <div>
      <Input.Search
        allowClear
        className="mb-2"
        placeholder="搜索权限名称或编码"
        value={keyword}
        onChange={(event) => setKeyword(event.target.value)}
      />
      <Tree
        checkable
        defaultExpandAll
        disabled={disabled}
        selectable={false}
        treeData={data}
        checkedKeys={checkedKeys}
        onCheck={(keys) => {
          const list = Array.isArray(keys) ? keys.map(String) : keys.checked.map(String);
          onChange?.(permissionIdsFromCheckedKeys(tree, list));
        }}
      />
    </div>
  );
}
