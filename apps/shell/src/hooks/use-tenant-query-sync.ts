import { useEffect, useRef } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import { useShellStore } from '@/stores/shell-store';

/** 租户切换时取消未完成请求并清空 React Query 缓存。M2 接入真实租户后生效。 */
export function useTenantQuerySync(queryClient: QueryClient) {
  const tenantId = useShellStore((state) => state.currentTenantId);
  const previousTenantId = useRef(tenantId);

  useEffect(() => {
    if (previousTenantId.current === tenantId) {
      return;
    }
    void queryClient.cancelQueries();
    queryClient.clear();
    previousTenantId.current = tenantId;
  }, [queryClient, tenantId]);
}
