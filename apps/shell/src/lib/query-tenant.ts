import type { QueryClient } from '@tanstack/react-query';
import { tenantIdFromQueryKey } from '@neorvion/shared';

/** 只取消/移除旧租户的业务缓存，保留当前用户和我的租户列表。 */
export function isolateTenantQueries(queryClient: QueryClient, previousTenantId: number | null) {
  const matchesPrevious = {
    predicate: (query: { queryKey: readonly unknown[] }) =>
      tenantIdFromQueryKey(query.queryKey) === previousTenantId,
  };
  void queryClient.cancelQueries(matchesPrevious);
  queryClient.removeQueries(matchesPrevious);
}
