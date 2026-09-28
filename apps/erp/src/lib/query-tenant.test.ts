import assert from 'node:assert/strict';
import { QueryClient } from '@tanstack/react-query';
import { describe, it } from 'vitest';
import { isolateTenantQueries } from './query-tenant';

describe('isolateTenantQueries', () => {
  it('切租户后旧成员和商品缓存被移除，新租户数据仍在', () => {
    const client = new QueryClient();
    client.setQueryData(['tenant', 1, 'members', {}], { items: [{ id: 11 }] });
    client.setQueryData(['tenant', 2, 'members', {}], { items: [{ id: 22 }] });
    client.setQueryData(['tenant', 1, 'products', {}], { items: [{ id: 11 }] });
    client.setQueryData(['tenant', 2, 'products', {}], { items: [{ id: 22 }] });
    client.setQueryData(['tenant', 1, 'roles'], [{ id: 3 }]);
    client.setQueryData(['tenant', 1, 'my-permissions'], { roles: ['ADMIN'], permissions: ['x'] });
    isolateTenantQueries(client, 1);
    assert.equal(client.getQueryData(['tenant', 1, 'members', {}]), undefined);
    assert.equal(client.getQueryData(['tenant', 1, 'products', {}]), undefined);
    assert.equal(client.getQueryData(['tenant', 1, 'roles']), undefined);
    assert.equal(client.getQueryData(['tenant', 1, 'my-permissions']), undefined);
    assert.deepEqual(client.getQueryData(['tenant', 2, 'members', {}]), { items: [{ id: 22 }] });
    assert.deepEqual(client.getQueryData(['tenant', 2, 'products', {}]), { items: [{ id: 22 }] });
  });
});
