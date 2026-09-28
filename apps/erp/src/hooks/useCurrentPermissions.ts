import { tenantContextQueryKey } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { fetchTenantContext } from '@/api/members';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function useCurrentPermissions() {
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const query = useQuery({
    queryKey: tenantContextQueryKey(tenantId),
    queryFn: ({ signal }) => fetchTenantContext(signal),
    enabled: tenantId != null,
  });
  return {
    tenantId,
    permissionCodes: query.data?.permission_codes ?? [],
    isOwner: query.data?.is_owner ?? false,
    isLoading: query.isLoading,
  };
}
