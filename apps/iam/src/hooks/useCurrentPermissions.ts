import { usePermissions } from './usePermissions';

/** 兼容 V2.3.2 页面；权限数据仍来自当前租户的 React Query。 */
export function useCurrentPermissions() {
  const { tenantId, permissions, isLoading } = usePermissions();
  return {
    tenantId,
    permissionCodes: permissions,
    isOwner: false,
    isLoading,
  };
}
