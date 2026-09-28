import type { PermissionTreeNode } from '../types/tenant';

/** 勾选树节点后只收集真实 permission_id。DIRECTORY 没有权限，不能提交。 */
export function permissionIdsFromCheckedKeys(
  tree: readonly PermissionTreeNode[],
  checkedKeys: readonly string[],
): number[] {
  const keys = new Set(checkedKeys);
  const ids: number[] = [];
  const walk = (nodes: readonly PermissionTreeNode[]) => {
    for (const node of nodes) {
      if (keys.has(node.key) && node.permission_id != null) {
        ids.push(node.permission_id);
      }
      if (node.children.length) {
        walk(node.children);
      }
    }
  };
  walk(tree);
  return [...new Set(ids)];
}

/** 用已保存的 permission_id 还原叶子勾选。父节点半选交给 Ant Design Tree。 */
export function checkedKeysFromPermissionIds(
  tree: readonly PermissionTreeNode[],
  ids: readonly number[],
): string[] {
  const idSet = new Set(ids);
  const keys: string[] = [];
  const walk = (nodes: readonly PermissionTreeNode[]) => {
    for (const node of nodes) {
      if (node.permission_id != null && idSet.has(node.permission_id)) {
        keys.push(node.key);
      }
      if (node.children.length) {
        walk(node.children);
      }
    }
  };
  walk(tree);
  return keys;
}

export function collectTreePermissionIds(tree: readonly PermissionTreeNode[]): number[] {
  const ids: number[] = [];
  const walk = (nodes: readonly PermissionTreeNode[]) => {
    for (const node of nodes) {
      if (node.permission_id != null) {
        ids.push(node.permission_id);
      }
      if (node.children.length) {
        walk(node.children);
      }
    }
  };
  walk(tree);
  return ids;
}
