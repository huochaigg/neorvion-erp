import {
  checkedKeysFromPermissionIds,
  permissionIdsFromCheckedKeys,
  type PermissionTreeNode,
} from '@neorvion/shared';
import { Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useMemo } from 'react';

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

export function PermissionTree({ tree, value = [], onChange, disabled }: PermissionTreeProps) {
  const data = useMemo(() => toDataNodes(tree), [tree]);
  const checkedKeys = useMemo(() => checkedKeysFromPermissionIds(tree, value), [tree, value]);

  return (
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
  );
}
