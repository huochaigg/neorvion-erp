import { useEffect, useRef } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import { isolateTenantQueries } from '@/lib/query-tenant';
import { useTenantStore } from '@/stores/tenant-store';

/**
 * 租户变化时只隔离旧租户的 Query 缓存，不清空当前用户 / 我的租户列表。
 * 真正的切换入口是 switchTenant；这里兜底处理任何直接改 store 的情况。
 */
export function useTenantQuerySync(queryClient: QueryClient) {
  const tenantId = useTenantStore((state) => state.currentTenantId);
  const previousTenantId = useRef(tenantId);

  useEffect(() => {
    if (previousTenantId.current === tenantId) {
      return;
    }
    isolateTenantQueries(queryClient, previousTenantId.current);
    previousTenantId.current = tenantId;
  }, [queryClient, tenantId]);
}
