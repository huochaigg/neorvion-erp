import {
  canAccess,
  tenantMyPermissionsQueryKey,
  type PermissionMode,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { fetchMyPermissions } from '@/api/permissions';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function usePermissions() {
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const query = useQuery({
    queryKey: tenantMyPermissionsQueryKey(tenantId),
    queryFn: ({ signal }) => fetchMyPermissions(signal),
    enabled: tenantId != null,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
    placeholderData: undefined,
  });
  const permissions = query.data?.permissions ?? [];
  const roles = query.data?.roles ?? [];

  return {
    tenantId,
    roles,
    permissions,
    isLoading: tenantId != null && query.isPending,
    isFetching: query.isFetching,
    hasPermission: (code: string) => canAccess(permissions, [code]),
    hasAnyPermission: (codes: readonly string[]) => canAccess(permissions, codes, 'any'),
    hasAllPermissions: (codes: readonly string[]) => canAccess(permissions, codes, 'all'),
    can: (codes: readonly string[], mode: PermissionMode = 'all') =>
      canAccess(permissions, codes, mode),
  };
}
