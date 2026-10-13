import assert from 'node:assert/strict';
import { QueryClient } from '@tanstack/react-query';
import { describe, it } from 'vitest';
import { isolateTenantQueries } from './query-tenant';

describe('isolateTenantQueries', () => {
  it('切租户后旧知识库缓存被移除，新租户数据仍在', () => {
    const client = new QueryClient();
    client.setQueryData(['tenant', 1, 'knowledge-bases', {}], { items: [{ id: 11 }] });
    client.setQueryData(['tenant', 2, 'knowledge-bases', {}], { items: [{ id: 22 }] });
    client.setQueryData(['tenant', 1, 'knowledge-base', 11], { id: 11 });
    client.setQueryData(['tenant', 1, 'my-permissions'], { roles: ['OWNER'], permissions: ['x'] });
    isolateTenantQueries(client, 1);
    assert.equal(client.getQueryData(['tenant', 1, 'knowledge-bases', {}]), undefined);
    assert.equal(client.getQueryData(['tenant', 1, 'knowledge-base', 11]), undefined);
    assert.equal(client.getQueryData(['tenant', 1, 'my-permissions']), undefined);
    assert.deepEqual(client.getQueryData(['tenant', 2, 'knowledge-bases', {}]), { items: [{ id: 22 }] });
  });
});
