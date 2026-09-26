import assert from 'node:assert/strict';
import { QueryClient } from '@tanstack/react-query';
import { currentUserQueryKey, healthQueryKey, myTenantsQueryKey } from '@neorvion/shared';
import { describe, it } from 'vitest';
import { isolateTenantQueries } from './query-tenant';

describe('isolateTenantQueries', () => {
  it('只删除旧租户缓存，保留用户资料和我的租户列表', () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(healthQueryKey(1), { app: 'old' });
    queryClient.setQueryData(healthQueryKey(2), { app: 'new' });
    queryClient.setQueryData(currentUserQueryKey(), { id: 7 });
    queryClient.setQueryData(myTenantsQueryKey(), [{ id: 1 }, { id: 2 }]);

    isolateTenantQueries(queryClient, 1);

    assert.equal(queryClient.getQueryData(healthQueryKey(1)), undefined);
    assert.deepEqual(queryClient.getQueryData(healthQueryKey(2)), { app: 'new' });
    assert.deepEqual(queryClient.getQueryData(currentUserQueryKey()), { id: 7 });
    assert.deepEqual(queryClient.getQueryData(myTenantsQueryKey()), [{ id: 1 }, { id: 2 }]);
  });
});
