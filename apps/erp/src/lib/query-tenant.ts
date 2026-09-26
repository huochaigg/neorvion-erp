import type { QueryClient } from '@tanstack/react-query';
import { tenantIdFromQueryKey } from '@neorvion/shared';

export function isolateTenantQueries(queryClient: QueryClient, previousTenantId: number | null) {
  const matchesPrevious = {
    predicate: (query: { queryKey: readonly unknown[] }) =>
      tenantIdFromQueryKey(query.queryKey) === previousTenantId,
  };
  void queryClient.cancelQueries(matchesPrevious);
  queryClient.removeQueries(matchesPrevious);
}
